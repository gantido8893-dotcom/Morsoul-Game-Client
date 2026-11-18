"""Pure sync classification for one profile."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class Action(StrEnum):
    NOTHING = "nothing"
    UPLOAD = "upload"
    DOWNLOAD = "download"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class LocalInfo:
    state_hash: str | None  # None = local missing / invalid handled elsewhere
    valid: bool = True


@dataclass(frozen=True)
class LastSynced:
    revision: int
    state_hash: str


@dataclass(frozen=True)
class CloudInfo:
    revision: int | None  # None = no cloud save
    state_hash: str | None = None


def classify(
    local: LocalInfo | None,
    last_synced: LastSynced | None,
    cloud: CloudInfo | None,
) -> Action:
    """Decide the sync action for one profile.

    First sync (no last_synced): cloud empty + local valid -> upload;
    local missing + cloud present -> download; both present -> conflict; both absent -> nothing.
    """
    local_present = local is not None and local.state_hash is not None and local.valid
    cloud_present = cloud is not None and cloud.revision is not None

    if last_synced is None:
        if local_present and not cloud_present:
            return Action.UPLOAD
        if cloud_present and not local_present:
            return Action.DOWNLOAD
        if local_present and cloud_present:
            return Action.CONFLICT
        return Action.NOTHING

    local_changed = bool(local_present and local is not None and local.state_hash != last_synced.state_hash)
    # missing/invalid local after having synced: treat as not locally changed for upload purposes
    if local is not None and not local.valid:
        local_changed = False
    if not local_present:
        local_changed = False

    cloud_changed = bool(
        cloud_present
        and cloud is not None
        and cloud.revision is not None
        and cloud.revision != last_synced.revision
    )
    if not cloud_present:
        # cloud gone — engine handles cloudDeleted; classify as nothing here
        return Action.NOTHING

    if not local_changed and not cloud_changed:
        return Action.NOTHING
    if local_changed and not cloud_changed:
        return Action.UPLOAD
    if not local_changed and cloud_changed:
        return Action.DOWNLOAD
    return Action.CONFLICT


SkipReason = Literal[
    "offline",
    "game_running",
    "local_invalid",
    "not_logged_in",
    "server_error",
    "key_unavailable",
    "rate_limited",
]
