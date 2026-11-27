"""Per-profile sync engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from morsoul_core import integrity, savestore
from morsoul_core.keystore import KeyUnavailableError
from morsoul_core.snapshot import Snapshot
from morsoul_core.validation import validate_snapshot
from morsoul_launcher.api import ApiClient, ApiError, AuthError, ConflictError, NetworkError, RateLimitedError
from morsoul_launcher.state import LauncherState, ProfileSyncRecord, save_launcher_state
from morsoul_launcher.sync.classify import Action, CloudInfo, LastSynced, LocalInfo, SkipReason, classify
from morsoul_launcher.sync.gamelock import is_game_running

log = logging.getLogger("morsoul.launcher.sync")


class SyncTrigger(StrEnum):
    OPEN = "open"
    CLOSE = "close"
    GAME_CLOSED = "game_closed"
    MANUAL = "manual"


@dataclass
class SyncOutcome:
    profile_id: str | None
    kind: Literal[
        "noop",
        "uploaded",
        "downloaded",
        "conflict",
        "skipped",
    ]
    revision: int | None = None
    reason: SkipReason | None = None
    local_summary: dict[str, Any] | None = None
    cloud_summary: dict[str, Any] | None = None
    error_message: str | None = None


def _summary_from_snapshot(snap: dict) -> dict[str, Any]:
    p = snap.get("payload") or {}
    cases = p.get("caseResults") or {}
    runic = p.get("runicLogs") or {}
    found = sum(1 for v in runic.values() if isinstance(v, dict) and v.get("foundAt") is not None)
    return {
        "currentCaseID": p.get("currentCaseID"),
        "casesCompleted": len(cases),
        "runicLogs": found,
        "ending": p.get("ending"),
        "playtime": snap.get("playtime", 0),
        "displayName": p.get("displayName"),
        "updatedAt": snap.get("updatedAt"),
    }


class SyncEngine:
    def __init__(
        self,
        *,
        api: ApiClient,
        db_path: Path,
        bak_path: Path,
        db_key: bytes,
        hmac_key: bytes,
        state: LauncherState,
        state_path: Path | None = None,
        content: Any = None,
        lock_path: Path | None = None,
        app_version: str = "0.1.0",
        online: bool = True,
        logged_in: bool = True,
    ) -> None:
        self.api = api
        self.db_path = db_path
        self.bak_path = bak_path
        self.db_key = db_key
        self.hmac_key = hmac_key
        self.state = state
        self.state_path = state_path
        self.content = content
        self.lock_path = lock_path
        self.app_version = app_version
        self.online = online
        self.logged_in = logged_in

    def _persist(self) -> None:
        if self.state_path is not None:
            save_launcher_state(self.state, self.state_path)

    def _export_local(self, profile_id: str) -> tuple[dict | None, SkipReason | None]:
        if not self.db_path.exists():
            return None, None
        try:
            snap = savestore.export_snapshot(
                self.db_path, self.db_key, profile_id, app_version=self.app_version, hmac_key=self.hmac_key
            )
        except KeyUnavailableError:
            return None, "key_unavailable"
        except KeyError:
            return None, None
        except FileNotFoundError:
            return None, None
        except Exception:
            log.exception("export failed")
            return None, "local_invalid"
        problems = integrity.verify(snap, self.hmac_key)
        if problems:
            return None, "local_invalid"
        if self.content is not None:
            try:
                model = Snapshot.model_validate(snap)
                issues = validate_snapshot(model, self.content)
            except Exception:
                return None, "local_invalid"
            if issues:
                return None, "local_invalid"
        return snap, None

    async def sync_all(self, trigger: SyncTrigger = SyncTrigger.MANUAL) -> list[SyncOutcome]:
        _ = trigger
        if not self.logged_in:
            return [SyncOutcome(None, "skipped", reason="not_logged_in")]
        if not self.online:
            return [SyncOutcome(None, "skipped", reason="offline")]
        if is_game_running(self.lock_path):
            return [SyncOutcome(None, "skipped", reason="game_running")]

        try:
            cloud_list = await self.api.list_saves()
        except RateLimitedError:
            return [SyncOutcome(None, "skipped", reason="rate_limited")]
        except (NetworkError, AuthError, ApiError):
            return [SyncOutcome(None, "skipped", reason="server_error")]

        cloud_by_id = {item.profileID: item for item in cloud_list}
        try:
            local_profiles = (
                savestore.list_profiles(self.db_path, self.db_key) if self.db_path.exists() else []
            )
        except KeyUnavailableError:
            return [SyncOutcome(None, "skipped", reason="key_unavailable")]

        local_ids = {p["profile_id"] for p in local_profiles}
        outcomes: list[SyncOutcome] = []

        for pid in sorted(local_ids | set(cloud_by_id)):
            outcomes.append(await self._sync_one(pid, cloud_by_id.get(pid)))
        return outcomes

    async def sync_profile(self, profile_id: str, trigger: SyncTrigger = SyncTrigger.MANUAL) -> SyncOutcome:
        _ = trigger
        if not self.logged_in:
            return SyncOutcome(profile_id, "skipped", reason="not_logged_in")
        if not self.online:
            return SyncOutcome(profile_id, "skipped", reason="offline")
        if is_game_running(self.lock_path):
            return SyncOutcome(profile_id, "skipped", reason="game_running")
        try:
            cloud_list = await self.api.list_saves()
        except RateLimitedError:
            return SyncOutcome(profile_id, "skipped", reason="rate_limited")
        except (NetworkError, AuthError, ApiError):
            return SyncOutcome(profile_id, "skipped", reason="server_error")
        cloud_by_id = {item.profileID: item for item in cloud_list}
        return await self._sync_one(profile_id, cloud_by_id.get(profile_id))

    async def _sync_one(self, profile_id: str, cloud_item: Any) -> SyncOutcome:
        rec = self.state.profiles.get(profile_id)
        local_snap, skip = self._export_local(profile_id)
        if skip == "key_unavailable":
            return SyncOutcome(profile_id, "skipped", reason="key_unavailable")
        if skip == "local_invalid":
            return SyncOutcome(profile_id, "skipped", reason="local_invalid")

        # If a profile was previously deleted from cloud, don't re-upload the old save automatically,
        # UNLESS the user has made brand-new local progress (different stateHash).
        if rec and rec.cloud_deleted and cloud_item is None:
            if local_snap is not None and bool(rec.state_hash) and local_snap.get("stateHash") != rec.state_hash:
                self.state.profiles.pop(profile_id, None)
                rec = None
                self._persist()
            else:
                return SyncOutcome(profile_id, "noop")  # local_only; do not re-upload

        local = (
            LocalInfo(state_hash=local_snap["stateHash"], valid=True)
            if local_snap
            else LocalInfo(state_hash=None, valid=True)
        )
        last = (
            LastSynced(rec.revision, rec.state_hash)
            if rec and rec.revision > 0 and not rec.cloud_deleted
            else None
        )
        cloud = (
            CloudInfo(revision=cloud_item.revision, state_hash=cloud_item.stateHash)
            if cloud_item is not None
            else CloudInfo(revision=None)
        )

        # cloudDeleted: treat as no last sync for upload, and no cloud
        if rec and rec.cloud_deleted:
            if cloud_item is None:
                return SyncOutcome(profile_id, "noop")
            # cloud reappeared — clear deleted flag and classify normally
            last = None

        action = classify(local if local_snap or True else None, last, cloud)
        # refine: no local snapshot
        if local_snap is None:
            local = LocalInfo(state_hash=None, valid=True)
            action = classify(local, last, cloud)

        if action == Action.NOTHING:
            if cloud_item is not None and local_snap is not None and (rec is None or rec.revision != cloud_item.revision):
                self.state.profiles[profile_id] = ProfileSyncRecord(
                    revision=cloud_item.revision, state_hash=cloud_item.stateHash, cloud_deleted=False
                )
                self._persist()
            return SyncOutcome(profile_id, "noop")
        if action == Action.CONFLICT:
            local_sum = _summary_from_snapshot(local_snap) if local_snap else None
            cloud_sum = None
            if cloud_item is not None:
                s = cloud_item.summary
                cloud_sum = s.model_dump() if hasattr(s, "model_dump") else dict(s or {})
            return SyncOutcome(profile_id, "conflict", local_summary=local_sum, cloud_summary=cloud_sum)
        if action == Action.UPLOAD:
            assert local_snap is not None
            return await self._upload(
                profile_id, local_snap, base=rec.revision if rec and not rec.cloud_deleted else 0
            )
        if action == Action.DOWNLOAD:
            return await self._download(profile_id)
        return SyncOutcome(profile_id, "noop")

    async def _upload(self, profile_id: str, snap: dict, *, base: int) -> SyncOutcome:
        try:
            result = await self.api.put_save(profile_id, base, snap)
        except ConflictError as exc:
            if exc.state_hash == snap.get("stateHash"):
                # lost response recovery
                self.state.profiles[profile_id] = ProfileSyncRecord(
                    revision=exc.server_revision, state_hash=snap["stateHash"]
                )
                self._persist()
                return SyncOutcome(profile_id, "uploaded", revision=exc.server_revision)
            return SyncOutcome(
                profile_id,
                "conflict",
                local_summary=_summary_from_snapshot(snap),
                cloud_summary=exc.summary if isinstance(exc.summary, dict) else None,
            )
        except NetworkError:
            return SyncOutcome(profile_id, "skipped", reason="offline")
        except ApiError as exc:
            if exc.status == 404:
                self.state.profiles[profile_id] = ProfileSyncRecord(
                    revision=base,
                    state_hash=snap["stateHash"],
                    cloud_deleted=True,
                )
                self._persist()
                return SyncOutcome(profile_id, "noop")
            if isinstance(exc, RateLimitedError):
                return SyncOutcome(profile_id, "skipped", reason="rate_limited", error_message=exc.message)
            return SyncOutcome(profile_id, "skipped", reason="server_error", error_message=exc.message)

        self.state.profiles[profile_id] = ProfileSyncRecord(
            revision=result.revision, state_hash=snap["stateHash"], cloud_deleted=False
        )
        self._persist()
        return SyncOutcome(profile_id, "uploaded", revision=result.revision)

    async def _download(self, profile_id: str) -> SyncOutcome:
        try:
            data = await self.api.get_latest(profile_id)
        except RateLimitedError:
            return SyncOutcome(profile_id, "skipped", reason="rate_limited")
        except (NetworkError, ApiError):
            return SyncOutcome(profile_id, "skipped", reason="server_error")

        snap = data.get("snapshot") or {}
        problems = integrity.verify(snap, self.hmac_key)
        if problems:
            return SyncOutcome(profile_id, "skipped", reason="local_invalid")
        if self.content is not None:
            try:
                model = Snapshot.model_validate(snap)
                issues = validate_snapshot(model, self.content)
            except Exception:
                return SyncOutcome(profile_id, "skipped", reason="local_invalid")
            if issues:
                return SyncOutcome(profile_id, "skipped", reason="local_invalid")
        try:
            savestore.import_snapshot(
                self.db_path, self.db_key, snap, bak_path=self.bak_path, hmac_key=self.hmac_key
            )
        except KeyUnavailableError:
            return SyncOutcome(profile_id, "skipped", reason="key_unavailable")
        except Exception:
            log.exception("import failed")
            return SyncOutcome(profile_id, "skipped", reason="local_invalid")

        revision = int(data.get("revision") or snap.get("revisionID") or 0)
        self.state.profiles[profile_id] = ProfileSyncRecord(
            revision=revision, state_hash=snap["stateHash"], cloud_deleted=False
        )
        self._persist()
        return SyncOutcome(profile_id, "downloaded", revision=revision)

    async def resolve_conflict(
        self, profile_id: str, choice: Literal["keep_local", "keep_cloud"]
    ) -> SyncOutcome:
        if is_game_running(self.lock_path):
            return SyncOutcome(profile_id, "skipped", reason="game_running")
        if choice == "keep_cloud":
            return await self._download(profile_id)
        # keep_local: re-read cloud revision then upload
        try:
            cloud_list = await self.api.list_saves()
        except (NetworkError, ApiError):
            return SyncOutcome(profile_id, "skipped", reason="server_error")
        cloud_item = next((c for c in cloud_list if c.profileID == profile_id), None)
        base = cloud_item.revision if cloud_item else 0
        local_snap, skip = self._export_local(profile_id)
        if skip:
            return SyncOutcome(profile_id, "skipped", reason=skip)
        if local_snap is None:
            return SyncOutcome(profile_id, "skipped", reason="local_invalid")
        return await self._upload(profile_id, local_snap, base=base)

    async def download_profile(self, profile_id: str) -> SyncOutcome:
        return await self._download(profile_id)

    async def delete_cloud_profile(self, profile_id: str) -> SyncOutcome:
        try:
            await self.api.delete_save(profile_id)
        except (NetworkError, ApiError):
            return SyncOutcome(profile_id, "skipped", reason="server_error")
        rec = self.state.profiles.get(profile_id)
        if rec:
            rec.cloud_deleted = True
        else:
            self.state.profiles[profile_id] = ProfileSyncRecord(revision=0, state_hash="", cloud_deleted=True)
        self._persist()
        return SyncOutcome(profile_id, "noop")
