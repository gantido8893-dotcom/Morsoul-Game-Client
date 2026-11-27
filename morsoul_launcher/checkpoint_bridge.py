"""Bridge between Unity local JSON checkpoints and user's SQLCipher database."""
import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path

from morsoul_core import savestore
from morsoul_core.keystore import get_or_create_key

log = logging.getLogger("morsoul.launcher.bridge")

_SEAL_KEY = b"Morsoul-Worlds-Case/Checkpoint/2026"
_SCENE_MODE = ["Mode3D", "Mode2D", "Cinematic", "Loading"]
_FACING_2D = ["Up", "Down", "Left", "Right"]
_GRADE = ["Ungraded", "Clean", "Standard", "Flawed"]
_TOOL = ["None", "GolemEye", "EmotionEcho", "AetherSight"]

_CASE_FALLBACK_SCENE = {
    0: "PrologueRuins",
    1: "Hub_LowerMarket",
    2: "Hub_CathedralCourtyard",
    3: "Hub_Wilderness",
    4: "Hub_IronHollow",
}


def _enum_str(names: list[str], val) -> str:
    if isinstance(val, str):
        return val
    idx = int(val)
    return names[idx] if 0 <= idx < len(names) else str(val)


def _format_num(val: float) -> str:
    rounded = round(float(val), 3)
    if rounded == 0.0:
        rounded = 0.0
    s = f"{rounded:.3f}".rstrip("0").rstrip(".")
    return s if s else "0"


def _canonicalize(obj) -> str:
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, int):
        return str(obj)
    if isinstance(obj, float):
        return _format_num(obj)
    if isinstance(obj, str):
        return json.dumps(obj, ensure_ascii=False)
    if isinstance(obj, dict):
        items = sorted((str(k), v) for k, v in obj.items())
        return "{" + ",".join(f"{json.dumps(k, ensure_ascii=False)}:{_canonicalize(v)}" for k, v in items) + "}"
    if isinstance(obj, list):
        return "[" + ",".join(_canonicalize(x) for x in obj) + "]"
    raise TypeError(type(obj))


def _player_pos(p):
    if p is None:
        return None
    return {"x": float(p.get("x", 0.0)), "y": float(p.get("y", 0.0)), "z": float(p.get("z", 0.0))}


