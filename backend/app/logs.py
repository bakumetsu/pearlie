"""Pearlie's own log: one text file per local day, scrubbed, size capped, purged after 7 days."""

from __future__ import annotations

import base64
import contextvars
import json
import logging
import os
import re
import sys
import threading
import time
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, quote_plus, urlsplit

import httpx

LOG_KEEP_DAYS = 7
MAX_LINE = 2000
DAY_CAP = 20 * 1024 * 1024
ERROR_CAP = 22 * 1024 * 1024
MIN_SECRET_LEN = 4
CUT_MARK = "...[cut]"
CAP_LINE = "log cap reached for today, dropping lines"
FILE_RE = re.compile(r"pearlie-(\d{4})-(\d{2})-(\d{2})\.log")
SETTING_KEY = "logs.debug"
ENV_DEBUG = "PEARLIE_LOG_DEBUG"

_ROOT_NAMES = ("pearlie", "app")
_EXTRA_NAMES = {"uvicorn.error"}


# -- secret registry ---------------------------------------------------------

_secrets: set[str] = set()
_secrets_lock = threading.Lock()
_secrets_sorted: tuple[str, ...] = ()


def _variants(value: str) -> set[str]:
    raw = value.encode()
    forms = {
        value,
        quote(value, safe=""),
        quote_plus(value),
        base64.b64encode(raw).decode(),
        base64.urlsafe_b64encode(raw).decode(),
    }
    forms |= {f.rstrip("=") for f in list(forms)}
    return {f for f in forms if len(f) >= MIN_SECRET_LEN}


def register_secret(value: str | None) -> None:
    """Hide this exact value (and its URL-encoded and base64 forms) in every later line."""
    global _secrets_sorted
    if not value or len(value) < MIN_SECRET_LEN:
        return
    with _secrets_lock:
        _secrets.update(_variants(value))
        _secrets_sorted = tuple(sorted(_secrets, key=len, reverse=True))


def register_secrets(values: Iterable[str | None]) -> None:
    for v in values:
        register_secret(v)


def clear_secrets() -> None:
    """Forget the registry (tests only)."""
    global _secrets_sorted
    with _secrets_lock:
        _secrets.clear()
        _secrets_sorted = ()


def register_settings_secrets(settings: object) -> None:
    """Register every secret the env settings hold."""
    for name in (
        "secret_key",
        "stash_api_key",
        "komga_api_key",
        "gelbooru_api_key",
        "rule34_api_key",
        "nhentai_cookies",
    ):
        val = getattr(settings, name, None)
        getter = getattr(val, "get_secret_value", None)
        text = getter() if getter is not None else val
        if not isinstance(text, str) or not text:
            continue
        register_secret(text)
        if name == "nhentai_cookies":
            for part in text.split(";"):
                register_secret(part.partition("=")[2].strip())


def register_stored_connections(store: object) -> None:
    """Register every stored or env connection secret (startup)."""
    from app.connections_store import NAMES

    for name in NAMES:
        try:
            register_connection_secrets(store.field_values(name))  # type: ignore[attr-defined]
        except Exception:
            pass


def register_connection_secrets(values: dict[str, str]) -> None:
    """Register the plain field values of one stored connection (not the User-Agent)."""
    for fid, v in values.items():
        if fid != "user_agent":
            register_secret(v)
            if fid == "cookie":
                for part in v.split(";"):
                    register_secret(part.partition("=")[2].strip())


# -- job context -------------------------------------------------------------

_job: contextvars.ContextVar[str] = contextvars.ContextVar("pearlie_log_job", default="")


def set_job(job_id: str, source: str = "", post_id: str = "") -> contextvars.Token[str]:
    """Mark the current thread's lines with the job; reset with reset_job(token)."""
    tag = f"job={job_id}" + (f" {source}/{post_id}" if source else "")
    return _job.set(tag)


def reset_job(token: contextvars.Token[str]) -> None:
    _job.reset(token)


def ctx() -> str:
    """Prefix for a log message: the job tag and a space, or nothing."""
    tag = _job.get()
    return tag + " " if tag else ""


# -- URL sanitizer -----------------------------------------------------------


