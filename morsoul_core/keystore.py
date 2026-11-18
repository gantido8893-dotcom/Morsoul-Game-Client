"""OS credential store for the local database encryption key."""

from __future__ import annotations

import secrets
from typing import Protocol

import keyring

SERVICE = "morsoul"
NAME = "db-key"


class KeyUnavailableError(Exception):
    """Raised when the database key cannot be read or used."""


class KeyStore(Protocol):
    def get(self) -> str | None: ...
    def set(self, hex_key: str) -> None: ...
    def clear(self) -> None: ...


class KeyringStore:
    def get(self) -> str | None:
        try:
            return keyring.get_password(SERVICE, NAME)
        except Exception as exc:  # keyring backend failures
            raise KeyUnavailableError("Cannot read the database key from the credential store") from exc

    def set(self, hex_key: str) -> None:
        try:
            keyring.set_password(SERVICE, NAME, hex_key)
        except Exception as exc:
            raise KeyUnavailableError("Cannot store the database key in the credential store") from exc

    def clear(self) -> None:
        try:
            keyring.delete_password(SERVICE, NAME)
        except keyring.errors.PasswordDeleteError:
            return
        except Exception as exc:
            raise KeyUnavailableError("Cannot clear the database key") from exc


class MemoryKeyStore:
    """In-memory store for tests only."""

    def __init__(self, hex_key: str | None = None) -> None:
        self._key = hex_key

    def get(self) -> str | None:
        return self._key

    def set(self, hex_key: str) -> None:
        self._key = hex_key

    def clear(self) -> None:
        self._key = None


_default_store: KeyStore = KeyringStore()


def set_keystore(store: KeyStore) -> None:
    global _default_store
    _default_store = store


def get_or_create_key(store: KeyStore | None = None) -> bytes:
    """Return a 32-byte key, creating and storing a new one if needed. Never logged."""
    ks = store or _default_store
    existing = ks.get()
    if existing is not None:
        try:
            raw = bytes.fromhex(existing)
        except ValueError as exc:
            raise KeyUnavailableError("Stored database key is not valid hex") from exc
        if len(raw) != 32:
            raise KeyUnavailableError("Stored database key has the wrong length")
        return raw
    raw = secrets.token_bytes(32)
    ks.set(raw.hex())
    return raw
