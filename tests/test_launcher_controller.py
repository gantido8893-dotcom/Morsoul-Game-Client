"""Controller tests with a fake ApiClient (milestone M5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from morsoul_launcher.appstate import AuthKind
from morsoul_launcher.config import LauncherSettings
from morsoul_launcher.controller import LauncherController
from morsoul_launcher.strings import friendly_error
from morsoul_launcher.tokens import MemoryTokenStore


class FakeApi:
    def __init__(self) -> None:
        self.fail_login = False
        self.token_sessions: dict[str, dict[str, Any]] = {}

    async def login(self, username: str, password: str) -> Any:
        from morsoul_launcher.api import ApiError, AuthSession

        if self.fail_login:
            raise ApiError(401, "INVALID_CREDENTIALS", "bad")
        return AuthSession(
            userID="u1", username=username, sessionToken="tok-1", expiresAt="2099-01-01T00:00:00Z"
        )

    async def register(self, username: str, password: str, email: str | None = None) -> Any:
        from morsoul_launcher.api import AuthSession

        return AuthSession(
            userID="u2", username=username, sessionToken="tok-2", expiresAt="2099-01-01T00:00:00Z"
        )

    async def me(self) -> Any:
        from morsoul_launcher.api import AuthError

        raise AuthError(401, "INVALID_SESSION", "gone")

    async def logout(self) -> None:
        return None

    async def logout_all(self) -> None:
        return None

    async def change_password(self, current: str, new: str) -> dict[str, Any]:
        return {"sessionToken": "tok-new", "expiresAt": "2099-01-01T00:00:00Z"}

    async def list_saves(self) -> list:
        return []

    async def updates_manifest(self) -> dict:
        raise Exception("no manifest")

    async def stats(self) -> dict:
        return {"cases": []}


@pytest.fixture
def controller(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LauncherController:
    monkeypatch.setenv("MORSOUL_DATA_DIR", str(tmp_path))
    from tests.helpers import KEY_B64

    settings = LauncherSettings(
        _env_file=None, save_hmac_key=KEY_B64, default_server_url="http://127.0.0.1:8080"
    )
    return LauncherController(
        settings,
        tokens=MemoryTokenStore(),
        api=FakeApi(),  # type: ignore[arg-type]
        state_path=tmp_path / "launcher-state.json",
        db_path=tmp_path / "game.db",
        bak_path=tmp_path / "game.db.bak",
        lock_path=tmp_path / "game.lock",
        db_key=b"k" * 32,
    )


@pytest.mark.asyncio
async def test_sign_in_and_offline(controller: LauncherController) -> None:
    r = await controller.sign_in("alice", "password12")
    assert r.ok
    assert controller.state.auth.kind == AuthKind.SIGNED_IN
    assert controller.tokens.get() == "tok-1"

    await controller.continue_offline()
    assert controller.state.auth.kind == AuthKind.OFFLINE_MODE


@pytest.mark.asyncio
async def test_sign_in_failure(controller: LauncherController) -> None:
    controller.api.fail_login = True  # type: ignore[attr-defined]
    r = await controller.sign_in("alice", "bad")
    assert not r.ok
    assert r.code == "INVALID_CREDENTIALS"
    assert controller.state.auth.kind == AuthKind.SIGNED_OUT


@pytest.mark.asyncio
async def test_change_password_replaces_token(controller: LauncherController) -> None:
    await controller.sign_in("alice", "password12")
    r = await controller.change_password("password12", "password99")
    assert r.ok
    assert controller.tokens.get() == "tok-new"


def test_friendly_errors() -> None:
    assert "Wrong username" in friendly_error("INVALID_CREDENTIALS")
    assert "wait 9" in friendly_error("RATE_LIMITED", retry_after=9)
    assert "sign in again" in friendly_error("INVALID_SESSION").lower() or "Please sign in" in friendly_error(
        "INVALID_SESSION"
    )
