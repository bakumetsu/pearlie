import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Literal

from pydantic import SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(Exception):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PEARLIE_", extra="ignore")

    mode: Literal["fixture", "real"]
    real: str = ""
    db_path: Path = Path("data/pearlie.db")
    static_dir: Path = Path("../frontend/dist")
    host: str = "127.0.0.1"
    port: int = 8000
    trusted_network: bool = False
    secret_key: SecretStr = SecretStr("")
    stash_url: str = ""
    stash_api_key: SecretStr = SecretStr("")
    stash_public_url: str = ""
    komga_url: str = ""
    komga_api_key: SecretStr = SecretStr("")
    gelbooru_user_id: str = ""
    gelbooru_api_key: SecretStr = SecretStr("")
    rule34_user_id: str = ""
    rule34_api_key: SecretStr = SecretStr("")
    nhentai_cookies: SecretStr = SecretStr("")
    stash_temp_dir: Path = Path("/mnt/media/stash/Temp")
    stash_default_dir: Path = Path("/mnt/media/stash/Other")
    stash_path_prefix_pearlie: str = ""
    stash_path_prefix_stash: str = ""
    stash_scan_timeout_s: float = 120.0
    komga_incoming_dir: str = ""
    komga_temp_dir: Path = Path("/mnt/media/komga/.pearlie-tmp")
    komga_path_prefix_pearlie: str = ""
    komga_path_prefix_komga: str = ""
    download_interval_s: float = 2.0
    worker_enabled: bool = True
    log_dir: Path | None = None
    log_keep_days: int = 7

    def safe_summary(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, SecretStr):
                result[name] = "set" if value.get_secret_value() else "unset"
            elif name.endswith("_url"):
                result[name] = "set" if value else "unset"
            else:
                result[name] = str(value)
        return result


LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
AUTO_HOST_IPV4_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")


def resolve_auto_host() -> str | None:
    try:
        result = subprocess.run(
            ["hostname", "-I"],
            timeout=3,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    for token in (result.stdout or "").split():
        if AUTO_HOST_IPV4_RE.match(token):
            return token
    return None


def load_settings(**overrides: Any) -> Settings:
    try:
        settings = Settings(**overrides)
        if settings.host == "auto":
            ip = resolve_auto_host()
            if ip is None:
                logging.getLogger(__name__).warning(
                    "PEARLIE_HOST=auto found no IPv4; bound to 127.0.0.1, "
                    "restart pearlie once the container has an address"
                )
                settings = settings.model_copy(update={"host": "127.0.0.1"})
            elif not settings.trusted_network:
                logging.getLogger(__name__).warning(
                    "PEARLIE_HOST=auto stays on 127.0.0.1 until PEARLIE_TRUSTED_NETWORK=1 is set"
                )
                settings = settings.model_copy(update={"host": "127.0.0.1"})
            else:
                settings = settings.model_copy(update={"host": ip})
        if settings.host not in LOOPBACK_HOSTS and not settings.trusted_network:
            raise ConfigError(
                "no login yet: a non-loopback PEARLIE_HOST needs "
                "PEARLIE_TRUSTED_NETWORK=1 (access limited to your tailnet or reverse proxy)"
            )
        return settings
    except ValidationError as exc:
        errors = exc.errors()
        mode_errors = [e for e in errors if "mode" in e["loc"]]
        if mode_errors:
            first = mode_errors[0]
            val = first.get("input")
            display = "unset" if first["type"] == "missing" or val is None else str(val)
            raise ConfigError(
                f"PEARLIE_MODE must be set to 'fixture' or 'real' (got: {display})"
            ) from exc
        field_names = sorted(set(str(e["loc"][0]) for e in errors))
        raise ConfigError(f"invalid configuration: {', '.join(field_names)}") from exc
