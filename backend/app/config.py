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
    stash_url: str = ""
    stash_api_key: SecretStr = SecretStr("")
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
    download_interval_s: float = 2.0
    worker_enabled: bool = True

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


def load_settings(**overrides: Any) -> Settings:
    try:
        settings = Settings(**overrides)
        if settings.host not in LOOPBACK_HOSTS:
            raise ConfigError("no login yet: Pearlie binds to loopback only until T-06")
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