def _to_canonical(s: dict) -> dict:
    v4 = int(s.get("saveVersion", 4)) >= 4
    pos = s.get("playerPosition") if (s.get("hasPlayerPosition", True) if v4 else s.get("playerPosition") is not None) else None
    act_int = s.get("activeInterrogation") if (s.get("hasActiveInterrogation", False) if v4 else s.get("activeInterrogation") is not None) else None
    inv_ret = s.get("investigationReturn") if (s.get("hasInvestigationReturn", False) if v4 else s.get("investigationReturn") is not None) else None

    board_states = [
        {
            "caseId": int(b.get("caseId", 0)),
            "visibleClueIds": list(b.get("visibleClueIds") or []),
            "collectedClueIds": list(b.get("collectedClueIds") or []),
            "links": [{"sourceId": l.get("sourceId") or "", "targetId": l.get("targetId") or ""} for l in (b.get("links") or []) if l],
            "nodePositions": [{"clueId": np.get("clueId") or "", "x": float(np.get("x", 0.0)), "y": float(np.get("y", 0.0))} for np in (b.get("nodePositions") or []) if np],
            "selectedConclusionId": b.get("selectedConclusionId") or "",
            "caseErrorCount": int(b.get("caseErrorCount", 0)),
            "firedHintTiers": [int(t) for t in (b.get("firedHintTiers") or [])],
            "linkingLockedOut": bool(b.get("linkingLockedOut", False)),
            "submittedConclusionId": b.get("submittedConclusionId") or "",
            "boardSolved": bool(b.get("boardSolved", False)),
            "completionRewardApplied": bool(b.get("completionRewardApplied", False)),
            "submittedWrongConclusionIds": list(b.get("submittedWrongConclusionIds") or []),
            "submittedPartialConclusionIds": list(b.get("submittedPartialConclusionIds") or []),
        }
        for b in (s.get("boardStates") or [])
        if b
    ]
    grade_states = [
        {
            "caseId": int(g.get("caseId", 0)),
            "caseErrorCount": int(g.get("caseErrorCount", 0)),
            "submittedWrongConclusionIds": list(g.get("submittedWrongConclusionIds") or []),
            "submittedPartialConclusionIds": list(g.get("submittedPartialConclusionIds") or []),
            "interrogationStrikeCount": int(g.get("interrogationStrikeCount", 0)),
            "mistrialUsed": bool(g.get("mistrialUsed", False)),
            "strainedScanUsed": bool(g.get("strainedScanUsed", False)),
            "displayGrade": _enum_str(_GRADE, g.get("displayGrade", 0)),
        }
        for g in (s.get("caseGradeStates") or [])
        if g
    ]

    m = {
        "saveVersion": int(s.get("saveVersion", 4)),
        "profileId": s.get("profileId") or "",
        "playerName": s.get("playerName") or "",
        "currentCase": int(s.get("currentCase", 0)),
        "checkpointSceneName": s.get("checkpointSceneName") or "",
        "currentSceneMode": _enum_str(_SCENE_MODE, s.get("currentSceneMode", 1)),
        "currentSceneId": s.get("currentSceneId") or "",
        "playerPosition": _player_pos(pos),
        "playerFacing2D": _enum_str(_FACING_2D, s.get("playerFacing2D", 1)),
        "collectedClueIds": list(s.get("collectedClueIds") or []),
        "boardEdges": list(s.get("boardEdges") or []),
        "runicLogsCollected": [bool(x) for x in (s.get("runicLogsCollected") or [])],
        "caseGrades": [_enum_str(_GRADE, x) for x in (s.get("caseGrades") or [])],
        "uneaseFlags": [{"key": f.get("key") or "", "value": bool(f.get("value", False))} for f in (s.get("uneaseFlags") or []) if f],
        "toolsUnlocked": [_enum_str(_TOOL, x) for x in (s.get("toolsUnlocked") or [])],
        "focusState": {
            "currentEnergy": float(s.get("focusEnergy", 100.0)),
            "maximumEnergy": float(s.get("focusMax", 100.0)),
            "restElapsedRemainder": float(s.get("restElapsedRemainderSeconds", 0.0)),
            "closedAtUtc": s.get("closedAtUtc") or "",
            "lastTrustedUtc": s.get("lastTrustedUtc") or "",
            "lastOfflineRecoveryAppliedAtUtc": s.get("lastOfflineRecoveryAppliedAtUtc") or "",
            "strainedScanUsedByCase": [bool(x) for x in (s.get("strainedScanUsedByCase") or [])],
        },
        "boardStates": board_states,
        "caseGradeStates": grade_states,
        "prologueCompleted": bool(s.get("prologueCompleted", False)),
        "prologueGateUnlocked": bool(s.get("prologueGateUnlocked", False)),
        "prologueRobeCollected": bool(s.get("prologueRobeCollected", False)),
        "prologueExitLoaded": bool(s.get("prologueExitLoaded", False)),
        "elizaIntroTriggered": bool(s.get("elizaIntroTriggered", False)),
        "elizaIntroSeen": bool(s.get("elizaIntroSeen", False)),
        "easternRouteUnlocked": bool(s.get("easternRouteUnlocked", False)),
        "activeCutsceneId": s.get("activeCutsceneId") or "",
        "preCutsceneCheckpointId": s.get("preCutsceneCheckpointId") or "",
        "activeInterrogation": None if act_int is None else {
            "caseId": int(act_int.get("caseId", 0)),
            "phaseIndex": int(act_int.get("phaseIndex", 0)),
            "composureSegmentsRemaining": int(act_int.get("composureSegmentsRemaining", 0)),
            "strikeCount": int(act_int.get("strikeCount", 0)),
            "entryStrikeCount": int(act_int.get("entryStrikeCount", 0)),
            "preInterrogationCheckpointId": act_int.get("preInterrogationCheckpointId") or "",
        },
    }
    if v4:
        m["hasPlayerPosition"] = bool(s.get("hasPlayerPosition", False))
        m["hasActiveInterrogation"] = bool(s.get("hasActiveInterrogation", False))
        m["hasInvestigationReturn"] = bool(s.get("hasInvestigationReturn", False))
        m["investigationCaseId"] = int(s.get("investigationCaseId", -1))
        m["investigationReturn"] = None if inv_ret is None else {
            "sceneName": inv_ret.get("sceneName") or "",
            "position": _player_pos(inv_ret.get("position")),
            "facing": _enum_str(_FACING_2D, inv_ret.get("facing", 0)),
        }
    return m


