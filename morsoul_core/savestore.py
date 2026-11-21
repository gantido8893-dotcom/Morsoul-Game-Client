"""Encrypted local save database (SQLCipher). Only module that opens game.db."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from morsoul_core import integrity
from morsoul_core.keystore import KeyUnavailableError
from morsoul_core.snapshot import Snapshot

try:
    import sqlcipher3.dbapi2 as sqlcipher
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("sqlcipher3-wheels is required; do not fall back to unencrypted SQLite") from exc

# DDL derived from SQLite-Schema ERD
SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY NOT NULL,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profiles (
  profile_id TEXT PRIMARY KEY NOT NULL,
  display_name TEXT NOT NULL,
  age INTEGER,
  created_at INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS profile_state (
  profile_id TEXT PRIMARY KEY NOT NULL REFERENCES profiles(profile_id) ON DELETE CASCADE,
  revision INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  playtime INTEGER NOT NULL DEFAULT 0,
  reputation INTEGER NOT NULL DEFAULT 0,
  current_case_id TEXT,
  ending TEXT,
  focus_energy REAL NOT NULL DEFAULT 0,
  focus_as_of_playtime INTEGER NOT NULL DEFAULT 0,
  dialogue_json TEXT NOT NULL DEFAULT '{}',
  board_json TEXT NOT NULL DEFAULT '{}',
  puzzles_json TEXT NOT NULL DEFAULT '{}',
  notes_json TEXT NOT NULL DEFAULT '[]',
  checkpoint_json TEXT
);

CREATE TABLE IF NOT EXISTS case_progress (
  profile_id TEXT NOT NULL REFERENCES profiles(profile_id) ON DELETE CASCADE,
  case_id TEXT NOT NULL,
  status TEXT NOT NULL,
  progress_version INTEGER NOT NULL DEFAULT 1,
  objective_id TEXT,
  warrant_granted INTEGER NOT NULL DEFAULT 0,
  failed_attempts INTEGER NOT NULL DEFAULT 0,
  hint_tier INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER,
  PRIMARY KEY (profile_id, case_id)
);

CREATE TABLE IF NOT EXISTS clues_found (
  profile_id TEXT NOT NULL REFERENCES profiles(profile_id) ON DELETE CASCADE,
  case_id TEXT NOT NULL,
  clue_id TEXT NOT NULL,
  collected_at INTEGER NOT NULL,
  via TEXT NOT NULL,
  PRIMARY KEY (profile_id, case_id, clue_id)
);

CREATE TABLE IF NOT EXISTS deduction_links (
  profile_id TEXT NOT NULL REFERENCES profiles(profile_id) ON DELETE CASCADE,
  case_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  target_id TEXT NOT NULL,
  PRIMARY KEY (profile_id, case_id, source_id, target_id)
);

CREATE TABLE IF NOT EXISTS case_results (
  profile_id TEXT NOT NULL REFERENCES profiles(profile_id) ON DELETE CASCADE,
  case_id TEXT NOT NULL,
  conclusion_id TEXT NOT NULL DEFAULT '',
  correct INTEGER NOT NULL DEFAULT 1,
  flawed INTEGER NOT NULL DEFAULT 0,
  strikes INTEGER NOT NULL DEFAULT 0,
  attempts INTEGER NOT NULL DEFAULT 1,
  completed_at INTEGER NOT NULL,
  PRIMARY KEY (profile_id, case_id)
);
"""


def _pragma_key(key: bytes) -> str:
    if len(key) != 32:
        raise KeyUnavailableError("Database key must be 32 bytes")
    return f"x'{key.hex()}'"