def safe_url(url: str) -> str:
    """host + path only: no scheme, userinfo, query or fragment."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return "invalid-url"
    return f"{host}{port}{parts.path}"


# -- scrubbing ---------------------------------------------------------------

_KEYWORDS = (
    r"api[_-]?key|apikey|key|token|password|passwd|secret|cookie|session|auth|authorization"
)
_KEYWORD_RE = re.compile(
    rf"(?<![A-Za-z0-9])({_KEYWORDS})(?![A-Za-z0-9])[\"']?(\s*[=:]\s*)"
    rf"(?:\"[^\"]*\"|'[^']*'|[^\s&;,\"']+)",
    re.IGNORECASE,
)
_HEADER_RE = re.compile(
    r"(?<![A-Za-z0-9])((?:set-)?cookie|authorization|api-?key|x-api-key)(\s*:\s*).*",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"\b(Bearer)\s+\S+", re.IGNORECASE)
_USERINFO_RE = re.compile(r"(https?://)[^/\s@:]+:[^/\s@]+@", re.IGNORECASE)
_QUERY_RE = re.compile(r"(https?://[^\s?#]+)[?#]\S*", re.IGNORECASE)
_LONG_RE = re.compile(
    r"(?<![A-Za-z0-9+/_.\-])(?=[A-Za-z0-9+]*\d)(?=[A-Za-z0-9+]*[A-Za-z])[A-Za-z0-9+]{40,}={0,2}"
    r"(?![A-Za-z0-9+/_.\-])"
)


def scrub(text: str) -> str:
    """Remove secrets from one piece of text (registry first, then patterns)."""
    for secret in _secrets_sorted:
        if secret in text:
            text = text.replace(secret, "***")
    text = _USERINFO_RE.sub(r"\1***@", text)
    text = _QUERY_RE.sub(r"\1?***", text)
    text = _HEADER_RE.sub(r"\1\2***", text)
    text = _BEARER_RE.sub(r"\1 ***", text)
    text = _KEYWORD_RE.sub(r"\1\2***", text)
    return _LONG_RE.sub("***", text)


def _escape(text: str) -> str:
    out: list[str] = []
    for ch in text:
        o = ord(ch)
        if ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif o < 32 or o == 127:
            out.append(f"\\x{o:02x}")
        else:
            out.append(ch)
    return "".join(out)


def _cut(line: str) -> str:
    if len(line) > MAX_LINE:
        return line[: MAX_LINE - len(CUT_MARK)] + CUT_MARK
    return line


class ScrubFilter(logging.Filter):
    """Scrubs message, %-args and traceback of a record before any formatter sees it."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        record.msg = scrub(msg)
        record.args = None
        if record.exc_info:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
            record.exc_info = None
        if record.exc_text:
            record.exc_text = scrub(record.exc_text)
        return True


class NameFilter(logging.Filter):
    """Passes pearlie*, app.* and uvicorn.error (not uvicorn.access, not httpx)."""

    def filter(self, record: logging.LogRecord) -> bool:
        name = record.name
        return name in _EXTRA_NAMES or any(
            name == n or name.startswith(n + ".") for n in _ROOT_NAMES
        )


def format_line(record: logging.LogRecord, when: datetime | None = None) -> str:
    """One scrubbed, escaped, capped line for a record."""
    ts = when or datetime.fromtimestamp(record.created)
    msg = record.getMessage() if record.args else str(record.msg)
    if record.exc_info:
        msg += " | " + logging.Formatter().formatException(record.exc_info)
    elif record.exc_text:
        msg += " | " + record.exc_text
    name = record.name
    head = f"{ts:%Y-%m-%d %H:%M:%S}.{ts.microsecond // 1000:03d} {record.levelname:<5} {name}  "
    return _cut(_escape(scrub(head + msg)))


# -- handler -----------------------------------------------------------------