def repair_checkpoint_scene(content: str) -> tuple[str, bool]:
    """If checkpointSceneName is 'Title' or empty, restore it from currentSceneId and re-seal."""
    try:
        outer = json.loads(content)
        payload_str = outer.get("payload")
        if not payload_str:
            return content, False
        pl = json.loads(payload_str)
        cp_scene = (pl.get("checkpointSceneName") or "").strip()
        if cp_scene and cp_scene.lower() != "title":
            return content, False

        target_scene = (pl.get("currentSceneId") or "").strip()
        if not target_scene or target_scene.lower() == "title":
            case_num = int(pl.get("currentCase", 0))
            if case_num == 0 and pl.get("prologueCompleted"):
                target_scene = "Hub_LowerMarket"
            else:
                target_scene = _CASE_FALLBACK_SCENE.get(case_num, "Hub_LowerMarket")

        pl["checkpointSceneName"] = target_scene
        new_payload_str = json.dumps(pl, separators=(",", ":"), ensure_ascii=False)
        canon = _canonicalize(_to_canonical(pl))
        state_hash = hashlib.sha256(canon.encode("utf-8")).hexdigest()
        seal_msg = f"{pl.get('profileId') or 'local'}:{int(pl.get('saveVersion', 4))}:{state_hash}".encode("utf-8")
        seal = hmac.new(_SEAL_KEY, seal_msg, hashlib.sha256).hexdigest()
        repaired = json.dumps(
            {"payload": new_payload_str, "stateHash": state_hash, "seal": seal},
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return repaired, True
    except Exception as exc:
        log.warning("Failed to repair checkpoint scene: %s", exc)
        return content, False

SLOT_FILES = {
    1: "morsoul_checkpoint.json",
    2: "morsoul_checkpoint_slot2.json",
    3: "morsoul_checkpoint_slot3.json",
}

def get_locallow_dir() -> Path:
    userprofile = os.environ.get("USERPROFILE", "")
    return Path(userprofile) / "AppData" / "LocalLow" / "DefaultCompany" / "Morsoul"

def get_account_slot_dir(user_id: str) -> Path:
    localappdata = os.environ.get("LOCALAPPDATA", "")
    p = Path(localappdata) / "Morsoul" / "checkpoints" / user_id
    p.mkdir(parents=True, exist_ok=True)
    return p

def sync_checkpoints_to_user_db(db_path: Path, user_id: str) -> None:
    """Read game's 3 slot checkpoint files and write/update them into user's game_{user_id}.db."""
    locallow = get_locallow_dir()
    if not locallow.exists():
        return
    
    key = get_or_create_key()
    now = int(time.time())
    
    for slot, fname in SLOT_FILES.items():
        cp_path = locallow / fname
        if not cp_path.exists():
            continue
        try:
            content = cp_path.read_text("utf-8")
            content, repaired = repair_checkpoint_scene(content)
            if repaired:
                cp_path.write_text(content, encoding="utf-8")
            data = json.loads(content)
            payload_str = data.get("payload")
            if not payload_str:
                continue
            pl = json.loads(payload_str)
            profile_id = pl.get("profileId")
            if not profile_id:
                continue
            
            player_name = (pl.get("playerName") or "").strip()
            display_name = player_name if player_name else "Detective"
            current_case = pl.get("currentCase", 0)
            case_id_str = f"case_{current_case:02d}"
            focus = round(float(pl.get("focusEnergy", 100.0)), 3)
            
            with savestore.connect(db_path, key, read_only=False) as conn:
                # 1. profiles table (order by created_at based on slot)
                # Ensure created_at preserves slot order: slot 1 earliest, slot 2 next, slot 3 latest
                slot_created_at = now - (3 - slot) * 100
                conn.execute(
                    """
                    INSERT INTO profiles (profile_id, display_name, created_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(profile_id) DO UPDATE SET display_name = excluded.display_name
                    """,
                    (profile_id, display_name, slot_created_at),
                )
                
                # 2. profile_state table
                conn.execute(
                    """
                    INSERT INTO profile_state (
                        profile_id, revision, updated_at, playtime, reputation,
                        current_case_id, ending, focus_energy, focus_as_of_playtime,
                        dialogue_json, board_json, puzzles_json, notes_json, checkpoint_json
                    ) VALUES (?, 1, ?, 0, 0, ?, '', ?, 0, '{}', '{}', '{}', '[]', ?)
                    ON CONFLICT(profile_id) DO UPDATE SET
                        revision = revision + 1,
                        updated_at = excluded.updated_at,
                        current_case_id = excluded.current_case_id,
                        focus_energy = excluded.focus_energy,
                        checkpoint_json = excluded.checkpoint_json
                    """,
                    (profile_id, now, case_id_str, focus, content),
                )
                
                # 3. clues_found
                for cid in pl.get("collectedClueIds", []):
                    if cid:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO clues_found (profile_id, clue_id, case_id, collected_at, via)
                            VALUES (?, ?, ?, ?, 'examine')
                            """,
                            (profile_id, cid, case_id_str, now),
                        )
                
                # 4. boardStates -> case_progress & deduction_links
                for b in pl.get("boardStates", []):
                    if not b:
                        continue
                    b_case_id = f"case_{b.get('caseId', 0):02d}"
                    status = "completed" if b.get("boardSolved") else "in_progress"
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO case_progress (
                            profile_id, case_id, status, progress_version, objective_id,
                            warrant_granted, failed_attempts, hint_tier, updated_at
                        ) VALUES (?, ?, ?, 1, ?, 0, ?, 0, ?)
                        """,
                        (profile_id, b_case_id, status, pl.get("currentSceneId") or "", b.get("caseErrorCount", 0), now),
                    )
                    
                    conn.execute("DELETE FROM deduction_links WHERE profile_id = ? AND case_id = ?", (profile_id, b_case_id))
                    for link in b.get("links", []):
                        src = link.get("sourceId")
                        dst = link.get("targetId")
                        if src and dst:
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO deduction_links (profile_id, case_id, source_id, target_id)
                                VALUES (?, ?, ?, ?)
                                """,
                                (profile_id, b_case_id, src, dst),
                            )
                
                # 5. caseGrades -> case_results
                case_grades = pl.get("caseGrades", [])
                for i, g in enumerate(case_grades):
                    if g and g > 0:
                        c_num = i + 1
                        c_case = f"case_{c_num:02d}"
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO case_results (
                                profile_id, case_id, conclusion_id, correct, flawed, strikes, attempts, completed_at
                            ) VALUES (?, ?, '', 1, ?, 0, 1, ?)
                            """,
                            (profile_id, c_case, 1 if g == 2 else 0, now),
                        )
                conn.commit()
        except Exception as e:
            log.warning("Failed to bridge checkpoint %s into DB: %s", fname, e)
    
    # Also backup current checkpoints into the user's isolated checkpoints folder
    backup_account_checkpoints(user_id)