def _connect_raw(path: Path, key: bytes, *, read_only: bool = False) -> sqlcipher.Connection:
    if read_only:
        uri = f"file:{path.as_posix()}?mode=ro"
        conn = sqlcipher.connect(uri, uri=True)
    else:
        conn = sqlcipher.connect(str(path))

    conn.execute(f'PRAGMA key = "{_pragma_key(key)}"')
    try:
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except sqlcipher.DatabaseError as exc:
        conn.close()
        raise KeyUnavailableError("Wrong or missing database key; the save file was not changed") from exc

    cipher_ver = conn.execute("PRAGMA cipher_version").fetchone()
    if not cipher_ver or not cipher_ver[0]:
        conn.close()
        raise RuntimeError("SQLCipher is not available (PRAGMA cipher_version empty)")
    try:
        ok = conn.execute("SELECT json_valid('{}')").fetchone()
        if not ok or not ok[0]:
            raise RuntimeError("SQLite JSON1 is not available")
    except sqlcipher.DatabaseError as exc:
        conn.close()
        raise RuntimeError("SQLite JSON1 is not available") from exc

    conn.execute("PRAGMA foreign_keys = ON")
    if not read_only:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = FULL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlcipher.Row
    return conn


def open_db(path: Path | str, key: bytes) -> sqlcipher.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect_raw(path, key, read_only=False)
    _migrate(conn)
    return conn


def _migrate(conn: sqlcipher.Connection) -> None:
    row = conn.execute("PRAGMA user_version").fetchone()
    version = int(row[0]) if row else 0
    if version == 0:
        conn.executescript(DDL)
        conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?), (?, ?)",
            ("schemaVersion", "1", "contentVersion", "1"),
        )
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    elif version > SCHEMA_VERSION:
        raise RuntimeError(f"Database schema version {version} is newer than this app ({SCHEMA_VERSION})")


@contextmanager
def connect(path: Path | str, key: bytes, *, read_only: bool = False) -> Iterator[sqlcipher.Connection]:
    path = Path(path)
    if read_only:
        if not path.exists():
            raise FileNotFoundError(path)
        conn = _connect_raw(path, key, read_only=True)
    else:
        conn = open_db(path, key)
    try:
        yield conn
    finally:
        conn.close()


def backup_db(path: Path | str, key: bytes, bak_path: Path | str) -> None:
    path = Path(path)
    bak_path = Path(bak_path)
    if not path.exists():
        return
    with connect(path, key) as src:
        bak_path.parent.mkdir(parents=True, exist_ok=True)
        if bak_path.exists():
            bak_path.unlink()
        dest = _connect_raw(bak_path, key, read_only=False)
        try:
            src.backup(dest)
            dest.commit()
        finally:
            dest.close()


def list_profiles(path: Path | str, key: bytes) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    with connect(path, key, read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT p.profile_id, p.display_name, p.created_at, s.revision, s.updated_at, s.playtime,
                   s.reputation, s.current_case_id, s.ending,
                   (SELECT COUNT(*) FROM case_results cr WHERE cr.profile_id = p.profile_id) AS cases_completed,
                   0 AS runic_logs
            FROM profiles p
            LEFT JOIN profile_state s ON s.profile_id = p.profile_id
            ORDER BY COALESCE(s.updated_at, 0) DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def delete_profile(path: Path | str, key: bytes, profile_id: str) -> None:
    with connect(path, key) as conn:
        conn.execute("DELETE FROM profiles WHERE profile_id = ?", (profile_id,))
        conn.commit()


def _meta(conn: sqlcipher.Connection) -> dict[str, str]:
    try:
        return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}
    except Exception:
        return {}


