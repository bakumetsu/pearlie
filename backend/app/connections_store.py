"""Encrypted per-connection address and secret store."""

from __future__ import annotations

import logging
import os
from collections.abc import Collection, Mapping
from typing import Literal, NamedTuple
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from app import logs
from app.config import Settings
from app.db import connect

logger = logging.getLogger("pearlie")

NAMES: tuple[str, ...] = ("stash", "komga", "danbooru", "gelbooru", "rule34", "nhentai")

FIXED_HOSTS: dict[str, str] = {
    "danbooru": "https://danbooru.donmai.us",
    "gelbooru": "https://gelbooru.com",
    "rule34": "https://api.rule34.xxx",
    "nhentai": "https://nhentai.net",
}

ENV_FIELDS: dict[str, tuple[str, str]] = {
    "stash": ("stash_url", "stash_api_key"),
    "komga": ("komga_url", "komga_api_key"),
    "danbooru": ("", ""),
    "gelbooru": ("", "gelbooru_api_key"),
    "rule34": ("", "rule34_api_key"),
    "nhentai": ("", "nhentai_cookies"),
}


class FieldDef(NamedTuple):
    id: str
    label: str
    env_attr: str


FIELDS: dict[str, tuple[FieldDef, ...]] = {
    "stash": (FieldDef("api_key", "API key", "stash_api_key"),),
    "komga": (FieldDef("api_key", "API key", "komga_api_key"),),
    "danbooru": (FieldDef("login", "Login", ""), FieldDef("api_key", "API key", "")),
    "gelbooru": (
        FieldDef("user_id", "User ID", "gelbooru_user_id"),
        FieldDef("api_key", "API key", "gelbooru_api_key"),
    ),
    "rule34": (
        FieldDef("user_id", "User ID", "rule34_user_id"),
        FieldDef("api_key", "API key", "rule34_api_key"),
    ),
    "nhentai": (
        FieldDef("cookie", "Cookie", "nhentai_cookies"),
        FieldDef("user_agent", "User-Agent", ""),
    ),
}

# The field kept under the old single-secret storage key, so upgrades keep working.
PRIMARY: dict[str, str] = {
    "stash": "api_key",
    "komga": "api_key",
    "danbooru": "api_key",
    "gelbooru": "api_key",
    "rule34": "api_key",
    "nhentai": "cookie",
}