def purge_old(
    directory: Path, keep_days: int = LOG_KEEP_DAYS, today: date | None = None
) -> list[str]:
    """Delete pearlie-YYYY-MM-DD.log files older than today minus keep_days; touch nothing else."""
    cutoff = (today or date.today()) - timedelta(days=keep_days)
    removed: list[str] = []
    try:
        entries = list(directory.iterdir())
    except OSError:
        return removed
    for f in entries:
        m = FILE_RE.fullmatch(f.name)
        if m is None or not f.is_file():
            continue
        try:
            day = date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            continue
        if day < cutoff:
            try:
                f.unlink()
                removed.append(f.name)
            except OSError:
                pass
    return removed


class DailyFileHandler(logging.Handler):
    """Appends one line per record to pearlie-YYYY-MM-DD.log (date of the record)."""

    def __init__(
        self,
        directory: Path,
        keep_days: int = LOG_KEEP_DAYS,
        day_cap: int = DAY_CAP,
        error_cap: int = ERROR_CAP,
        level: int = logging.INFO,
    ) -> None:
        super().__init__(level)
        self.directory = Path(directory)
        self.keep_days = keep_days
        self.day_cap = day_cap
        self.error_cap = error_cap
        self._day: date | None = None
        self._size = 0
        self._cap_noted = False
        self._warned = False
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            self._warn_once("cannot create log folder")
        purge_old(self.directory, self.keep_days)

    def _warn_once(self, why: str) -> None:
        if not self._warned:
            self._warned = True
            print(f"pearlie log: {why}", file=sys.stderr)

    def path_for(self, day: date) -> Path:
        return self.directory / f"pearlie-{day:%Y-%m-%d}.log"

    def _roll(self, day: date) -> None:
        first = self._day is None
        self._day = day
        self._cap_noted = False
        try:
            self._size = self.path_for(day).stat().st_size
        except OSError:
            self._size = 0
        if not first:
            purge_old(self.directory, self.keep_days, day)

    def _append(self, day: date, line: str) -> None:
        data = (line + "\n").encode("utf-8", "replace")
        with open(self.path_for(day), "ab") as f:
            f.write(data)
        self._size += len(data)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            when = datetime.fromtimestamp(record.created)
            day = when.date()
            line = format_line(record, when)
            if day != self._day:
                self._roll(day)
            size = self._size + len(line.encode("utf-8", "replace")) + 1
            cap = self.error_cap if record.levelno >= logging.ERROR else self.day_cap
            if size > cap:
                if not self._cap_noted:
                    self._cap_noted = True
                    stamp = f"{when:%Y-%m-%d %H:%M:%S}.{when.microsecond // 1000:03d}"
                    note = f"{stamp} ERROR pearlie.logs  {CAP_LINE}"
                    self._append(day, note)
                return
            self._append(day, line)
        except Exception:
            self._warn_once("write failed, dropping lines")


# -- setup -------------------------------------------------------------------

_handler: DailyFileHandler | None = None
_console: logging.Handler | None = None


def _env_flag(name: str, env: dict[str, str] | None = None) -> bool:
    return (env if env is not None else os.environ).get(name, "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def read_debug_setting(db_path: Path) -> bool:
    """The stored logs.debug switch, or the env override."""
    if _env_flag(ENV_DEBUG):
        return True
    try:
        from app.db import connect

        with connect(db_path) as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (SETTING_KEY,)
            ).fetchone()
        return bool(row) and row[0] == "1"
    except Exception:
        return False


def set_debug(on: bool) -> None:
    """Lower (True) or raise (False) the file's minimum level live."""
    if _handler is not None:
        _handler.setLevel(logging.DEBUG if on else logging.INFO)


def is_debug() -> bool:
    return _handler is not None and _handler.level <= logging.DEBUG


def log_dir() -> Path | None:
    return _handler.directory if _handler is not None else None


def setup_logging(
    directory: Path,
    debug: bool = False,
    keep_days: int = LOG_KEEP_DAYS,
) -> DailyFileHandler:
    """Attach the daily file handler to the root logger (replaces an earlier one)."""
    global _handler, _console
    root = logging.getLogger()
    if _handler is not None:
        root.removeHandler(_handler)
        _handler.close()
    handler = DailyFileHandler(directory, keep_days=keep_days)
    handler.addFilter(NameFilter())
    handler.addFilter(ScrubFilter())
    root.addHandler(handler)
    _handler = handler
    for name in (*_ROOT_NAMES, *_EXTRA_NAMES):
        logging.getLogger(name).setLevel(logging.DEBUG)
    # A root handler stops the stdlib last-resort stderr output, so keep warnings visible.
    if _console is None and not [h for h in root.handlers if h is not handler]:
        _console = logging.StreamHandler()
        _console.setLevel(logging.WARNING)
        _console.addFilter(ScrubFilter())
        root.addHandler(_console)
    set_debug(debug)
    return handler