def export_snapshot(
    path: Path | str,
    key: bytes,
    profile_id: str,
    *,
    app_version: str | None = "0.1.0",
    hmac_key: bytes,
) -> dict:
    path = Path(path)
    with connect(path, key, read_only=True) as conn:
        prof = conn.execute(
            "SELECT profile_id, display_name FROM profiles WHERE profile_id = ?", (profile_id,)
        ).fetchone()
        if prof is None:
            raise KeyError(f"profile not found: {profile_id}")
        state = conn.execute("SELECT * FROM profile_state WHERE profile_id = ?", (profile_id,)).fetchone()
        if state is None:
            raise KeyError(f"profile state not found: {profile_id}")
        meta = _meta(conn)
        ending_val = state["ending"] if state["ending"] in {"bad", "normal", "true"} else None
        current_case_val = state["current_case_id"] or None

        case_progress: dict[str, Any] = {}
        for r in conn.execute("SELECT * FROM case_progress WHERE profile_id = ?", (profile_id,)):
            case_progress[r["case_id"]] = {
                "status": r["status"],
                "progressVersion": r["progress_version"],
                "objectiveID": r["objective_id"],
                "warrantGranted": bool(r["warrant_granted"]),
                "failedAttempts": r["failed_attempts"],
                "hintTier": r["hint_tier"],
                "deductionSolved": False,
                "interrogationResult": None,
                "completedAt": r["updated_at"] if r["status"] == "completed" else None,
            }

        evidence: dict[str, Any] = {}
        for r in conn.execute("SELECT * FROM clues_found WHERE profile_id = ?", (profile_id,)):
            evidence[r["clue_id"]] = {
                "caseID": r["case_id"],
                "collectedAt": r["collected_at"],
                "via": r["via"],
            }

        if current_case_val and current_case_val not in case_progress:
            case_progress[current_case_val] = {
                "status": "in_progress",
                "progressVersion": 1,
                "objectiveID": None,
                "warrantGranted": False,
                "failedAttempts": 0,
                "hintTier": 0,
                "deductionSolved": False,
                "interrogationResult": None,
                "completedAt": None,
            }

        deduction_links: dict[str, list[list[str]]] = {}
        for r in conn.execute("SELECT * FROM deduction_links WHERE profile_id = ?", (profile_id,)):
            deduction_links.setdefault(r["case_id"], []).append([r["source_id"], r["target_id"]])

        unlocks: dict[str, list[str]] = {"tool": [], "sector": [], "case": []}
        runic_logs: dict[str, Any] = {}

        case_results: dict[str, Any] = {}
        for r in conn.execute("SELECT * FROM case_results WHERE profile_id = ?", (profile_id,)):
            case_results[r["case_id"]] = {
                "conclusionID": r["conclusion_id"],
                "correct": bool(r["correct"]),
                "flawed": bool(r["flawed"]),
                "strikes": r["strikes"],
                "attempts": r["attempts"],
                "completedAt": r["completed_at"],
            }

        dialogue = json.loads(state["dialogue_json"] or "{}")
        board = json.loads(state["board_json"] or "{}")
        puzzles = json.loads(state["puzzles_json"] or "{}")
        notes = json.loads(state["notes_json"] or "[]")
        checkpoint = None
        if state["checkpoint_json"]:
            checkpoint = json.loads(state["checkpoint_json"])

        focus_value = round(float(state["focus_energy"]), 3)
        as_of_playtime = int(state["focus_as_of_playtime"])
        ending_val = state["ending"] if state["ending"] in {"bad", "normal", "true"} else None
        current_case_val = state["current_case_id"] or None
        payload = {
            "displayName": prof["display_name"],
            "reputation": state["reputation"],
            "currentCaseID": current_case_val,
            "ending": ending_val,
            "focusEnergy": {"value": focus_value, "asOfPlaytime": as_of_playtime},
            "caseProgress": case_progress,
            "evidence": evidence,
            "deductionLinks": deduction_links,
            "unlocks": unlocks,
            "runicLogs": runic_logs,
            "caseResults": case_results,
            "dialogue": dialogue,
            "board": board,
            "puzzles": puzzles,
            "notes": notes,
            "checkpoint": checkpoint,
        }
        snap = {
            "profileID": prof["profile_id"],
            "schemaVersion": int(meta.get("schemaVersion", "1")),
            "contentVersion": int(meta.get("contentVersion", "1")),
            "appVersion": app_version,
            "revisionID": int(state["revision"]),
            "updatedAt": int(state["updated_at"]),
            "playtime": int(state["playtime"]),
            "payload": payload,
        }
        sealed = integrity.seal(snap, hmac_key)
        Snapshot.model_validate(sealed)
        return sealed


