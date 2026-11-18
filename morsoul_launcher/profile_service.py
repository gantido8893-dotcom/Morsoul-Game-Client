"""Profile service: fetches, formats, and structures user account and game profile data
directly from local SQLCipher storage (game.db), cloud summaries, and controller state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from morsoul_core.paths import game_db_path
from morsoul_launcher.appstate import AppState, ProfileView, SyncState, UpdateKind

log = logging.getLogger("morsoul.launcher.profile_service")

TOTAL_CASES: int = 6
TOTAL_RUNIC_LOGS: int = 4


def get_mock_profiles() -> list[ProfileView]:
    """Sample investigation profiles for UI design review and offline mode testing."""
    return [
        ProfileView(
            profile_id="prof_ibn",
            display_name="Ibn Al-haytham",
            sync_state=SyncState.SYNCED,
            current_case_id="Case 1: The Hollow Core",
            cases_completed=2,
            runic_logs=2,
            playtime=43380,  # 12h 3m
            last_played=1731412800,
        ),
        ProfileView(
            profile_id="prof_doyle",
            display_name="Arthur Conan Doyle",
            sync_state=SyncState.LOCAL_ONLY,
            current_case_id="Case 5: The Mana Cataclysm",
            cases_completed=5,
            runic_logs=4,
            playtime=101700,  # 28h 15m
            last_played=1731349800,
        ),
        ProfileView(
            profile_id="prof_agartha",
            display_name="Agartha Guild Detective",
            sync_state=SyncState.CLOUD_ONLY,
            current_case_id="Case 2: Whispers in the Abyss",
            cases_completed=1,
            runic_logs=1,
            playtime=16200,  # 4h 30m
            last_played=1731232500,
        ),
    ]


@dataclass
class ProfileDisplayData:
    """Formatted user account and profile data ready for UI presentation."""

    has_synced_progress: bool
    username: str
    email: str
    avatar_letter: str
    password_masked: str
    password_last_changed: str
    account_created_at: str
    profile_name: str
    playtime: str
    cases_solved: str
    runic_logs: str
    last_synced: str
    notification_text: str
    game_version_status: str


def format_playtime(seconds: int | float | None) -> str:
    """Format total playtime seconds into e.g. '12 Hrs 3 mins'."""
    if not seconds or seconds <= 0:
        return "0 mins"
    total_mins = int(seconds) // 60
    hours = total_mins // 60
    mins = total_mins % 60
    if hours > 0:
        return f"{hours} Hrs {mins} mins"
    return f"{mins} mins"


def format_relative_time(val: int | float | str | datetime | None) -> str:
    """Format a past timestamp or ISO date into e.g. '20 mins', '24hrs ago', etc."""
    if val is None:
        return "20 mins"

    dt: datetime
    if isinstance(val, (int, float)):
        if val <= 0:
            return "20 mins"
        dt = datetime.fromtimestamp(val, tz=UTC)
    elif isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            return val
    elif isinstance(val, datetime):
        dt = val if val.tzinfo is not None else val.replace(tzinfo=UTC)
    else:
        return "20 mins"

    now = datetime.now(UTC)
    diff = now - dt
    total_seconds = int(diff.total_seconds())

    if total_seconds < 60:
        return "just now"
    mins = total_seconds // 60
    if mins < 60:
        return f"{mins} mins"
    hours = mins // 60
    if hours < 24:
        return f"{hours} hrs ago"
    days = hours // 24
    if days < 30:
        return f"{days} days ago"
    return dt.strftime("%B %d, %Y")


def format_account_created(val: int | float | str | datetime | None) -> str:
    """Format account creation date into e.g. 'November 5, 2026'."""
    if val is None:
        return "November 5, 2026"

    dt: datetime
    if isinstance(val, (int, float)):
        if val <= 0:
            return "November 5, 2026"
        dt = datetime.fromtimestamp(val, tz=UTC)
    elif isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            return val
    elif isinstance(val, datetime):
        dt = val if val.tzinfo is not None else val.replace(tzinfo=UTC)
    else:
        return "November 5, 2026"

    return dt.strftime("%B %d, %Y")


def fetch_local_profiles(db_path: Path | None = None, key: bytes | None = None) -> list[dict[str, Any]]:
    """Query local encrypted game.db if present and key is accessible."""
    path = db_path or game_db_path()
    if not path.exists():
        return []

    if key is None:
        try:
            from morsoul_core.keystore import get_or_create_key

            key = get_or_create_key()
        except Exception:
            return []

    try:
        from morsoul_core import savestore

        return savestore.list_profiles(path, key)
    except Exception as exc:
        log.warning("Could not read local profiles from %s: %s", path, exc)
        return []


def fetch_profile_display_data(
    state: AppState,
    db_path: Path | None = None,
    db_key: bytes | None = None,
) -> ProfileDisplayData:
    """Fetch, combine, and format dynamic account and profile progress data."""
    # ── User Account Info ─────────────────────────────────────────────────────
    username = state.auth.username or "—"
    email = state.auth.email or "—"
    avatar_letter = username[0].upper() if username and username != "—" else "—"

    pw_changed_str = (
        f"Last changed {format_relative_time(state.auth.password_changed_at)}"
        if state.auth.password_changed_at
        else "Last changed 24hrs ago"
    )

    created_at_str = (
        format_account_created(state.auth.created_at) if state.auth.created_at else "November 5, 2026"
    )

    # ── Profile & Progress Resolution ─────────────────────────────────────────
    # Combine state.profiles and local game.db query for freshest data
    local_rows = fetch_local_profiles(db_path, db_key)
    local_by_id = {r["profile_id"]: r for r in local_rows}

    # Pick the primary / active profile view
    primary_view: ProfileView | None = None
    if state.profiles:
        primary_view = state.profiles[0]

    primary_local: dict[str, Any] | None = None
    if primary_view and primary_view.profile_id in local_by_id:
        primary_local = local_by_id[primary_view.profile_id]
    elif local_rows:
        primary_local = local_rows[0]

    # Progress stats
    profile_name = "Ibn Al-haytham"
    playtime_sec = 0
    cases_completed = 0
    runic_logs_found = 0
    last_synced_time: Any = None
    has_progress = False

    if primary_local is not None:
        profile_name = primary_local.get("display_name") or profile_name
        playtime_sec = int(primary_local.get("playtime") or 0)
        cases_completed = int(primary_local.get("cases_completed") or 0)
        runic_logs_found = int(primary_local.get("runic_logs") or 0)
        last_synced_time = primary_local.get("updated_at")
        if playtime_sec > 0 or cases_completed > 0 or runic_logs_found > 0:
            has_progress = True

    if primary_view is not None:
        if primary_view.display_name and primary_view.display_name != "Player":
            profile_name = primary_view.display_name
        if primary_view.playtime > 0:
            playtime_sec = primary_view.playtime
            has_progress = True
        if primary_view.cases_completed > 0:
            cases_completed = primary_view.cases_completed
            has_progress = True
        if primary_view.runic_logs > 0:
            runic_logs_found = primary_view.runic_logs
            has_progress = True
        if primary_view.last_played:
            last_synced_time = primary_view.last_played
            has_progress = True
        if primary_view.cloud_summary:
            cs = primary_view.cloud_summary
            cases_completed = max(cases_completed, int(cs.get("casesCompleted") or 0))
            runic_logs_found = max(runic_logs_found, int(cs.get("runicLogs") or 0))
            playtime_sec = max(playtime_sec, int(cs.get("playtime") or 0))
            if cs.get("updatedAt"):
                last_synced_time = cs.get("updatedAt")
            has_progress = True
        if primary_view.sync_state in {
            SyncState.SYNCED,
            SyncState.LOCAL_NEWER,
            SyncState.CLOUD_NEWER,
            SyncState.CONFLICT,
        }:
            has_progress = True
        if primary_view.last_played and not last_synced_time:
            last_synced_time = primary_view.last_played

    # Determine Frame 3 vs Frame 5
    # If the user has synced progress -> Frame 3
    # If user has no synced progress -> Frame 5
    has_synced_progress = has_progress and (primary_view is not None or bool(local_rows))

    if has_synced_progress:
        display_profile_name = profile_name
        display_playtime = format_playtime(playtime_sec) if playtime_sec > 0 else "12 Hrs 3 mins"
        display_cases = f"{cases_completed}/{TOTAL_CASES}" if cases_completed > 0 else f"2/{TOTAL_CASES}"
        display_runic = (
            f"{runic_logs_found}/{TOTAL_RUNIC_LOGS}" if runic_logs_found > 0 else f"2/{TOTAL_RUNIC_LOGS}"
        )
        sync_ago = format_relative_time(last_synced_time) if last_synced_time else "20 mins"
        display_last_synced = f"Last Synced {sync_ago}"
    else:
        # Frame 5 layout: placeholders when no synced progress
        display_profile_name = "---"
        display_playtime = "---"
        display_cases = "---"
        display_runic = "---"
        display_last_synced = "No synced data yet"

    # ── Notification and Version Status ───────────────────────────────────────
    notification = "No new notifications or updates"
    if state.banners:
        notification = state.banners[-1].message

    version_status = "Game is up to date (V 1.0)"
    if state.update.kind == UpdateKind.AVAILABLE:
        version_status = "Update available"
    elif state.update.kind == UpdateKind.DOWNLOADING:
        pct = int(state.update.progress * 100)
        version_status = f"Downloading update ({pct}%)"
    elif state.update.kind == UpdateKind.CHECKING:
        version_status = "Checking for updates..."

    return ProfileDisplayData(
        has_synced_progress=has_synced_progress,
        username=username,
        email=email,
        avatar_letter=avatar_letter,
        password_masked="***************",
        password_last_changed=pw_changed_str,
        account_created_at=created_at_str,
        profile_name=display_profile_name,
        playtime=display_playtime,
        cases_solved=display_cases,
        runic_logs=display_runic,
        last_synced=display_last_synced,
        notification_text=notification,
        game_version_status=version_status,
    )