# ---------------------------------------------------------------------------
# Outbound HTTP hooks (T-141, design 4.2)
# ---------------------------------------------------------------------------

_out = logging.getLogger("pearlie.out")
_T0 = "pearlie_t0"
_HEADER_WHITELIST = ("content-type", "server", "retry-after", "cf-mitigated")
_GQL_OP = re.compile(r"^\s*(?:query|mutation)\s+(\w+)")
_GQL_FIELD = re.compile(r"\{\s*(\w+)")
_SNIPPET = 200


def _ms(request: httpx.Request) -> int:
    t0 = request.extensions.get(_T0)
    return int((time.monotonic() - t0) * 1000) if isinstance(t0, float) else 0


def _gql_op(request: httpx.Request) -> str:
    try:
        text = json.loads(request.content).get("query", "")
    except (ValueError, AttributeError, httpx.RequestNotRead):
        return "unknown"
    if not isinstance(text, str):
        return "unknown"
    m = _GQL_OP.match(text) or _GQL_FIELD.search(text)
    return m.group(1) if m else "anonymous"


def _gql_error(resp: httpx.Response) -> str:
    try:
        resp.read()
        errors = resp.json().get("errors")
        if errors:
            return str(errors[0].get("message", ""))[:_SNIPPET]
    except (ValueError, AttributeError, TypeError, IndexError, httpx.HTTPError):
        pass
    return ""


def _header_line(resp: httpx.Response) -> str:
    items = []
    for name in _HEADER_WHITELIST:
        value = resp.headers.get(name)
        if value:
            items.append(f"{name}={value[:100]!r}")
    return " ".join(items)


def install_http_hooks(client: httpx.Client, site: str, save: bool = False) -> httpx.Client:
    """Log one line per call made by *client*; *site* is the configured site label.

    INFO for non-2xx and save-pipeline (*save*) calls, DEBUG for other 2xx.
    Transport errors log the exception class name only, at WARNING.
    """

    def on_request(request: httpx.Request) -> None:
        request.extensions[_T0] = time.monotonic()

    def on_response(resp: httpx.Response) -> None:
        req = resp.request
        status = resp.status_code
        ok = 200 <= status < 300
        where = safe_url(str(req.url))
        line = f"OUT site={site} {req.method} {where} status={status} ms={_ms(req)}"
        # Stash media is streamed (open_media): reading its body here would consume it.
        streamed = site == "stash" and not req.url.path.endswith("/graphql")
        if site == "stash" and not streamed:
            line += f" op={_gql_op(req)}"
            err = _gql_error(resp) if ok else ""
            if err:
                line += f" gql_error={err!r}"
        if not ok:
            hdrs = _header_line(resp)
            if hdrs:
                line += " " + hdrs
            if not streamed and _out.isEnabledFor(logging.DEBUG):
                try:
                    resp.read()
                    body = resp.text[:_SNIPPET]
                except httpx.HTTPError:
                    body = ""
                if body:
                    line += f" body={body!r}"
        level = logging.INFO if (not ok or save) else logging.DEBUG
        _out.log(level, line)

    hooks = client.event_hooks
    hooks.setdefault("request", []).append(on_request)
    hooks.setdefault("response", []).append(on_response)
    client.event_hooks = hooks

    plain_send = client.send

    def send(request: httpx.Request, **kwargs):  # type: ignore[no-untyped-def]
        try:
            return plain_send(request, **kwargs)
        except httpx.TransportError as exc:
            _out.warning(
                "OUT site=%s %s %s error=%s ms=%d",
                site,
                request.method,
                safe_url(str(request.url)),
                type(exc).__name__,
                _ms(request),
            )
            raise

    client.send = send  # type: ignore[method-assign]
    return client
