"""Tests for morsoul_core paths, keystore and savestore (milestone M1)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from morsoul_core import paths, savestore
from morsoul_core.keystore import KeyUnavailableError, MemoryKeyStore, get_or_create_key, set_keystore
from tests.helpers import KEY, new_profile, snapshot


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("MORSOUL_DATA_DIR", str(tmp_path / "data"))
    return paths.data_dir()


@pytest.fixture
def mem_keys() -> Iterator[MemoryKeyStore]:
    store = MemoryKeyStore()
    set_keystore(store)
    yield store
    set_keystore(MemoryKeyStore())  # reset


def test_paths(data_root: Path) -> None:
    assert paths.game_db_path().parent == data_root
    assert paths.game_db_bak_path().name == "game.db.bak"
    assert paths.game_lock_path().name == "game.lock"
    assert paths.stats_cache_path().name == "stats-cache.json"
    assert paths.launcher_state_path().parent.name == "launcher"


def test_get_or_create_key(mem_keys: MemoryKeyStore) -> None:
    k1 = get_or_create_key(mem_keys)
    k2 = get_or_create_key(mem_keys)
    assert k1 == k2
    assert len(k1) == 32
    assert mem_keys.get() == k1.hex()


def test_export_import_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "game.db"
    bak = tmp_path / "game.db.bak"
    key = b"a" * 32
    pid = new_profile()
    snap = snapshot(pid, revision=2, playtime=5000, reputation=42, displayName="Caelan")
    # richer payload
    snap = snapshot(
        pid,
        revision=3,
        playtime=9000,
        reputation=100,
        displayName="Caelan",
        caseProgress={
            "case_01": {
                "status": "completed",
                "progressVersion": 1,
                "objectiveID": None,
                "warrantGranted": True,
                "failedAttempts": 1,
                "hintTier": 2,
                "deductionSolved": True,
                "interrogationResult": "success",
                "completedAt": 1700000100,
            }
        },
        evidence={"clue_017": {"caseID": "case_01", "collectedAt": 1000, "via": "scan"}},
        deductionLinks={"case_01": [["clue_017", "clue_021"]]},
        unlocks={"tool": ["golem_eye"], "sector": ["sector_docks"], "case": []},
        runicLogs={"1": {"foundAt": 10, "decryptedAt": 20}, "2": {"foundAt": None, "decryptedAt": None}},
        caseResults={
            "case_01": {
                "conclusionID": "conc_a",
                "correct": True,
                "flawed": False,
                "strikes": 0,
                "attempts": 1,
                "completedAt": 1700000100,
            }
        },
        dialogue={
            "npcs": {"npc_a": {"stage": 1, "variant": "default", "flags": []}},
            "statementsHeard": ["s1"],
        },
        board={"nodes": {"clue_017": {"x": 0.5, "y": 0.25}}},
        puzzles={"puz_1": {"solved": True, "attempts": 2}},
        notes=[{"entryID": "n1", "title": "Note", "content": "hello", "linkedClueID": "clue_017"}],
        checkpoint={"room": "lab"},
    )
    savestore.import_snapshot(db, key, snap, bak_path=bak, hmac_key=KEY)
    out = savestore.export_snapshot(db, key, pid, hmac_key=KEY)
    # second import into the same db must write a backup first
    savestore.import_snapshot(db, key, out, bak_path=bak, hmac_key=KEY)
    assert bak.exists()
    # re-import into a fresh db and export again
    db2 = tmp_path / "game2.db"
    savestore.import_snapshot(db2, key, out, bak_path=tmp_path / "game2.db.bak", hmac_key=KEY)
    out2 = savestore.export_snapshot(db2, key, pid, hmac_key=KEY)
    assert out == out2
    assert out["profileID"] == pid
    assert out["payload"]["displayName"] == "Caelan"
    assert out["payload"]["reputation"] == 100
    assert out["payload"]["caseProgress"]["case_01"]["warrantGranted"] is True
    assert out["payload"]["deductionLinks"]["case_01"] == [["clue_017", "clue_021"]]


def test_wrong_key_keeps_file(tmp_path: Path) -> None:
    db = tmp_path / "game.db"
    key = b"b" * 32
    wrong = b"c" * 32
    pid = new_profile()
    snap = snapshot(pid)
    savestore.import_snapshot(db, key, snap, bak_path=tmp_path / "b.bak", hmac_key=KEY)
    before = db.read_bytes()
    with pytest.raises(KeyUnavailableError):
        savestore.open_db(db, wrong)
    assert db.read_bytes() == before
    # still openable with the right key
    with savestore.connect(db, key) as conn:
        n = conn.execute("SELECT count(*) FROM profiles").fetchone()[0]
    assert n == 1


def test_tampered_page_detected(tmp_path: Path) -> None:
    db = tmp_path / "game.db"
    key = b"d" * 32
    pid = new_profile()
    savestore.import_snapshot(db, key, snapshot(pid), bak_path=tmp_path / "t.bak", hmac_key=KEY)
    # drop WAL sidecars so only the encrypted main file remains
    for side in (tmp_path / "game.db-wal", tmp_path / "game.db-shm"):
        if side.exists():
            side.unlink()
    raw = bytearray(db.read_bytes())
    assert len(raw) > 200
    # corrupt an interior page of the ciphertext
    for i in range(100, 200):
        raw[i] ^= 0xA5
    db.write_bytes(bytes(raw))
    with pytest.raises((KeyUnavailableError, Exception)):
        with savestore.connect(db, key) as conn:
            conn.execute("SELECT count(*) FROM profiles").fetchone()


def test_list_and_delete(tmp_path: Path) -> None:
    db = tmp_path / "game.db"
    key = b"e" * 32
    p1, p2 = new_profile(), new_profile()
    savestore.import_snapshot(
        db, key, snapshot(p1, displayName="A"), bak_path=tmp_path / "x.bak", hmac_key=KEY
    )
    savestore.import_snapshot(
        db, key, snapshot(p2, displayName="B"), bak_path=tmp_path / "x.bak", hmac_key=KEY
    )
    listed = savestore.list_profiles(db, key)
    assert {r["profile_id"] for r in listed} == {p1, p2}
    savestore.delete_profile(db, key, p1)
    listed = savestore.list_profiles(db, key)
    assert [r["profile_id"] for r in listed] == [p2]


def test_backup_api(tmp_path: Path) -> None:
    db = tmp_path / "game.db"
    bak = tmp_path / "game.db.bak"
    key = b"f" * 32
    pid = str(uuid.uuid4())
    savestore.import_snapshot(db, key, snapshot(pid), bak_path=tmp_path / "first.bak", hmac_key=KEY)
    savestore.backup_db(db, key, bak)
    assert bak.exists()
    out = savestore.export_snapshot(bak, key, pid, hmac_key=KEY)
    assert out["profileID"] == pid
