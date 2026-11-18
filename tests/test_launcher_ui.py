"""UI tests with a fake controller (milestone M7). Screens must not import ApiClient/savestore."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from morsoul_launcher import strings
from morsoul_launcher.appstate import (
    AppState,
    AuthKind,
    AuthState,
    NetworkKind,
    UpdateKind,
    UpdateState,
)
from morsoul_launcher.controller import Result
from morsoul_launcher.strings import friendly_error

UI_ROOT = Path(__file__).resolve().parents[1] / "morsoul_launcher_ui"


def test_ui_does_not_import_api_or_savestore() -> None:
    forbidden = {"morsoul_launcher.api", "morsoul_core.savestore", "morsoul_launcher.sync"}
    for path in UI_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in forbidden, f"{path} imports {alias.name}"
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module not in forbidden, f"{path} imports {node.module}"
                for part in forbidden:
                    assert not node.module.startswith(part + "."), f"{path} imports {node.module}"


def test_error_string_map_complete() -> None:
    for code in (
        "INVALID_CREDENTIALS",
        "USERNAME_TAKEN",
        "EMAIL_TAKEN",
        "VALIDATION_ERROR",
        "RATE_LIMITED",
        "INVALID_SESSION",
        "WRONG_PASSWORD",
        "NETWORK",
        "REVISION_CONFLICT",
        "FORBIDDEN_PROFILE",
        "INVALID_SAVE",
        "PAYLOAD_TOO_LARGE",
        "MANIFEST_INVALID",
        "key_unavailable",
        "local_invalid",
    ):
        msg = friendly_error(code, retry_after=3)
        assert msg
        assert "snapshot" not in msg.lower()
        assert "revision" not in msg.lower() or code == "REVISION_CONFLICT"


@pytest.mark.parametrize(
    "kind,expect",
    [
        (AuthKind.SIGNED_OUT, "Online Mode"),
        (AuthKind.SIGNED_IN, "Online Mode"),
    ],
)
def test_home_render_chips(qtbot, kind, expect) -> None:
    pytest.importorskip("PySide6")
    from morsoul_launcher_ui.screens.home import HomeScreen

    home = HomeScreen()
    qtbot.addWidget(home)
    state = AppState(auth=AuthState(kind=kind), update=UpdateState(kind=UpdateKind.UP_TO_DATE))
    home.render_state(state)
    assert home.sync_chip.text() == expect
    assert home.update_chip.text() == strings.UP_TO_DATE

    # In offline mode, chip says "Offline Mode", top pill has message, and empty banner container is hidden
    offline_state = AppState(
        auth=AuthState(kind=AuthKind.OFFLINE_MODE),
        update=UpdateState(kind=UpdateKind.UP_TO_DATE),
    )
    home.render_state(offline_state)
    assert home.sync_chip.text() == "Offline Mode"
    assert home.update_chip.text() == "You are offline. You can still play."
    assert home.banner.isHidden()


def test_auth_modal_login_signal(qtbot) -> None:
    from morsoul_launcher_ui.screens.auth_modal import AuthModal

    modal = AuthModal()
    qtbot.addWidget(modal)
    modal.user.setText("alice")
    modal.password.setText("password12")
    with qtbot.waitSignal(modal.login_requested, timeout=1000) as blocker:
        modal.submit.click()
    assert blocker.args == ["alice", "password12"]


def test_result_ok_shape() -> None:
    assert Result(True).ok is True


def test_account_screen_frame3_frame5(qtbot) -> None:
    from morsoul_launcher.appstate import ProfileView
    from morsoul_launcher_ui.screens.account import AccountOverlay

    account = AccountOverlay()
    qtbot.addWidget(account)

    # Frame 3: Synced progress
    state_synced = AppState(
        auth=AuthState(
            kind=AuthKind.SIGNED_IN,
            username="User Sample 1",
            email="sampleuser@samplemail.com",
            created_at="2026-11-05T00:00:00Z",
            password_changed_at="2026-11-06T00:00:00Z",
        ),
        profiles=[
            ProfileView(
                profile_id="p1",
                display_name="Ibn Al-haytham",
                playtime=12 * 3600 + 3 * 60,
                cases_completed=2,
                runic_logs=2,
            )
        ],
    )
    account.render_state(state_synced)
    assert account._dark_overlay is not None
    assert account._title_bar is not None
    assert account.min_btn.objectName() == "winBtn"
    assert account.close_btn.objectName() == "winCloseBtn"
    assert account.username_header.text() == "User Sample 1"
    assert account.email_header.text() == "sampleuser@samplemail.com"
    assert account.avatar_label.text() == "U"
    assert account.val_username.text() == "User Sample 1"
    assert account.val_email.text() == "sampleuser@samplemail.com"
    assert account.val_profile_name.text() == "Ibn Al-haytham"
    assert "12 Hrs" in account.val_playtime.text()
    assert account.val_cases_solved.text() == "2/6"
    assert account.val_runic_logs.text() == "2/4"

    # Frame 5: No synced progress
    state_empty = AppState(
        auth=AuthState(
            kind=AuthKind.SIGNED_IN,
            username="User Sample 1",
            email="sampleuser@samplemail.com",
            created_at="2026-11-05T00:00:00Z",
        ),
        profiles=[],
    )
    account.render_state(state_empty)
    assert account.val_profile_name.text() == "---"
    assert account.val_playtime.text() == "---"
    assert account.val_cases_solved.text() == "---"
    assert account.val_runic_logs.text() == "---"
    assert account.val_last_synced.text() == "No synced data yet"


def test_toast_notification_manager(qtbot) -> None:
    from PySide6.QtWidgets import QWidget

    from morsoul_launcher_ui.toast import ToastManager, ToastType

    host = QWidget()
    qtbot.addWidget(host)
    host.resize(800, 600)
    mgr = ToastManager(host)

    # Red error cases – white card design with icon assets (no per-type background color)
    for err in ("wrong password", "server is not online", "user is not online"):
        toast = mgr.show_error(err)
        assert toast.kind == ToastType.ERROR
        assert "#FFFFFF" in toast.styleSheet()

    # Green success cases
    for succ in ("account created", "password changed!", "signed out", "signed out of all devices"):
        toast = mgr.show_success(succ)
        assert toast.kind == ToastType.SUCCESS
        assert "#FFFFFF" in toast.styleSheet()

    # Blue info/sync cases
    for info in ("profile progress synced!", "app is up to date!", "syncing 5s"):
        toast = mgr.show_info(info)
        assert toast.kind in (ToastType.INFO, ToastType.SYNC)
        assert "#FFFFFF" in toast.styleSheet()


def test_forgot_password_modal(qtbot) -> None:
    from morsoul_launcher_ui.screens.forgot_password_modal import ForgotPasswordModal

    modal = ForgotPasswordModal()
    qtbot.addWidget(modal)
    assert modal.tab_otp_btn.text() == "Email OTP Code"
    assert modal.tab_link_btn.text() == "Email Verification Link"

    # Validation errors emit toast notify_error
    with qtbot.waitSignal(modal.notify_error, timeout=1000):
        modal.otp_email.setText("")
        modal.otp_send_btn.click()

    # Valid email emits send_code_requested
    with qtbot.waitSignal(modal.send_code_requested, timeout=1000) as blocker:
        modal.otp_email.setText("user@example.com")
        modal.otp_send_btn.click()
    assert blocker.args == ["user@example.com", "otp"]

    modal.otp_code.setText("123456")
    modal.otp_new_pw.setText("newpassword123")
    modal.otp_confirm_pw.setText("newpassword123")
    assert modal.otp_submit_btn.isEnabled()

    # Submit emits reset_requested
    with qtbot.waitSignal(modal.reset_requested, timeout=1000) as blocker:
        modal.otp_submit_btn.click()
    assert blocker.args == ["user@example.com", "123456", "newpassword123"]


def test_offline_modal(qtbot) -> None:
    from morsoul_launcher_ui.screens.offline_modal import OfflineConfirmationModal

    modal = OfflineConfirmationModal()
    qtbot.addWidget(modal)
    with qtbot.waitSignal(modal.confirmed, timeout=1000):
        modal.confirm_btn.click()


def test_delete_account_modal(qtbot) -> None:
    from morsoul_launcher_ui.screens.delete_account_modal import DeleteAccountModal

    modal = DeleteAccountModal()
    qtbot.addWidget(modal)
    assert modal.width() == 480
    assert modal.height() == 310

    # Entering password and confirming emits password
    modal.password_input.setText("secretpassword")
    with qtbot.waitSignal(modal.confirmed, timeout=1000) as blocker:
        modal.confirm_btn.click()
    assert blocker.args == ["secretpassword"]

    # Cancel clears password and emits cancelled
    modal.password_input.setText("anotherpassword")
    with qtbot.waitSignal(modal.cancelled, timeout=1000):
        modal.cancel_btn.click()
    assert modal.password_input.text() == ""


def test_sign_out_all_modal(qtbot) -> None:
    from morsoul_launcher_ui.screens.sign_out_all_modal import SignOutAllModal

    modal = SignOutAllModal()
    qtbot.addWidget(modal)
    assert modal.width() == 460
    assert modal.height() == 250

    with qtbot.waitSignal(modal.confirmed, timeout=1000):
        modal.confirm_btn.click()

    with qtbot.waitSignal(modal.cancelled, timeout=1000):
        modal.cancel_btn.click()


def test_progress_overlay_mock_profiles_and_switch(qtbot) -> None:
    from morsoul_launcher.appstate import AppState, AuthKind, AuthState
    from morsoul_launcher.profile_service import get_mock_profiles
    from morsoul_launcher_ui.screens.progress import ProgressOverlay

    progress = ProgressOverlay()
    qtbot.addWidget(progress)
    assert progress.width() == 680
    assert progress.height() == 520
    assert "#FFFFFF" in progress.styleSheet()

    # Provide mock profiles explicitly (no auto-loading)
    offline_state = AppState(
        auth=AuthState(kind=AuthKind.OFFLINE_MODE, username="Offline Player"),
        profiles=get_mock_profiles(),
    )
    progress.render_state(offline_state)

    # 3 mock profile rows rendered
    assert progress.list_layout.count() >= 3

    # Test switch profile signal
    with qtbot.waitSignal(progress.switch_profile, timeout=1000) as blocker:
        progress.switch_profile.emit("prof_doyle")
    assert blocker.args == ["prof_doyle"]

    # Empty state shows empty message (not hidden by render_state)
    empty_state = AppState(auth=AuthState(kind=AuthKind.OFFLINE_MODE, username="Offline Player"))
    progress.render_state(empty_state)
    assert not progress.empty.isHidden()


def test_account_settings_privacy_about_tabs(qtbot) -> None:
    from PySide6.QtWidgets import QScrollArea

    from morsoul_launcher_ui.screens.account import AccountOverlay

    account = AccountOverlay()
    qtbot.addWidget(account)
    state = AppState(auth=AuthState(kind=AuthKind.SIGNED_IN, username="Tester"))
    account.render_state(state)

    # Notification text defaults to "No new notifications or updates"
    assert account.val_notification.text() == "No new notifications or updates"

    # Settings subpage aligns to 410px width matching profile middle card, server address hidden
    assert account.settings_card.width() == 410
    assert account.settings_card.height() == 365
    assert not account.server_lbl.isVisible()
    assert account.settings_subpage.findChild(QScrollArea) is None

    # Privacy subpage dual-cards layout (410 + 440)
    assert account.privacy_sec_card.width() == 410
    assert account.privacy_cloud_card.width() == 440
    assert account.privacy_subpage.findChild(QScrollArea) is None

    # About subpage dual-cards layout (410 + 440)
    assert account.about_game_card.width() == 410
    assert account.about_credits_card.width() == 440
    assert account.about_subpage.findChild(QScrollArea) is None



def test_controller_has_internet_method() -> None:
    """Controller exposes has_internet() for connectivity check."""
    import base64

    from morsoul_launcher.config import LauncherSettings
    from morsoul_launcher.controller import LauncherController
    settings = LauncherSettings(
        default_server_url="http://127.0.0.1:8080",
        launcher_key="test_key",
        save_hmac_key=base64.b64encode(b"0" * 32).decode(),
    )
    ctrl = LauncherController(settings)
    # Method exists and returns a bool
    result = ctrl.has_internet()
    assert isinstance(result, bool)


def test_offline_mode_nav_and_sync(qtbot) -> None:
    """In offline mode, clicking profile icon keeps icon unhighlighted; chip toggles offline/online mode."""
    from morsoul_launcher_ui.screens.home import HomeScreen

    home = HomeScreen()
    qtbot.addWidget(home)

    offline_state = AppState(
        auth=AuthState(kind=AuthKind.OFFLINE_MODE),
        network=NetworkKind.OFFLINE,
    )
    home.render_state(offline_state)

    # In offline mode, clicking profile icon keeps icon_holder unchecked and home_btn checked
    with qtbot.waitSignal(home.account_clicked, timeout=1000):
        home.icon_holder.click()
    assert not home.icon_holder.isChecked()
    assert home.home_btn.isChecked()

    # Clicking bottom chip emits sync_chip_clicked
    with qtbot.waitSignal(home.sync_chip_clicked, timeout=1000):
        home.sync_chip.clicked.emit()