def import_snapshot(
    path: Path | str,
    key: bytes,
    snapshot: dict,
    *,
    bak_path: Path | str | None = None,
    hmac_key: bytes,
) -> None:
    """Replace one profile's rows after verifying integrity. Backs up first."""
    problems = integrity.verify(snapshot, hmac_key)
    if problems:
        raise ValueError("; ".join(problems))
    snap = Snapshot.model_validate(snapshot)
    path = Path(path)
    if bak_path is None:
        bak_path = path.with_suffix(path.suffix + ".bak")
    if path.exists():
        backup_db(path, key, bak_path)

    pid = snap.profileID
    p = snap.payload
    with connect(path, key) as conn:
        conn.execute("BEGIN")
        try:
            conn.execute("DELETE FROM profiles WHERE profile_id = ?", (pid,))
            conn.execute(
                "INSERT INTO profiles(profile_id, display_name, age, created_at) VALUES (?, ?, NULL, ?)",
                (pid, p.displayName, snap.updatedAt),
            )
            checkpoint_json = (
                None if p.checkpoint is None else json.dumps(p.checkpoint, separators=(",", ":"))
            )
            reputation = getattr(p, "reputation", 0)
            conn.execute(
                """
                INSERT INTO profile_state(
                  profile_id, revision, updated_at, playtime, reputation, current_case_id, ending,
                  focus_energy, focus_as_of_playtime, dialogue_json, board_json, puzzles_json,
                  notes_json, checkpoint_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid,
                    snap.revisionID,
                    snap.updatedAt,
                    snap.playtime,
                    reputation,
                    p.currentCaseID or "",
                    p.ending or "",
                    round(p.focusEnergy.value, 3),
                    p.focusEnergy.asOfPlaytime,
                    json.dumps(p.dialogue.model_dump(mode="json"), separators=(",", ":")),
                    json.dumps(p.board.model_dump(mode="json"), separators=(",", ":")),
                    json.dumps(
                        {k: v.model_dump(mode="json") for k, v in p.puzzles.items()}, separators=(",", ":")
                    ),
                    json.dumps([n.model_dump(mode="json") for n in p.notes], separators=(",", ":")),
                    checkpoint_json,
                ),
            )
            for case_id, cp in p.caseProgress.items():
                conn.execute(
                    """
                    INSERT INTO case_progress(
                      profile_id, case_id, status, progress_version, objective_id, warrant_granted,
                      failed_attempts, hint_tier, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pid,
                        case_id,
                        cp.status,
                        cp.progressVersion,
                        cp.objectiveID,
                        int(cp.warrantGranted),
                        cp.failedAttempts,
                        cp.hintTier,
                        cp.completedAt or snap.updatedAt,
                    ),
                )
            for clue_id, ev in p.evidence.items():
                conn.execute(
                    """
                    INSERT INTO clues_found(profile_id, case_id, clue_id, collected_at, via)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (pid, ev.caseID, clue_id, ev.collectedAt, ev.via),
                )
            for case_id, links in p.deductionLinks.items():
                for source_id, target_id in links:
                    conn.execute(
                        """
                        INSERT INTO deduction_links(profile_id, case_id, source_id, target_id)
                        VALUES (?, ?, ?, ?)
                        """,
                        (pid, case_id, source_id, target_id),
                    )
            for case_id, cr in p.caseResults.items():
                conn.execute(
                    """
                    INSERT INTO case_results(
                      profile_id, case_id, conclusion_id, correct, flawed, strikes, attempts, completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pid,
                        case_id,
                        cr.conclusionID,
                        int(cr.correct),
                        int(cr.flawed),
                        cr.strikes,
                        cr.attempts,
                        cr.completedAt,
                    ),
                )
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?), (?, ?)",
                ("schemaVersion", str(snap.schemaVersion), "contentVersion", str(snap.contentVersion)),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