def sync_user_db_to_checkpoints(db_path: Path, user_id: str) -> None:
    """When switching accounts or downloading cloud profiles, restore them to the game's 3 slot files."""
    if not db_path.exists():
        # Clear slot files so new account starts fresh with no profiles
        clear_game_checkpoints()
        return

    locallow = get_locallow_dir()
    locallow.mkdir(parents=True, exist_ok=True)
    key = get_or_create_key()

    with savestore.connect(db_path, key, read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT p.profile_id, s.checkpoint_json
            FROM profiles p
            LEFT JOIN profile_state s ON s.profile_id = p.profile_id
            ORDER BY p.created_at ASC, p.profile_id ASC
            LIMIT 3
            """
        ).fetchall()

    if not rows:
        clear_game_checkpoints()
        return

    for slot in [1, 2, 3]:
        fname = SLOT_FILES[slot]
        target = locallow / fname
        idx = slot - 1
        if idx < len(rows) and rows[idx]["checkpoint_json"]:
            repaired_cp, _ = repair_checkpoint_scene(rows[idx]["checkpoint_json"])
            target.write_text(repaired_cp, encoding="utf-8")
        else:
            if target.exists():
                try:
                    target.unlink()
                except OSError:
                    pass

def backup_account_checkpoints(user_id: str) -> None:
    """Save the active slot files to the user's isolated backup folder."""
    locallow = get_locallow_dir()
    account_dir = get_account_slot_dir(user_id)
    for fname in SLOT_FILES.values():
        src = locallow / fname
        dst = account_dir / fname
        if src.exists():
            try:
                dst.write_text(src.read_text("utf-8"), encoding="utf-8")
            except Exception:
                pass
        else:
            if dst.exists():
                try:
                    dst.unlink()
                except OSError:
                    pass

def restore_account_checkpoints(user_id: str) -> None:
    """Restore this account's isolated slot files into the game directory."""
    locallow = get_locallow_dir()
    locallow.mkdir(parents=True, exist_ok=True)
    account_dir = get_account_slot_dir(user_id)
    for fname in SLOT_FILES.values():
        src = account_dir / fname
        dst = locallow / fname
        if src.exists():
            repaired_cp, _ = repair_checkpoint_scene(src.read_text("utf-8"))
            dst.write_text(repaired_cp, encoding="utf-8")
        else:
            if dst.exists():
                try:
                    dst.unlink()
                except OSError:
                    pass

def clear_game_checkpoints() -> None:
    """Delete active slot files so an empty account sees empty slots."""
    locallow = get_locallow_dir()
    for fname in SLOT_FILES.values():
        p = locallow / fname
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass


def delete_profile_checkpoints(profile_id: str, user_id: str | None = None) -> None:
    """Delete any local/backed-up slot checkpoint file belonging to profile_id."""
    if not profile_id:
        return
    dirs = [get_locallow_dir()]
    if user_id:
        dirs.append(get_account_slot_dir(user_id))
    for folder in dirs:
        if not folder.exists():
            continue
        for fname in SLOT_FILES.values():
            p = folder / fname
            if not p.exists():
                continue
            try:
                outer = json.loads(p.read_text("utf-8"))
                pl = json.loads(outer.get("payload") or "{}")
                if pl.get("profileId") == profile_id:
                    p.unlink()
            except Exception:
                pass


def detect_played_profile_id(session_start_ts: float) -> str | None:
    """Return profileId of the slot checkpoint modified most recently during the game session."""
    locallow = get_locallow_dir()
    if not locallow.exists():
        return None
    best_mtime = session_start_ts - 2.0
    best_pid: str | None = None
    for fname in SLOT_FILES.values():
        p = locallow / fname
        if not p.exists():
            continue
        try:
            mtime = p.stat().st_mtime
            if mtime >= best_mtime:
                outer = json.loads(p.read_text("utf-8"))
                pl = json.loads(outer.get("payload") or "{}")
                pid = pl.get("profileId")
                if pid:
                    best_mtime = mtime
                    best_pid = pid
        except Exception:
            pass
    return best_pid


def add_profile_playtime(db_path: Path, profile_id: str, elapsed_seconds: int) -> None:
    """Add elapsed session seconds to a profile's playtime in the SQLCipher DB."""
    if not db_path.exists() or not profile_id or elapsed_seconds <= 0:
        return
    key = get_or_create_key()
    with savestore.connect(db_path, key, read_only=False) as conn:
        conn.execute(
            "UPDATE profile_state SET playtime = COALESCE(playtime, 0) + ? WHERE profile_id = ?",
            (int(elapsed_seconds), profile_id),
        )
        conn.commit()
