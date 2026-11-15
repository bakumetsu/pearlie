"""uvicorn console logs must not carry secrets from the request URL."""

from __future__ import annotations

import io
import logging
import logging.config

from app import logs


def _console(config: dict) -> tuple[io.StringIO, logging.Logger]:
    # Same config uvicorn gets, with the console streams swapped for buffers.
    buf = io.StringIO()
    for h in config["handlers"].values():
        h["stream"] = buf
    logging.config.dictConfig(config)
    return buf, logging.getLogger("uvicorn.access")


def test_access_log_drops_query_secrets() -> None:
    buf, access = _console(logs.uvicorn_log_config())
    access.info(
        '%s - "%s %s HTTP/%s" %d',
        "127.0.0.1:5000",
        "GET",
        "/api/media/x?apikey=SEKRET123&token=abcdef&foo=1",
        "1.1",
        200,
    )
    out = buf.getvalue()
    assert "SEKRET123" not in out and "abcdef" not in out and "foo=1" not in out
    assert "GET /api/media/x" in out and "200" in out


def test_error_log_scrubs_cookie_and_key() -> None:
    buf, _ = _console(logs.uvicorn_log_config())
    logging.getLogger("uvicorn.error").error("bad request Cookie: sid=SEKRET123 apikey=SEKRET456")
    assert "SEKRET123" not in buf.getvalue() and "SEKRET456" not in buf.getvalue()
