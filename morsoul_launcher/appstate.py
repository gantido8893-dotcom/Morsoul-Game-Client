"""Observable launcher state (no UI types)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal


class AuthKind(StrEnum):
    SIGNED_OUT = "signed_out"
    SIGNING_IN = "signing_in"
    SIGNED_IN = "signed_in"
    OFFLINE_MODE = "offline_mode"


@dataclass
class AuthState:
    kind: AuthKind = AuthKind.SIGNED_OUT
    user_id: str | None = None
    username: str | None = None
    email: str | None = None
    created_at: str | None = None
    password_changed_at: str | None = None


class NetworkKind(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"


class UpdateKind(StrEnum):
    IDLE = "idle"
    CHECKING = "checking"
    AVAILABLE = "available"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    APPLYING = "applying"
    UP_TO_DATE = "up_to_date"
    FAILED = "failed"


@dataclass
class UpdateState:
    kind: UpdateKind = UpdateKind.IDLE
    info: Any = None
    progress: float = 0.0
    status_text: str = ""
    reason: str | None = None


class SyncState(StrEnum):
    SYNCED = "synced"
    LOCAL_NEWER = "local_newer"
    CLOUD_NEWER = "cloud_newer"
    CONFLICT = "conflict"
    LOCAL_ONLY = "local_only"
    CLOUD_ONLY = "cloud_only"
    SYNCING = "syncing"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class ProfileView:
    profile_id: str
    display_name: str
    current_case_id: str | None = None
    cases_completed: int = 0
    runic_logs: int = 0
    rank: str = ""
    playtime: int = 0
    last_played: int | None = None
    sync_state: SyncState = SyncState.SYNCED
    sync_reason: str | None = None
    cloud_summary: dict[str, Any] | None = None


class GameKind(StrEnum):
    NOT_RUNNING = "not_running"
    RUNNING = "running"


@dataclass
class Banner:
    id: str
    message: str
    level: Literal["info", "warn", "error", "success"] = "info"


@dataclass
class AppState:
    auth: AuthState = field(default_factory=AuthState)
    network: NetworkKind = NetworkKind.ONLINE
    update: UpdateState = field(default_factory=UpdateState)
    profiles: list[ProfileView] = field(default_factory=list)
    game: GameKind = GameKind.NOT_RUNNING
    server_url: str = ""
    banners: list[Banner] = field(default_factory=list)
    busy: bool = False
    last_error: str | None = None

    def clear_banners(self) -> None:
        self.banners.clear()

    def remove_banner(self, banner_id: str) -> None:
        self.banners = [b for b in self.banners if b.id != banner_id]

    def add_banner(
        self, banner_id: str, message: str, level: Literal["info", "warn", "error", "success"] = "info"
    ) -> None:
        self.banners = [b for b in self.banners if b.id != banner_id]
        self.banners.append(Banner(banner_id, message, level))
