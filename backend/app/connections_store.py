"""Encrypted per-connection address and secret store."""

from __future__ import annotations

import logging
from typing import Literal
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from app.config import Settings
from app.db import connect

logger = logging.getLogger("pearlie")

NAMES: tuple[str, ...] = ("stash", "komga", "danbooru", "gelbooru", "rule34", "nhentai")

FIXED_HOSTS: dict[str, str] = {
    "danbooru": "https://danbooru.donmai.us",
    "gelbooru": "https://gelbooru.com",
    "rule34": "https://api.rule34.xyz",
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

    def can_store(self) -> bool:
        key: str = self._settings.secret_key.get_secret_value()
        if not key:
            return False
        try:
            Fernet(key)
        except (ValueError, TypeError):
            return False
        return True

    def _fernet(self) -> Fernet:
        return Fernet(self._settings.secret_key.get_secret_value())

    # -- env lock detection --

    def env_locked(self, name: str) -> dict[str, bool]:
        addr_attr, secret_attr = ENV_FIELDS.get(name, ("", ""))
        locked: dict[str, bool] = {"address": False, "secret": False}
        if addr_attr and addr_attr in self._settings.model_fields_set:
            val: object = getattr(self._settings, addr_attr)
            if isinstance(val, SecretStr):
                locked["address"] = bool(val.get_secret_value())
            else:
                locked["address"] = bool(val)
        if secret_attr and secret_attr in self._settings.model_fields_set:
            val = getattr(self._settings, secret_attr)
            if isinstance(val, SecretStr):
                locked["secret"] = bool(val.get_secret_value())
            else:
                locked["secret"] = bool(val)
        return locked

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
        locked = self.env_locked(name)
        if locked["secret"]:
            return "set"
        stored: str | None = self._read(f"connections.{name}.secret")
        return "set" if stored is not None else "missing"

    def effective_secret(self, name: str) -> str:
        locked = self.env_locked(name)
        if locked["secret"]:
            _, secret_attr = ENV_FIELDS[name]
            val: object = getattr(self._settings, secret_attr)
            if isinstance(val, SecretStr):
                return val.get_secret_value()
            return str(val) if val else ""
        stored: str | None = self._read(f"connections.{name}.secret")
        if stored is None or not self.can_store():
            return ""
        try:
            return self._fernet().decrypt(stored.encode()).decode()
        except InvalidToken:
            logger.warning("stored key for %s cannot be decrypted", name)
            return ""

    # -- mutation --

    def save(
        self,
        name: str,
        address: str | None,
        secret: str | None,
        clear_secret: bool,
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
        if (secret is not None or clear_secret) and not self.can_store():
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

        # Apply secret
        if clear_secret:
            self._delete(secret_key)
            secret_changed = True
        elif secret is not None and secret != "":
            token: str = self._fernet().encrypt(secret.encode()).decode()
            self._write(secret_key, token)
            secret_changed = True

        if secret_changed:
            logger.info("key for %s changed", name)
