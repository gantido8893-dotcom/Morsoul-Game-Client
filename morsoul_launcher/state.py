"""Persistent launcher state (server URL cache and per-profile sync pointers)."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from morsoul_core.paths import launcher_state_path


@dataclass
class ProfileSyncRecord:
    revision: int
    state_hash: str
    cloud_deleted: bool = False


@dataclass
class LauncherState:
    server_url: str | None = None
    installed_app_version: str | None = None
    profiles: dict[str, ProfileSyncRecord] = field(default_factory=dict)
    sync_on_game_close: bool = True
    sync_on_launcher_open: bool = True
    check_updates_on_start: bool = True
    close_launcher_on_game_start: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "serverURL": self.server_url,
            "installedAppVersion": self.installed_app_version,
            "syncOnGameClose": self.sync_on_game_close,
            "syncOnLauncherOpen": self.sync_on_launcher_open,
            "checkUpdatesOnStart": self.check_updates_on_start,
            "closeLauncherOnGameStart": self.close_launcher_on_game_start,
            "profiles": {
                pid: {
                    "revision": rec.revision,
                    "stateHash": rec.state_hash,
                    **({"cloudDeleted": True} if rec.cloud_deleted else {}),
                }
                for pid, rec in self.profiles.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LauncherState:
        profiles: dict[str, ProfileSyncRecord] = {}
        for pid, raw in (data.get("profiles") or {}).items():
            profiles[pid] = ProfileSyncRecord(
                revision=int(raw["revision"]),
                state_hash=str(raw["stateHash"]),
                cloud_deleted=bool(raw.get("cloudDeleted", False)),
            )
        return cls(
            server_url=data.get("serverURL"),
            installed_app_version=data.get("installedAppVersion"),
            profiles=profiles,
            sync_on_game_close=bool(data.get("syncOnGameClose", True)),
            sync_on_launcher_open=bool(data.get("syncOnLauncherOpen", True)),
            check_updates_on_start=bool(data.get("checkUpdatesOnStart", True)),
            close_launcher_on_game_start=bool(data.get("closeLauncherOnGameStart", False)),
        )


def load_launcher_state(path: Path | None = None) -> LauncherState:
    path = path or launcher_state_path()
    if not path.exists():
        return LauncherState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return LauncherState.from_dict(data)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return LauncherState()


def save_launcher_state(state: LauncherState, path: Path | None = None) -> None:
    path = path or launcher_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state.to_dict(), indent=2, sort_keys=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".launcher-state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# silence unused import warning for asdict if unused
_ = asdict
