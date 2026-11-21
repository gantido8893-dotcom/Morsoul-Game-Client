"""Fixed-size frameless launcher window shell matching mockup."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from morsoul_core.paths import data_dir
from morsoul_launcher.appstate import AppState, AuthKind
from morsoul_launcher.controller import Result
from morsoul_launcher_ui.bridge import ControllerBridge
from morsoul_launcher_ui.screens.account import AccountOverlay
from morsoul_launcher_ui.screens.auth_modal import AuthModal
from morsoul_launcher_ui.screens.delete_account_modal import DeleteAccountModal
from morsoul_launcher_ui.screens.forgot_password_modal import ForgotPasswordModal
from morsoul_launcher_ui.screens.home import HomeScreen
from morsoul_launcher_ui.screens.offline_modal import OfflineConfirmationModal
from morsoul_launcher_ui.screens.progress import ProgressOverlay
from morsoul_launcher_ui.screens.sign_out_all_modal import SignOutAllModal
from morsoul_launcher_ui.theme import WINDOW_H, WINDOW_W, get_font_family, stylesheet
from morsoul_launcher_ui.toast import ToastManager


class MainWindow(QMainWindow):
    def __init__(self, bridge: ControllerBridge) -> None:
        super().__init__()
        self.bridge = bridge
        self.setWindowTitle("Morsoul: World's Case")
        self.setFixedSize(WINDOW_W, WINDOW_H)
        self.setStyleSheet(stylesheet())

        # Frameless window matching mockup
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self._drag_pos: QPoint | None = None

        self._root = QWidget()
        self.setCentralWidget(self._root)

        # Full-screen pages stack: 0 = Home, 1 = Auth (Frame 2), 2 = Account (Frame 3)
        self._stack = QStackedLayout(self._root)
        self._stack.setStackingMode(QStackedLayout.StackingMode.StackOne)

        self.home = HomeScreen()
        self.auth = AuthModal()
        self.account = AccountOverlay()

        self._stack.addWidget(self.home)  # Index 0
        self._stack.addWidget(self.auth)  # Index 1
        self._stack.addWidget(self.account)  # Index 2

        # Semi-transparent backdrop overlay host for dialogs (Progress, Forgot PW, Offline confirm)
        self._overlay_host = QWidget(self._root)
        self._overlay_host.setObjectName("overlayHost")
        self._overlay_host.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._overlay_host.setStyleSheet("background: rgba(0, 0, 0, 0.58);")

        self.progress = ProgressOverlay(self._overlay_host)
        self.progress.hide()

        self.forgot_modal = ForgotPasswordModal(self._overlay_host)
        self.forgot_modal.hide()

        self.offline_modal = OfflineConfirmationModal(self._overlay_host)
        self.offline_modal.hide()

        self.delete_modal = DeleteAccountModal(self._overlay_host)
        self.delete_modal.hide()

        self.sign_out_all_modal = SignOutAllModal(self._overlay_host)
        self.sign_out_all_modal.hide()

        self._overlay_host.hide()

        # Toast manager for modern top-center popup notifications
        self.toast = ToastManager(self)

        self._wire()
        bridge.state_changed.connect(self._on_state)
        bridge.call_finished.connect(self._on_finished)
        bridge.call_failed.connect(self._on_failed)

    def _wire(self) -> None:
        # Home screen
        self.home.minimize_clicked.connect(self.showMinimized)
        self.home.close_clicked.connect(self.close)
        self.home.check_updates.connect(lambda: self.bridge.call_async("check_updates"))
        self.home.sync_clicked.connect(self._on_sync_clicked)
        self.home.launch_clicked.connect(lambda: self.bridge.call("launch_game"))
        self.home.account_clicked.connect(self._show_account)
        self.home.sync_chip_clicked.connect(self._on_bottom_chip_clicked)
        self.home.progress_clicked.connect(self._show_progress)

        # Auth screen (Frame 2)
        self.auth.minimize_clicked.connect(self.showMinimized)
        self.auth.close_clicked.connect(self.close)
        self.auth.login_requested.connect(lambda u, p: self.bridge.call_async("sign_in", u, p))
        self.auth.register_requested.connect(lambda u, p, e: self.bridge.call_async("register", u, p, e))
        self.auth.offline_requested.connect(self._show_offline_modal)
        self.auth.forgot_password_requested.connect(self._show_forgot_modal)
        self.auth.closed.connect(self._show_home)

        # Forgot password modal
        self.forgot_modal.closed.connect(self._hide_overlays)
        self.forgot_modal.reset_success.connect(self._on_forgot_pw_success)
        self.forgot_modal.notify_error.connect(self.toast.show_error)
        self.forgot_modal.notify_success.connect(self.toast.show_success)
        self.forgot_modal.notify_info.connect(self.toast.show_info)
        self.forgot_modal.send_code_requested.connect(
            lambda email, method: self.bridge.call_async("request_password_reset", email, method)
        )
        self.forgot_modal.reset_requested.connect(
            lambda email, code, new_pw: self.bridge.call_async("reset_password", email, code, new_pw)
        )

        # Offline confirmation modal
        self.offline_modal.cancelled.connect(self._hide_overlays)
        self.offline_modal.confirmed.connect(self._on_offline_confirmed)

        # Delete account modal
        self.delete_modal.cancelled.connect(self._hide_overlays)
        self.delete_modal.confirmed.connect(self._on_delete_account_confirmed)

        # Sign out all devices modal
        self.sign_out_all_modal.cancelled.connect(self._hide_overlays)
        self.sign_out_all_modal.confirmed.connect(self._on_sign_out_all_confirmed)

        # Account screen (Frame 3)
        self.account.minimize_clicked.connect(self.showMinimized)
        self.account.close_clicked.connect(self.close)
        self.account.closed.connect(self._show_home)
        self.account.check_updates.connect(lambda: self.bridge.call_async("check_updates"))
        self.account.sign_out.connect(lambda: self.bridge.call_async("sign_out"))
        self.account.sign_out_all.connect(self._show_sign_out_all_modal)
        self.account.request_sign_out_all.connect(self._show_sign_out_all_modal)
        self.account.switch_profile_clicked.connect(self._show_progress)
        self.account.change_password.connect(
            lambda cur, new: self.bridge.call_async("change_password", cur, new)
        )
        self.account.change_email.connect(
            lambda pw, email: self.bridge.call_async("change_email", pw, email)
        )
        self.account.setting_toggled.connect(lambda k, v: self.bridge.controller.set_setting_toggle(k, v))
        self.account.reset_server_url.connect(self._on_reset_server_url)
        self.account.download_data.connect(self._on_download_data)
        self.account.delete_account.connect(self._show_delete_modal)
        self.account.request_delete_account.connect(self._show_delete_modal)
        self.account.delete_cloud.connect(lambda pid: self.bridge.call_async("delete_cloud_profile", pid))
        self.account.view_update_log.connect(self._show_update_log_modal)
        self.account.view_client_log.connect(self._show_client_log_modal)

        # Progress / conflict dialog
        self.progress.closed.connect(self._hide_overlays)
        self.progress.sync_all.connect(self._on_sync_clicked)
        self.progress.sync_one.connect(self._on_sync_one)
        self.progress.download.connect(lambda pid: self.bridge.call_async("download_profile", pid))
        self.progress.delete_cloud.connect(lambda pid: self.bridge.call_async("delete_cloud_profile", pid))
        self.progress.resolve.connect(
            lambda pid, choice: self.bridge.call_async("resolve_conflict", pid, choice)
        )
        self.progress.switch_profile.connect(self._on_switch_profile)

    # ── Window dragging ───────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._layout_overlays()
        self.toast.reposition()

    def _layout_overlays(self) -> None:
        self._overlay_host.setGeometry(0, 0, self.width(), self.height())
        for widget in (
            self.progress,
            self.forgot_modal,
            self.offline_modal,
            self.delete_modal,
            self.sign_out_all_modal,
        ):
            if widget.isVisible():
                widget.adjustSize()
                px = (self.width() - widget.width()) // 2
                py = max(12, (self.height() - widget.height()) // 2)
                widget.move(px, py)

    # ── Navigation / Screen switching ─────────────────────────────────────────

    def _fade_to_page(self, target: QWidget) -> None:
        if self._stack.currentWidget() == target:
            return
        self._stack.setCurrentWidget(target)

        effect = QGraphicsOpacityEffect(target)
        target.setGraphicsEffect(effect)

        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _on_finished():
            target.setGraphicsEffect(None) # type: ignore

        anim.finished.connect(_on_finished)
        anim.start()
        self._page_fade_anim = anim

    def _show_home(self) -> None:
        self._hide_overlays()
        self.home.home_btn.setChecked(True)
        self.home.icon_holder.setChecked(False)
        self._fade_to_page(self.home)

    def _show_auth(self) -> None:
        self._hide_overlays()
        self.auth.clear()
        self._fade_to_page(self.auth)

    def _show_account(self) -> None:
        self._hide_overlays()
        state = self.bridge.controller.state

        # Offline mode: block profile access with warning & ensure home stays selected
        if state.auth.kind == AuthKind.OFFLINE_MODE:
            self._show_home()
            self.toast.show_error("You are offline. Connect to the internet to access your account.")
            return

        if state.auth.kind not in {AuthKind.SIGNED_IN, AuthKind.OFFLINE_MODE}:
            # Not signed in — check internet first
            if not self.bridge.controller.has_internet():
                self._show_home()
                self.toast.show_error("You are offline. Connect to the internet to sign in.")
                return
            # Has internet (even if server is down) -> show auth screen
            self._show_auth()
            return
        # Signed in -> show Frame 3 Account screen
        self.account.render_state(state)
        self._fade_to_page(self.account)

    def _show_progress(self) -> None:
        self.progress.render_state(self.bridge.controller.state)
        self._show_overlay_widget(self.progress)

    def _show_forgot_modal(self) -> None:
        self._show_overlay_widget(self.forgot_modal)

    def _show_offline_modal(self) -> None:
        self._show_overlay_widget(self.offline_modal)

    def _show_delete_modal(self) -> None:
        self.delete_modal.clear()
        self._show_overlay_widget(self.delete_modal)

    def _show_sign_out_all_modal(self) -> None:
        self._show_overlay_widget(self.sign_out_all_modal)

    def _show_overlay_widget(self, w: QWidget) -> None:
        for widget in (
            self.progress,
            self.forgot_modal,
            self.offline_modal,
            self.delete_modal,
            self.sign_out_all_modal,
        ):
            widget.hide()
        self._overlay_host.show()
        self._overlay_host.raise_()
        w.show()
        w.raise_()
        self._layout_overlays()
        self._animate_modal_entrance(w)

    def _animate_modal_entrance(self, w: QWidget) -> None:
        target_pos = w.pos()
        start_pos = QPoint(target_pos.x(), target_pos.y() + 16)
        w.move(start_pos)

        anim = QPropertyAnimation(w, b"pos", self)
        anim.setDuration(220)
        anim.setStartValue(start_pos)
        anim.setEndValue(target_pos)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._modal_anim = anim

    def _hide_overlays(self) -> None:
        for widget in (
            self.progress,
            self.forgot_modal,
            self.offline_modal,
            self.delete_modal,
            self.sign_out_all_modal,
        ):
            widget.hide()
        self._overlay_host.hide()

    def show_auth_if_needed(self) -> None:
        pass

    # ── Action Handlers ───────────────────────────────────────────────────────

    def _on_sync_clicked(self) -> None:
        state = self.bridge.controller.state
        if state.auth.kind == AuthKind.OFFLINE_MODE or state.network.value == "offline":
            self.toast.show_error("Syncing is unavailable in offline mode.")
            return
        if state.auth.kind != AuthKind.SIGNED_IN:
            self.toast.show_error("Sign in to sync your progress.")
            return
        self.toast.start_sync_toast()
        self.bridge.call_async("sync_all")

    def _on_sync_one(self, profile_id: str) -> None:
        state = self.bridge.controller.state
        if state.auth.kind == AuthKind.OFFLINE_MODE or state.network.value == "offline":
            self.toast.show_error("Syncing is unavailable in offline mode.")
            return
        if state.auth.kind != AuthKind.SIGNED_IN:
            self.toast.show_error("Sign in to sync your progress.")
            return
        self.toast.start_sync_toast()
        self.bridge.call_async("sync_profile", profile_id)

    def _on_bottom_chip_clicked(self) -> None:
        state = self.bridge.controller.state
        if state.auth.kind == AuthKind.OFFLINE_MODE or state.network.value == "offline":
            self.bridge.call_async("return_to_online")
        else:
            self._show_offline_modal()

    def _on_offline_confirmed(self) -> None:
        self._hide_overlays()
        self.toast.show_error("User is not online")
        self.bridge.call_async("continue_offline")

    def _on_delete_account_confirmed(self, password: str) -> None:
        self._hide_overlays()
        self.bridge.call_async("delete_account", password)

    def _on_sign_out_all_confirmed(self) -> None:
        self._hide_overlays()
        self.bridge.call_async("sign_out_all")

    def _on_switch_profile(self, profile_id: str) -> None:
        state = self.bridge.controller.state
        if not state.profiles:
            self.toast.show_error("No profiles available")
            return

        found_name = profile_id
        for idx, p in enumerate(state.profiles):
            if p.profile_id == profile_id:
                found_name = p.display_name or p.profile_id
                active_p = state.profiles.pop(idx)
                state.profiles.insert(0, active_p)
                break

        self.progress.render_state(state)
        if self._stack.currentWidget() == self.account:
            self.account.render_state(state)
        self.toast.show_success(f"Switched to profile: {found_name}")

    def _on_forgot_pw_success(self, msg: str) -> None:
        self._hide_overlays()
        self.toast.show_success("Password changed!")

    def _on_reset_server_url(self) -> None:
        url = self.bridge.controller.reset_server_url()
        self.account.server_lbl.setText(url)
        self.toast.show_info("App is up to date!")

    def _on_download_data(self) -> None:
        try:
            path = self.bridge.controller.export_user_data()
            self.toast.show_success(f"Data exported to {path.name}!")
        except Exception as exc:
            self.toast.show_error(f"Export failed: {exc}")

    def _show_update_log_modal(self) -> None:
        fonts = get_font_family()
        dlg = QDialog(self)
        dlg.setWindowTitle("Update Log")
        dlg.setFixedSize(540, 380)
        dlg.setStyleSheet("""
            QDialog {
                background-color: #1A1A1C;
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 14px;
            }
        """)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        t = QLabel("Morsoul Client Changelog")
        t.setStyleSheet(f"color: #CBA344; font-size: 16px; font-weight: 700; font-family: {fonts};")
        lay.addWidget(t)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        host = QWidget()
        host.setStyleSheet("background: transparent;")
        h_lay = QVBoxLayout(host)
        h_lay.setSpacing(10)

        logs = [
            (
                "v0.1.0 — Current Release",
                "• Encrypted local SQLCipher save store (game.db) with PBKDF2 HMAC keys\n"
                "• Profile view with dual Frame 3 and Frame 5 dynamic progress rendering\n"
                "• Multi-device cloud synchronization with conflict resolution\n"
                "• Modern notification toasts, offline security, and recovery modals\n"
                "• Standalone single-file Windows binary packaging support",
            ),
            (
                "v0.0.9 — Beta",
                "• Added account authentication and secure token storage\n"
                "• Initial Agartha Case 1 and Case 2 investigation log schemas",
            ),
        ]
        for ver, note in logs:
            box = QWidget()
            b_lay = QVBoxLayout(box)
            b_lay.setContentsMargins(0, 0, 0, 0)
            b_lay.setSpacing(3)
            vl = QLabel(ver)
            vl.setStyleSheet(f"color: #FFFFFF; font-size: 13px; font-weight: 700; font-family: {fonts};")
            nl = QLabel(note)
            nl.setStyleSheet(f"color: #AAAAAA; font-size: 12px; line-height: 1.4; font-family: {fonts};")
            b_lay.addWidget(vl)
            b_lay.addWidget(nl)
            h_lay.addWidget(box)

        h_lay.addStretch()
        scroll.setWidget(host)
        lay.addWidget(scroll)

        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedHeight(34)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #CBA344;
                color: #1A1600;
                font-size: 12px;
                font-weight: 700;
                border-radius: 6px;
                border: none;
                font-family: {fonts};
            }}
        """)
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn)
        dlg.exec()

    def _show_client_log_modal(self) -> None:
        fonts = get_font_family()
        log_dir = data_dir() / "launcher"
        log_file = log_dir / "launcher.log"
        content = "No log entries found yet."
        if log_file.exists():
            try:
                lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
                content = "\n".join(lines[-40:]) if lines else content
            except Exception:
                pass

        dlg = QDialog(self)
        dlg.setWindowTitle("Client Log")
        dlg.setFixedSize(560, 400)
        dlg.setStyleSheet("""
            QDialog {
                background-color: #1A1A1C;
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 14px;
            }
        """)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        t = QLabel("Client Log Output")
        t.setStyleSheet(f"color: #CBA344; font-size: 16px; font-weight: 700; font-family: {fonts};")
        lay.addWidget(t)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        host = QLabel(content)
        host.setWordWrap(True)
        host.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px; color: #CCCCCC; background: #121214; padding: 10px; border-radius: 6px;"
        )
        scroll.setWidget(host)
        lay.addWidget(scroll)

        btn_row = QHBoxLayout()
        open_folder_btn = QPushButton("Open Logs Folder")
        open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_folder_btn.setFixedHeight(34)
        open_folder_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 6px;
                color: #FFFFFF;
                font-size: 12px;
                font-weight: 600;
                padding: 0 16px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.16);
            }
        """)
        open_folder_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir))))
        btn_row.addWidget(open_folder_btn)

        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedHeight(34)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #CBA344;
                color: #1A1600;
                font-size: 12px;
                font-weight: 700;
                border-radius: 6px;
                border: none;
                padding: 0 20px;
                font-family: {fonts};
            }}
        """)
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)
        dlg.exec()

    # ── State / Results bridge callbacks ──────────────────────────────────────

    def _on_state(self, state: AppState) -> None:
        self.home.render_state(state)
        if self._stack.currentWidget() == self.account:
            self.account.render_state(state)
        if self.progress.isVisible():
            self.progress.render_state(state)
        self.auth.set_busy(state.busy)

    def _on_finished(self, name: str, result: object) -> None:
        if name == "sign_in" and isinstance(result, Result):
            if result.ok:
                self._show_home()
            else:
                self.auth.set_error(result.message)
                self.toast.show_error(result.message)
                self._show_auth()

        if name == "register" and isinstance(result, Result):
            if result.ok:
                self.toast.show_success("Account created")
                self._show_home()
            else:
                self.auth.set_error(result.message)
                self.toast.show_error(result.message)
                self._show_auth()

        if name == "change_password" and isinstance(result, Result):
            msg = "Password changed" if result.ok else result.message
            self.account.set_message(msg, ok=result.ok)
            if result.ok:
                self.toast.show_success("Password changed")
            else:
                self.toast.show_error(result.message)

        if name == "change_email" and isinstance(result, Result):
            self.account.set_email_message(result.message, ok=result.ok)
            if result.ok:
                self.toast.show_success("Email updated!")
            else:
                self.toast.show_error(result.message)

        if name == "sign_out":
            self.toast.show_success("Signed out")
            self._show_home()

        if name == "sign_out_all":
            self.toast.show_success("Signed out of all devices")
            self._show_home()

        if name == "delete_account" and isinstance(result, Result):
            if result.ok:
                self.toast.show_success("Signed out of all devices")
                self._show_home()
            else:
                self.toast.show_error(result.message)

        if name in {"sync_all", "sync_profile"}:
            self.toast.stop_sync_ticker()
            outcomes: list[Any] = result if isinstance(result, list) else ([result] if result is not None else [])
            skipped_reasons = {getattr(o, "reason", None) for o in outcomes if getattr(o, "kind", None) == "skipped"}

            if "offline" in skipped_reasons or "server_error" in skipped_reasons:
                self.toast.show_error("Sync failed: Server is offline")
            elif "not_logged_in" in skipped_reasons:
                self.toast.show_error("Sign in to sync your progress.")
            elif "game_running" in skipped_reasons:
                self.toast.show_error("Cannot sync while game is running")
            elif "key_unavailable" in skipped_reasons:
                self.toast.show_error("Database key is unavailable")
            elif any(getattr(o, "kind", None) in {"uploaded", "downloaded"} for o in outcomes):
                self.toast.show_info("Profile progress synced!")
                self.bridge.call_async("refresh_profiles")
            elif any(getattr(o, "kind", None) == "conflict" for o in outcomes):
                self.toast.show_info("Sync conflict detected")
            else:
                self.toast.show_info("App is up to date!")

        if name == "delete_cloud_profile" and isinstance(result, Result):
            if result.ok:
                self.toast.show_info("Profile progress synced!")
                self.bridge.call_async("refresh_profiles")
            else:
                self.toast.show_error(result.message)

        if name == "check_updates":
            self.toast.show_info("App is up to date!")

        if name == "continue_offline":
            self._show_home()

        if name == "return_to_online" and isinstance(result, Result):
            if result.ok:
                self.toast.show_success("Switched to Online Mode")
            else:
                self.toast.show_error(result.message)

        if name == "request_password_reset" and isinstance(result, Result):
            if result.ok:
                msg = result.message or "Verification code sent to your email!"
                self.toast.show_success(msg)
                self.forgot_modal.on_code_sent(msg)
            else:
                self.toast.show_error(result.message)
                self.forgot_modal.on_code_failed(result.message)

        if name == "reset_password" and isinstance(result, Result):
            if result.ok:
                self._hide_overlays()
                self.toast.show_success("Password changed!")
            else:
                self.toast.show_error(result.message)

    def _on_failed(self, name: str, message: str) -> None:
        if name in {"sign_in", "register"}:
            self.auth.set_error(message)
            self._show_auth()
        if name == "request_password_reset":
            self.forgot_modal.on_code_failed(message)
        if name == "return_to_online":
            self.toast.show_error(message)
            return
        self.toast.show_error(message)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.bridge.call_async("on_launcher_close")
        event.accept()
