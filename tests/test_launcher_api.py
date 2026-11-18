"""ApiClient, tokens and launcher state (milestone M2)."""

from __future__ import annotations

import httpx
import pytest

from morsoul_launcher.api import (
    ApiClient,
    ApiError,
    AuthError,
    ConflictError,
    RateLimitedError,
)
from morsoul_launcher.state import LauncherState, ProfileSyncRecord, load_launcher_state, save_launcher_state
from morsoul_launcher.tokens import MemoryTokenStore
from tests.helpers import KEY_B64, PASSWORD, new_profile, snapshot


def test_launcher_state_atomic(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MORSOUL_DATA_DIR", str(tmp_path))
    path = tmp_path / "launcher" / "launcher-state.json"
    state = LauncherState(
        server_url="http://127.0.0.1:8080",
        installed_app_version="0.1.0",
        profiles={"p1": ProfileSyncRecord(revision=2, state_hash="a" * 64, cloud_deleted=True)},
    )
    save_launcher_state(state, path)
    loaded = load_launcher_state(path)
    assert loaded.server_url == "http://127.0.0.1:8080"
    assert loaded.profiles["p1"].cloud_deleted is True
    assert loaded.profiles["p1"].revision == 2


@pytest.mark.asyncio
async def test_api_login_and_errors_mock() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(
                200,
                json={
                    "userID": "u1",
                    "username": "alice",
                    "sessionToken": "tok",
                    "expiresAt": "2099-01-01T00:00:00Z",
                },
            )
        if request.url.path.endswith("/auth/me"):
            return httpx.Response(401, json={"error": {"code": "INVALID_SESSION", "message": "no"}})
        if request.url.path.endswith("/saves/p1"):
            if request.method == "PUT":
                return httpx.Response(
                    409,
                    json={
                        "error": {
                            "code": "REVISION_CONFLICT",
                            "message": "conflict",
                            "details": {
                                "serverRevision": 3,
                                "stateHash": "b" * 64,
                                "summary": {"casesCompleted": 1},
                            },
                        }
                    },
                )
        if request.url.path.endswith("/saves"):
            return httpx.Response(
                429,
                headers={"Retry-After": "7"},
                json={"error": {"code": "RATE_LIMITED", "message": "slow down"}},
            )
        return httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "no"}})

    transport = httpx.MockTransport(handler)
    tokens = MemoryTokenStore()
    async with ApiClient(base_url="http://test", token=tokens.get, transport=transport) as api:
        session = await api.login("alice", "password12")
        tokens.set(session.sessionToken)
        assert session.username == "alice"
        with pytest.raises(AuthError):
            await api.me()
        with pytest.raises(ConflictError) as ce:
            await api.put_save("p1", 1, {"profileID": "p1"})
        assert ce.value.server_revision == 3
        with pytest.raises(RateLimitedError) as re:
            await api.list_saves()
        assert re.value.retry_after == 7


@pytest.mark.asyncio
async def test_get_retries_put_does_not() -> None:
    counts = {"GET": 0, "PUT": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        method = request.method
        counts[method] = counts.get(method, 0) + 1
        if method == "GET":
            if counts["GET"] < 3:
                return httpx.Response(503, json={"error": {"code": "UNAVAILABLE", "message": "busy"}})
            return httpx.Response(200, json=[])
        return httpx.Response(503, json={"error": {"code": "UNAVAILABLE", "message": "busy"}})

    transport = httpx.MockTransport(handler)
    async with ApiClient(base_url="http://test", token=lambda: "t", transport=transport) as api:
        assert await api.list_saves() == []
        assert counts["GET"] == 3
        with pytest.raises(ApiError):
            await api.put_save("p1", 0, {})
        assert counts["PUT"] == 1


@pytest.mark.asyncio
async def test_network_refresh_once() -> None:
    urls: list[str] = []
    state = {"base": "http://old"}

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        if "old" in str(request.url):
            raise httpx.ConnectError("down")
        return httpx.Response(200, json={"status": "ok"})

    async def refresh() -> str | None:
        state["base"] = "http://new"
        return state["base"]

    transport = httpx.MockTransport(handler)
    async with ApiClient(
        base_url=lambda: state["base"],
        token=lambda: None,
        refresh_server_config=refresh,
        transport=transport,
    ) as api:
        data = await api.health()
        assert data["status"] == "ok"
        assert any("new" in u for u in urls)


@pytest.mark.asyncio
async def test_integration_login_and_save(make_client) -> None:
    server = await make_client(save_hmac_key=KEY_B64)
    transport = httpx.ASGITransport(app=server.app, raise_app_exceptions=False)
    tokens = MemoryTokenStore()

    async with ApiClient(
        base_url="http://test",
        token=tokens.get,
        transport=transport,
        client=httpx.AsyncClient(transport=transport, base_url="http://test"),
    ) as api:
        # ApiClient builds absolute URLs from base_url provider; point it at ASGI via custom client
        api._base_url = lambda: "http://test"
        session = await api.register("player_one", PASSWORD)
        tokens.set(session.sessionToken)
        me = await api.me()
        assert me.username == "player_one"
        pid = new_profile()
        snap = snapshot(pid)
        result = await api.put_save(pid, 0, snap)
        assert result.revision == 1
        listed = await api.list_saves()
        assert listed[0].profileID == pid
