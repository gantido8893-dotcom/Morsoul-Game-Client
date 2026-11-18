"""Session token store. Never write the token to a plain file."""

from __future__ import annotations

from typing import Protocol

import keyring

SERVICE = "morsoul"
NAME = "session-token"


class TokenStore(Protocol):
    def get(self) -> str | None: ...
    def set(self, token: str) -> None: ...
    def clear(self) -> None: ...


class KeyringTokenStore:
    def get(self) -> str | None:
        try:
            return keyring.get_password(SERVICE, NAME)
        except Exception:
            return None

    def set(self, token: str) -> None:
        try:
            keyring.set_password(SERVICE, NAME, token)
        except Exception:
            pass

    def clear(self) -> None:
        try:
            keyring.delete_password(SERVICE, NAME)
        except Exception:
            return


class MemoryTokenStore:
    """In-memory store for tests only."""

    def __init__(self, token: str | None = None) -> None:
        self._token = token

    def get(self) -> str | None:
        return self._token

    def set(self, token: str) -> None:
        self._token = token

    def clear(self) -> None:
        self._token = None
