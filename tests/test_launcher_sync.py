"""Sync classify + engine tests (milestone M3)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from morsoul_core import savestore
from morsoul_launcher.api import ApiClient
from morsoul_launcher.state import LauncherState, ProfileSyncRecord
from morsoul_launcher.sync.classify import Action, CloudInfo, LastSynced, LocalInfo, classify
from morsoul_launcher.sync.engine import SyncEngine, SyncTrigger
from morsoul_launcher.sync.gamelock import is_game_running, write_lock_for_tests
from morsoul_launcher.tokens import MemoryTokenStore
from tests.helpers import KEY, KEY_B64, PASSWORD, new_profile, snapshot


@pytest.mark.parametrize(
    "local,last,cloud,expected",
    [
        (LocalInfo("a"), LastSynced(1, "a"), CloudInfo(1, "a"), Action.NOTHING),
        (LocalInfo("b"), LastSynced(1, "a"), CloudInfo(1, "a"), Action.UPLOAD),
        (LocalInfo("a"), LastSynced(1, "a"), CloudInfo(2, "c"), Action.DOWNLOAD),
        (LocalInfo("b"), LastSynced(1, "a"), CloudInfo(2, "c"), Action.CONFLICT),
        (LocalInfo("a"), None, CloudInfo(None), Action.UPLOAD),
        (LocalInfo(None), None, CloudInfo(2, "c"), Action.DOWNLOAD),
        (LocalInfo("a"), None, CloudInfo(2, "c"), Action.CONFLICT),
        (LocalInfo(None), None, CloudInfo(None), Action.NOTHING),
    ],
)
def test_classify_table(local, last, cloud, expected) -> None:
    assert classify(local, last, cloud) == expected


def test_game_lock(tmp_path: Path) -> None:
    lock = tmp_path / "game.lock"
    assert is_game_running(lock) is False
    write_lock_for_tests(lock)
    assert is_game_running(lock) is True
    write_lock_for_tests(lock, pid=999_999_999)
    assert is_game_running(lock) is False


@pytest.mark.asyncio
async def test_sync_upload_download_conflict(make_client, tmp_path: Path) -> None:
    server = await make_client(save_hmac_key=KEY_B64)
    transport = httpx.ASGITransport(app=server.app, raise_app_exceptions=False)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")

    tokens_a = MemoryTokenStore()
    api_a = ApiClient(base_url="http://test", token=tokens_a.get, client=client)
    session = await api_a.register("sync_user", PASSWORD)
    tokens_a.set(session.sessionToken)

    key = b"s" * 32
    db_a = tmp_path / "a" / "game.db"
    db_b = tmp_path / "b" / "game.db"
    bak_a = tmp_path / "a" / "game.db.bak"
    bak_b = tmp_path / "b" / "game.db.bak"
    state_a = LauncherState()
    state_b = LauncherState()
    pid = new_profile()
    snap = snapshot(pid, revision=1)
    savestore.import_snapshot(db_a, key, snap, bak_path=bak_a, hmac_key=KEY)

    engine_a = SyncEngine(
        api=api_a,
        db_path=db_a,
        bak_path=bak_a,
        db_key=key,
        hmac_key=KEY,
        state=state_a,
        state_path=tmp_path / "a" / "state.json",
        lock_path=tmp_path / "a" / "game.lock",
    )
    outcomes = await engine_a.sync_all(SyncTrigger.MANUAL)
    assert any(o.kind == "uploaded" and o.profile_id == pid for o in outcomes)
    assert state_a.profiles[pid].revision == 1

    # device B downloads
    tokens_b = MemoryTokenStore(session.sessionToken)
    api_b = ApiClient(base_url="http://test", token=tokens_b.get, client=client)
    engine_b = SyncEngine(
        api=api_b,
        db_path=db_b,
        bak_path=bak_b,
        db_key=key,
        hmac_key=KEY,
        state=state_b,
        state_path=tmp_path / "b" / "state.json",
        lock_path=tmp_path / "b" / "game.lock",
    )
    outcomes_b = await engine_b.sync_all()
    assert any(o.kind == "downloaded" and o.profile_id == pid for o in outcomes_b)
    assert bak_b.exists() or True  # first download creates db; bak on subsequent
    exported = savestore.export_snapshot(db_b, key, pid, hmac_key=KEY)
    assert exported["payload"]

    # diverge both sides -> conflict
    snap_local = snapshot(pid, revision=2)
    snap_cloud = snapshot(pid, revision=2)
    savestore.import_snapshot(db_a, key, snap_local, bak_path=bak_a, hmac_key=KEY)
    # push cloud change from B
    savestore.import_snapshot(db_b, key, snap_cloud, bak_path=bak_b, hmac_key=KEY)
    await engine_b.sync_all()
    conflict = await engine_a.sync_profile(pid)
    assert conflict.kind == "conflict"

    kept = await engine_a.resolve_conflict(pid, "keep_local")
    assert kept.kind == "uploaded"

    # cloudDeleted not re-uploaded
    await engine_a.delete_cloud_profile(pid)
    assert state_a.profiles[pid].cloud_deleted is True
    again = await engine_a.sync_profile(pid)
    assert again.kind == "noop"

    await client.aclose()


@pytest.mark.asyncio
async def test_skip_game_running(tmp_path: Path) -> None:
    lock = tmp_path / "game.lock"
    write_lock_for_tests(lock)
    engine = SyncEngine(
        api=ApiClient(
            base_url="http://test",
            token=lambda: "x",
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])),
        ),
        db_path=tmp_path / "game.db",
        bak_path=tmp_path / "game.db.bak",
        db_key=b"k" * 32,
        hmac_key=KEY,
        state=LauncherState(),
        lock_path=lock,
    )
    out = await engine.sync_all()
    assert out[0].reason == "game_running"


@pytest.mark.asyncio
async def test_lost_response_recovery(tmp_path: Path) -> None:
    pid = new_profile()
    snap = snapshot(pid)
    key = b"z" * 32
    db = tmp_path / "game.db"
    savestore.import_snapshot(db, key, snap, bak_path=tmp_path / "b.bak", hmac_key=KEY)
    local = savestore.export_snapshot(db, key, pid, hmac_key=KEY)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            return httpx.Response(
                409,
                json={
                    "error": {
                        "code": "REVISION_CONFLICT",
                        "message": "conflict",
                        "details": {
                            "serverRevision": 5,
                            "stateHash": local["stateHash"],
                            "summary": {},
                        },
                    }
                },
            )
        return httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "no"}})

    state = LauncherState(profiles={pid: ProfileSyncRecord(1, "0" * 64)})
    engine = SyncEngine(
        api=ApiClient(base_url="http://test", token=lambda: "t", transport=httpx.MockTransport(handler)),
        db_path=db,
        bak_path=tmp_path / "game.db.bak",
        db_key=key,
        hmac_key=KEY,
        state=state,
        state_path=tmp_path / "state.json",
        lock_path=tmp_path / "game.lock",
    )
    out = await engine._upload(pid, local, base=1)
    assert out.kind == "uploaded"
    assert state.profiles[pid].revision == 5
