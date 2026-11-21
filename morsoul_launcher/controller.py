"""LauncherController — the only surface the UI talks to."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from morsoul_core.keystore import KeyUnavailableError, get_or_create_key
from morsoul_core.paths import game_db_bak_path, game_db_path, game_lock_path, launcher_state_path
from morsoul_launcher import strings
from morsoul_launcher.api import (
    ApiClient,
    ApiError,
    AuthError,
    NetworkError,
    RateLimitedError,
    fetch_server_url,
)
from morsoul_launcher.appstate import (
    AppState,
    AuthKind,
    GameKind,
    NetworkKind,
    ProfileView,
    SyncState,
    UpdateKind,
)
from morsoul_launcher.config import LauncherSettings
from morsoul_launcher.game import game_is_running, launch_game
from morsoul_launcher.state import load_launcher_state, save_launcher_state
from morsoul_launcher.stats import refresh_stats_cache
from morsoul_launcher.sync.engine import SyncEngine, SyncOutcome, SyncTrigger
from morsoul_launcher.tokens import MemoryTokenStore, TokenStore
from morsoul_launcher.updater import UpdateError, apply_update, check_updates

log = logging.getLogger("morsoul.launcher.controller")

StateListener = Callable[[AppState], None]


@dataclass
class Result:
    ok: bool
    message: str = ""
    code: str | None = None


class LauncherController:
    def __init__(
        self,
        settings: LauncherSettings,
        *,
        tokens: TokenStore | None = None,
        api: ApiClient | None = None,
        state_path: Path | None = None,
        db_path: Path | None = None,
        bak_path: Path | None = None,
        lock_path: Path | None = None,
        db_key: bytes | None = None,
        ranks: list[dict[str, Any]] | None = None,
    ) -> None:
        self.settings = settings
        self.tokens = tokens or MemoryTokenStore()
        self.state = AppState(server_url=settings.default_server_url)
        self._listeners: list[StateListener] = []
        self._launcher_state = load_launcher_state(state_path)
        self._state_path = state_path or launcher_state_path()
        self._db_path = db_path or game_db_path()
        self._bak_path = bak_path or game_db_bak_path()
        self._lock_path = lock_path or game_lock_path()
        self._db_key = db_key
        self._ranks = ranks or []
        self._update_cancel = False
        self._update_info: Any = None
        if not settings.server_config_url:
            self._server_url = settings.default_server_url
            self._launcher_state.server_url = self._server_url
        else:
            self._server_url = self._launcher_state.server_url or settings.default_server_url
        self.state.server_url = self._server_url

        if api is not None:
            self.api = api
        else:
            self.api = ApiClient(
                base_url=lambda: self._server_url,
                token=self.tokens.get,
                launcher_key=settings.launcher_key,
                refresh_server_config=self._refresh_server_config,
            )

    def get_state(self) -> AppState:
        return self.state

    def on_state(self, listener: StateListener) -> None:
        self._listeners.append(listener)

    def _emit(self) -> None:
        for listener in list(self._listeners):
            try:
                listener(self.state)
            except Exception:
                log.exception("state listener failed")

    def _set_error(self, message: str, code: str | None = None) -> Result:
        self.state.last_error = message
        self._emit()
        return Result(False, message, code)

    async def _refresh_server_config(self) -> str | None:
        if not self.settings.server_config_url:
            return None
        url = await fetch_server_url(self.settings.server_config_url)
        if url:
            self._server_url = url
            self.state.server_url = url
            self._launcher_state.server_url = url
            save_launcher_state(self._launcher_state, self._state_path)
            self._emit()
        return url

    def _db_key_bytes(self) -> bytes:
        if self._db_key is not None:
            return self._db_key
        return get_or_create_key()

    def _engine(self) -> SyncEngine:
        return SyncEngine(
            api=self.api,
            db_path=self._db_path,
            bak_path=self._bak_path,
            db_key=self._db_key_bytes(),
            hmac_key=self.settings.hmac_key_bytes,
            state=self._launcher_state,
            state_path=self._state_path,
            lock_path=self._lock_path,
            app_version=self.settings.app_version,
            online=self.state.network == NetworkKind.ONLINE,
            logged_in=self.state.auth.kind == AuthKind.SIGNED_IN,
        )

    def _apply_outcomes(self, outcomes: list[SyncOutcome]) -> None:
        by_id = {o.profile_id: o for o in outcomes if o.profile_id}
        for view in self.state.profiles:
            out = by_id.get(view.profile_id)
            if out is None:
                continue
            if out.kind == "conflict":
                view.sync_state = SyncState.CONFLICT
                self.state.add_banner("conflict", strings.NEEDS_ATTENTION, "warn")
            elif out.kind == "skipped" and out.reason:
                view.sync_state = SyncState.SKIPPED
                view.sync_reason = out.reason
            elif out.kind in {"uploaded", "downloaded", "noop"}:
                view.sync_state = SyncState.SYNCED
        self._emit()

    async def sign_in(self, username: str, password: str) -> Result:
        self.state.auth.kind = AuthKind.SIGNING_IN
        self.state.busy = True
        self._emit()
        try:
            session = await self.api.login(username, password)
            self.tokens.set(session.sessionToken)
            email: str | None = None
            created_at: str | None = None
            pw_changed: str | None = None
            try:
                me = await self.api.me()
                email = me.email
                created_at = me.createdAt
                pw_changed = me.passwordChangedAt
            except Exception:
                pass
            self.state.auth = type(self.state.auth)(
                kind=AuthKind.SIGNED_IN,
                user_id=session.userID,
                username=session.username,
                email=email,
                created_at=created_at,
                password_changed_at=pw_changed,
            )
            self.state.network = NetworkKind.ONLINE
            self.state.last_error = None
            self._emit()
            return Result(True)
        except RateLimitedError as exc:
            self.state.auth.kind = AuthKind.SIGNED_OUT
            return self._set_error(
                strings.friendly_error("RATE_LIMITED", retry_after=exc.retry_after), exc.code
            )
        except NetworkError:
            self.state.auth.kind = AuthKind.SIGNED_OUT
            self.state.network = NetworkKind.OFFLINE
            self.state.add_banner("offline", strings.OFFLINE_BANNER, "warn")
            return self._set_error(strings.NETWORK_ERROR, "NETWORK")
        except ApiError as exc:
            self.state.auth.kind = AuthKind.SIGNED_OUT
            return self._set_error(strings.friendly_error(exc.code, details=exc.details), exc.code)
        finally:
            self.state.busy = False
            self._emit()

    async def register(self, username: str, password: str, email: str | None = None) -> Result:
        self.state.auth.kind = AuthKind.SIGNING_IN
        self.state.busy = True
        self._emit()
        try:
            session = await self.api.register(username, password, email)
            self.tokens.set(session.sessionToken)
            self.state.auth = type(self.state.auth)(
                kind=AuthKind.SIGNED_IN,
                user_id=session.userID,
                username=session.username,
                email=email,
                created_at=datetime.now(UTC).isoformat(),
            )
            self.state.network = NetworkKind.ONLINE
            return Result(True)
        except RateLimitedError as exc:
            self.state.auth.kind = AuthKind.SIGNED_OUT
            return self._set_error(
                strings.friendly_error("RATE_LIMITED", retry_after=exc.retry_after), exc.code
            )
        except NetworkError:
            self.state.auth.kind = AuthKind.SIGNED_OUT
            return self._set_error(strings.NETWORK_ERROR, "NETWORK")
        except ApiError as exc:
            self.state.auth.kind = AuthKind.SIGNED_OUT
            return self._set_error(strings.friendly_error(exc.code, details=exc.details), exc.code)
        finally:
            self.state.busy = False
            self._emit()

    async def continue_offline(self) -> None:
        self.state.auth.kind = AuthKind.OFFLINE_MODE
        self.state.network = NetworkKind.OFFLINE
        self.state.add_banner("offline", strings.OFFLINE_BANNER, "info")
        self._emit()

    async def return_to_online(self) -> Result:
        if not self.has_internet():
            return self._set_error("Cannot switch to Online Mode: No internet access.")
        self.state.network = NetworkKind.ONLINE
        self.state.remove_banner("offline")
        token = self.tokens.get()
        if token:
            try:
                me = await self.api.me()
                self.state.auth = type(self.state.auth)(
                    kind=AuthKind.SIGNED_IN,
                    user_id=me.userID,
                    username=me.username,
                    email=me.email,
                    created_at=me.createdAt,
                    password_changed_at=me.passwordChangedAt,
                )
            except Exception:
                self.tokens.clear()
                self.state.auth = type(self.state.auth)(kind=AuthKind.SIGNED_OUT)
        else:
            self.state.auth = type(self.state.auth)(kind=AuthKind.SIGNED_OUT)
        self.state.last_error = None
        self._emit()
        return Result(True, "Switched to Online Mode")

    def has_internet(self) -> bool:
        """Quick check for raw internet connectivity (non-blocking, fast timeout)."""
        import socket

        try:
            socket.create_connection(("1.1.1.1", 443), timeout=1.0).close()
            return True
        except OSError:
            return False

    async def sign_out(self) -> None:
        try:
            if self.tokens.get():
                await self.api.logout()
        except Exception:
            pass
        self.tokens.clear()
        self.state.auth = type(self.state.auth)(kind=AuthKind.SIGNED_OUT)
        self._emit()

    async def sign_out_all(self) -> None:
        try:
            if self.tokens.get():
                await self.api.logout_all()
        except Exception:
            pass
        self.tokens.clear()
        self.state.auth = type(self.state.auth)(kind=AuthKind.SIGNED_OUT)
        self._emit()

    async def change_password(self, current: str, new: str) -> Result:
        if current == new:
            return self._set_error(strings.PASSWORD_MUST_DIFFER)
        try:
            data = await self.api.change_password(current, new)
            token = data.get("sessionToken")
            if token:
                self.tokens.set(token)
            self.state.auth.password_changed_at = datetime.now(UTC).isoformat()
            self._emit()
            return Result(True, strings.PASSWORD_CHANGED)
        except NetworkError:
            return self._set_error(strings.NETWORK_ERROR, "NETWORK")
        except ApiError as exc:
            return self._set_error(strings.friendly_error(exc.code), exc.code)

    async def delete_account(self, password: str) -> Result:
        try:
            await self.api.delete_account(password)
            self.tokens.clear()
            self.state.auth = type(self.state.auth)(kind=AuthKind.SIGNED_OUT)
            self._emit()
            return Result(True)
        except ApiError as exc:
            return self._set_error(strings.friendly_error(exc.code), exc.code)

    async def request_password_reset(self, email: str, method: str = "otp") -> Result:
        try:
            data = await self.api.request_password_reset(email, method)
            msg = data.get("message") or "Verification code sent to your email!"
            return Result(True, msg)
        except NetworkError:
            return self._set_error(strings.NETWORK_ERROR, "NETWORK")
        except ApiError as exc:
            return self._set_error(strings.friendly_error(exc.code), exc.code)

    async def reset_password(self, email: str, code: str, new_password: str) -> Result:
        try:
            data = await self.api.reset_password(email, code, new_password)
            msg = data.get("message") or "Password changed successfully."
            return Result(True, msg)
        except NetworkError:
            return self._set_error(strings.NETWORK_ERROR, "NETWORK")
        except ApiError as exc:
            return self._set_error(strings.friendly_error(exc.code), exc.code)

    async def check_updates(self) -> Any:
        self.state.update.kind = UpdateKind.CHECKING
        self._emit()
        if not self.settings.update_public_key or not self.settings.game_install_dir:
            self.state.update.kind = UpdateKind.UP_TO_DATE
            self._emit()
            return None
        try:
            raw = await self.api.updates_manifest()
            info = await check_updates(
                manifest=raw["manifest"],
                signature=raw["signature"],
                public_key_b64=self.settings.update_public_key,
                install_dir=Path(self.settings.game_install_dir),
            )
            self._update_info = info
            if info.available:
                self.state.update.kind = UpdateKind.AVAILABLE
                self.state.update.info = info
            else:
                self.state.update.kind = UpdateKind.UP_TO_DATE
            self._emit()
            return info
        except (UpdateError, NetworkError, ApiError, KeyError) as exc:
            self.state.update.kind = UpdateKind.FAILED
            self.state.update.reason = str(exc) if str(exc) else strings.UPDATE_VERIFY_FAILED
            self._emit()
            return None

    async def apply_update(self) -> Result:
        if self._update_info is None or not self.settings.game_install_dir:
            return Result(False, strings.UPDATE_FAILED)
        if game_is_running(self._lock_path):
            return Result(False, strings.GAME_RUNNING)
        self._update_cancel = False
        self.state.update.kind = UpdateKind.DOWNLOADING
        self._emit()
        staging = Path(self.settings.game_install_dir) / ".update-staging"

        def progress(_path: str, done: int, total: int) -> None:
            self.state.update.progress = (done / total) if total else 0.0
            self._emit()

        try:
            await apply_update(
                self._update_info,
                install_dir=Path(self.settings.game_install_dir),
                staging_dir=staging,
                progress=progress,
                cancelled=lambda: self._update_cancel,
            )
            self.state.update.kind = UpdateKind.UP_TO_DATE
            self._launcher_state.installed_app_version = getattr(self._update_info, "app_version", None)
            save_launcher_state(self._launcher_state, self._state_path)
            self._emit()
            return Result(True)
        except UpdateError as exc:
            self.state.update.kind = UpdateKind.FAILED
            self.state.update.reason = str(exc) or strings.UPDATE_FAILED
            self._emit()
            return Result(False, self.state.update.reason)

    def cancel_update(self) -> None:
        self._update_cancel = True

    async def refresh_profiles(self) -> None:
        views: list[ProfileView] = []
        try:
            from morsoul_core import savestore

            key = self._db_key_bytes()
            for row in savestore.list_profiles(self._db_path, key) if self._db_path.exists() else []:
                views.append(
                    ProfileView(
                        profile_id=row["profile_id"],
                        display_name=row.get("display_name") or "Player",
                        current_case_id=row.get("current_case_id"),
                        cases_completed=int(row.get("cases_completed") or 0),
                        runic_logs=int(row.get("runic_logs") or 0),
                        playtime=int(row.get("playtime") or 0),
                        last_played=row.get("updated_at"),
                        sync_state=SyncState.LOCAL_ONLY,
                    )
                )
        except KeyUnavailableError:
            self.state.add_banner("key", strings.KEY_UNAVAILABLE, "error")
        except Exception:
            log.exception("refresh_profiles local failed")

        if self.state.auth.kind == AuthKind.SIGNED_IN and self.state.network == NetworkKind.ONLINE:
            try:
                cloud = await self.api.list_saves()
                by_id = {v.profile_id: v for v in views}
                for item in cloud:
                    summary = item.summary
                    s = summary.model_dump() if hasattr(summary, "model_dump") else dict(summary or {})
                    if item.profileID in by_id:
                        v = by_id[item.profileID]
                        v.cloud_summary = s
                        v.cases_completed = int(s.get("casesCompleted") or 0)
                        v.runic_logs = int(s.get("runicLogs") or 0)
                    else:
                        views.append(
                            ProfileView(
                                profile_id=item.profileID,
                                display_name=item.displayName,
                                current_case_id=s.get("currentCaseID"),
                                cases_completed=int(s.get("casesCompleted") or 0),
                                runic_logs=int(s.get("runicLogs") or 0),
                                playtime=int(s.get("playtime") or 0),
                                sync_state=SyncState.CLOUD_ONLY,
                                cloud_summary=s,
                            )
                        )
                    rec = self._launcher_state.profiles.get(item.profileID)
                    if rec and rec.cloud_deleted:
                        by_id.get(item.profileID)
            except (NetworkError, ApiError):
                pass
        self.state.profiles = views
        self._emit()

    async def sync_all(self, trigger: SyncTrigger = SyncTrigger.MANUAL) -> list[SyncOutcome]:
        for p in self.state.profiles:
            p.sync_state = SyncState.SYNCING
        self._emit()
        try:
            outcomes = await self._engine().sync_all(trigger)
        except KeyUnavailableError:
            self.state.add_banner("key", strings.KEY_UNAVAILABLE, "error")
            outcomes = []
        await self.refresh_profiles()
        self._apply_outcomes(outcomes)
        return outcomes

    async def sync_profile(self, profile_id: str, trigger: SyncTrigger = SyncTrigger.MANUAL) -> SyncOutcome:
        out = await self._engine().sync_profile(profile_id, trigger)
        await self.refresh_profiles()
        self._apply_outcomes([out])
        return out

    async def resolve_conflict(
        self, profile_id: str, choice: Literal["keep_local", "keep_cloud"]
    ) -> SyncOutcome:
        out = await self._engine().resolve_conflict(profile_id, choice)
        await self.refresh_profiles()
        self._apply_outcomes([out])
        return out

    async def download_profile(self, profile_id: str) -> SyncOutcome:
        out = await self._engine().download_profile(profile_id)
        await self.refresh_profiles()
        self._apply_outcomes([out])
        return out

    async def delete_cloud_profile(self, profile_id: str) -> Result:
        out = await self._engine().delete_cloud_profile(profile_id)
        await self.refresh_profiles()
        return Result(out.kind != "skipped", out.reason or "")

    async def load_history(self, profile_id: str) -> list[dict[str, Any]]:
        try:
            return await self.api.history(profile_id)
        except (NetworkError, ApiError):
            return []

    def launch_game(self) -> Result:
        r = launch_game(self.settings.game_exe_path, lock_path=self._lock_path)
        self.state.game = (
            GameKind.RUNNING if game_is_running(self._lock_path) or r.ok else GameKind.NOT_RUNNING
        )
        self._emit()
        if r.ok:
            self._watch_game_exit()
        return Result(r.ok, r.message)

    def _watch_game_exit(self) -> None:
        """Poll for game.lock removal in a background thread and reset state."""
        import threading

        def _poll() -> None:
            import time

            while game_is_running(self._lock_path):
                time.sleep(2)
            self.state.game = GameKind.NOT_RUNNING
            self._emit()

        t = threading.Thread(target=_poll, name="game-exit-watcher", daemon=True)
        t.start()

    def is_game_running(self) -> bool:
        running = game_is_running(self._lock_path)
        self.state.game = GameKind.RUNNING if running else GameKind.NOT_RUNNING
        return running

    def set_setting_toggle(self, key: str, value: bool) -> None:
        if hasattr(self._launcher_state, key):
            setattr(self._launcher_state, key, value)
            save_launcher_state(self._launcher_state, self._state_path)

    def reset_server_url(self) -> str:
        self._server_url = self.settings.default_server_url
        self._launcher_state.server_url = self._server_url
        save_launcher_state(self._launcher_state, self._state_path)
        self.state.server_url = self._server_url
        self._emit()
        return self._server_url

    def export_user_data(self, out_path: Path | str | None = None) -> Path:
        import json
        import time
        from datetime import datetime

        from morsoul_core.paths import data_dir

        profiles = []
        if self._db_path.exists():
            try:
                from morsoul_core import savestore

                profiles = savestore.list_profiles(self._db_path, self._db_key_bytes())
            except Exception:
                pass

        data = {
            "app": "Morsoul: World's Case",
            "version": self.settings.app_version,
            "username": self.state.auth.username,
            "email": self.state.auth.email,
            "profiles": profiles,
            "exportedAt": datetime.now(UTC).isoformat(),
        }

        if out_path is None:
            downloads = Path.home() / "Downloads"
            if not downloads.exists():
                downloads = data_dir()
            out_path = downloads / f"morsoul_backup_{int(time.time())}.json"
        else:
            out_path = Path(out_path)

        out_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return out_path

    async def on_launcher_open(self) -> None:
        if self.settings.server_config_url:
            url = await fetch_server_url(self.settings.server_config_url)
            if url:
                self._server_url = url
                self._launcher_state.server_url = url
                save_launcher_state(self._launcher_state, self._state_path)
            elif self._launcher_state.server_url:
                self._server_url = self._launcher_state.server_url
            self.state.server_url = self._server_url
            self._emit()
        else:
            self._server_url = self.settings.default_server_url
            self.state.server_url = self._server_url
            self._launcher_state.server_url = self._server_url
            save_launcher_state(self._launcher_state, self._state_path)
            self._emit()

        token = self.tokens.get()
        if token:
            try:
                me = await self.api.me()
                self.state.auth = type(self.state.auth)(
                    kind=AuthKind.SIGNED_IN,
                    user_id=me.userID,
                    username=me.username,
                    email=me.email,
                    created_at=me.createdAt,
                    password_changed_at=me.passwordChangedAt,
                )
                self.state.network = NetworkKind.ONLINE
            except AuthError:
                self.tokens.clear()
                self.state.auth = type(self.state.auth)(kind=AuthKind.SIGNED_OUT)
            except NetworkError:
                self.state.network = NetworkKind.OFFLINE
                self.state.add_banner("offline", strings.OFFLINE_BANNER, "warn")
        self._emit()
        if getattr(self._launcher_state, "check_updates_on_start", True):
            await self.check_updates()
        if self.state.auth.kind == AuthKind.SIGNED_IN:
            if getattr(self._launcher_state, "sync_on_launcher_open", True):
                await self.sync_all(SyncTrigger.OPEN)
            await refresh_stats_cache(self.api)
        await self.refresh_profiles()

    async def on_launcher_close(self) -> None:
        if self.state.auth.kind != AuthKind.SIGNED_IN:
            return
        if not getattr(self._launcher_state, "sync_on_game_close", True):
            return
        try:
            import asyncio

            await asyncio.wait_for(self.sync_all(SyncTrigger.CLOSE), timeout=5.0)
        except Exception:
            pass