class StoreError(Exception):
    """Error raised by ConnectionStore operations."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code: str = code


class ConnectionStore:
    """Stores per-connection address and Fernet-encrypted secret."""

    def __init__(self, settings: Settings, mem: dict[str, str] | None) -> None:
        self._settings: Settings = settings
        self._mem: dict[str, str] | None = mem
        self._auto_key: str | None = None
        self._env_key_warned: bool = False

    # -- storage backend --

    def _read(self, key: str) -> str | None:
        if self._settings.mode == "fixture":
            if self._mem is not None:
                return self._mem.get(key)
            return None
        conn = connect(self._settings.db_path)
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        finally:
            conn.close()
        return row["value"] if row is not None else None

    def _write(self, key: str, value: str) -> None:
        if self._settings.mode == "fixture":
            if self._mem is not None:
                self._mem[key] = value
            return
        conn = connect(self._settings.db_path)
        try:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()

    def _delete(self, key: str) -> None:
        if self._settings.mode == "fixture":
            if self._mem is not None:
                self._mem.pop(key, None)
            return
        conn = connect(self._settings.db_path)
        try:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            conn.commit()
        finally:
            conn.close()

    # -- key management --

    def _key(self) -> str:
        env = self._settings.secret_key.get_secret_value()
        if env:
            try:
                Fernet(env)
                return env
            except (ValueError, TypeError):
                if not self._env_key_warned:
                    self._env_key_warned = True
                    logger.warning(
                        "PEARLIE_SECRET_KEY is not a valid key; using the generated key file"
                    )
        if self._auto_key is not None:
            return self._auto_key
        path = self._settings.db_path.parent / "secret.key"
        try:
            if path.is_file():
                key = path.read_text(encoding="utf-8").strip()
            else:
                key = Fernet.generate_key().decode()
                path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(key)
                try:
                    os.chmod(path, 0o600)
                except OSError:
                    pass
        except FileExistsError:
            key = path.read_text(encoding="utf-8").strip()
        except OSError:
            logger.warning("could not read or create the secret key file")
            return ""
        if key:
            self._auto_key = key
        return key

    def can_store(self) -> bool:
        key: str = self._key()
        if not key:
            return False
        try:
            Fernet(key)
        except (ValueError, TypeError):
            return False
        return True

    def _fernet(self) -> Fernet:
        return Fernet(self._key())

    # -- env lock detection --

    def field_locked(self, name: str, fid: str) -> bool:
        attr: str = self._field_def(name, fid).env_attr
        if attr and attr in self._settings.model_fields_set:
            val: object = getattr(self._settings, attr)
            if isinstance(val, SecretStr):
                return bool(val.get_secret_value())
            return bool(val)
        return False

    def env_locked(self, name: str) -> dict[str, bool]:
        addr_attr, _ = ENV_FIELDS.get(name, ("", ""))
        locked: dict[str, bool] = {"address": False, "secret": False}
        if addr_attr and addr_attr in self._settings.model_fields_set:
            val: object = getattr(self._settings, addr_attr)
            if isinstance(val, SecretStr):
                locked["address"] = bool(val.get_secret_value())
            else:
                locked["address"] = bool(val)
        if name in PRIMARY:
            locked["secret"] = self.field_locked(name, PRIMARY[name])
        return locked

    # -- fields --

    def _field_def(self, name: str, fid: str) -> FieldDef:
        for f in FIELDS.get(name, ()):
            if f.id == fid:
                return f
        raise StoreError("unknown_field")

    def _skey(self, name: str, fid: str) -> str:
        if PRIMARY.get(name) == fid:
            return f"connections.{name}.secret"
        return f"connections.{name}.field.{fid}"

    def field_state(self, name: str, fid: str) -> Literal["set", "missing"]:
        if self.field_locked(name, fid):
            return "set"
        stored: str | None = self._read(self._skey(name, fid))
        return "set" if stored is not None else "missing"

    def field_value(self, name: str, fid: str) -> str:
        """Plain value of one field (env wins over stored); empty when unset."""
        if self.field_locked(name, fid):
            val: object = getattr(self._settings, self._field_def(name, fid).env_attr)
            if isinstance(val, SecretStr):
                return val.get_secret_value()
            return str(val) if val else ""
        stored: str | None = self._read(self._skey(name, fid))
        if stored is None or not self.can_store():
            return ""
        try:
            return self._fernet().decrypt(stored.encode()).decode()
        except InvalidToken:
            logger.warning("stored %s for %s cannot be decrypted", fid, name)
            return ""

    def field_values(self, name: str) -> dict[str, str]:
        """All fields of a connection that hold a value."""
        out: dict[str, str] = {}
        for f in FIELDS.get(name, ()):
            v: str = self.field_value(name, f.id)
            if v:
                out[f.id] = v
        return out

    # -- public queries --

    def address(self, name: str) -> str:
        if name in FIXED_HOSTS:
            return FIXED_HOSTS[name]
        locked = self.env_locked(name)
        if locked["address"]:
            addr_attr, _ = ENV_FIELDS[name]
            val: object = getattr(self._settings, addr_attr)
            if isinstance(val, SecretStr):
                return val.get_secret_value()
            return str(val)
        stored: str | None = self._read(f"connections.{name}.address")
        return stored if stored is not None else ""

    def secret_state(self, name: str) -> Literal["set", "missing"]:
        return self.field_state(name, PRIMARY[name])

    def effective_secret(self, name: str) -> str:
        return self.field_value(name, PRIMARY[name])

    # -- mutation --

    def save(
        self,
        name: str,
        address: str | None,
        secret: str | None,
        clear_secret: bool,
        fields: Mapping[str, str] | None = None,
        clear_fields: Collection[str] = (),
    ) -> None:
        if name not in NAMES:
            raise StoreError("unknown")

        locked = self.env_locked(name)

        # Fixed-host: address not editable
        if address is not None and name in FIXED_HOSTS:
            raise StoreError("bad_address")

        # Env-lock: cannot override env-provided values
        if address is not None and locked["address"]:
            raise StoreError("locked")
        if secret is not None and locked["secret"]:
            raise StoreError("locked")

        # Per-field values; the old secret/clear_secret arguments address the primary field
        sets: dict[str, str] = {k: v for k, v in (fields or {}).items() if v != ""}
        clears: set[str] = set(clear_fields)
        if secret is not None and secret != "":
            sets[PRIMARY[name]] = secret
        if clear_secret:
            clears.add(PRIMARY[name])
        for fid in [*sets, *clears]:
            self._field_def(name, fid)
            if self.field_locked(name, fid):
                raise StoreError("locked")
        for v in sets.values():
            if any(ord(c) < 32 or ord(c) == 127 for c in v):
                raise StoreError("bad_value")

        # Address format validation (only reachable for stash/komga)
        if address is not None:
            addr_stripped: str = address.strip()
            parsed = urlparse(addr_stripped)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
            ):
                raise StoreError("bad_address")
            address = addr_stripped.rstrip("/")

        # Master key required for explicit secret operations
        if (sets or clears) and not self.can_store():
            raise StoreError("no_master_key")

        addr_key: str = f"connections.{name}.address"
        secret_key: str = f"connections.{name}.secret"

        secret_changed: bool = False

        # Address change: invalidate stored secret unless a new one is supplied
        if address is not None:
            current_addr: str = self.address(name)
            if address != current_addr:
                if not (secret is not None and secret != ""):
                    self._delete(secret_key)
                    secret_changed = True
                self._write(addr_key, address)
                logger.info("address for %s changed", name)

        # Apply fields
        for fid in clears:
            if fid not in sets:
                self._delete(self._skey(name, fid))
                secret_changed = True
        for fid, value in sets.items():
            token: str = self._fernet().encrypt(value.encode()).decode()
            self._write(self._skey(name, fid), token)
            secret_changed = True

        if secret_changed:
            logs.register_connection_secrets(self.field_values(name))
            logger.info("key for %s changed", name)
