"""Modern top-center floating toast / popup notification modal styled after modern white cards."""

from __future__ import annotations

from enum import StrEnum

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from morsoul_launcher_ui.theme import ASSETS, get_font_family

TOAST_ASSETS = ASSETS / "toast"


class ToastType(StrEnum):
    ERROR = "error"  # Red / Danger
    SUCCESS = "success"  # Green
    WARNING = "warning"  # Amber / Warning
    INFO = "info"  # Blue / Info
    SYNC = "sync"  # Blue / Sync


def _get_icon_pixmap(kind: ToastType, size: int = 22) -> QPixmap | None:
    filename_map = {
        ToastType.ERROR: "error.png",
        ToastType.SUCCESS: "success.png",
        ToastType.WARNING: "warning.png",
        ToastType.INFO: "info.png",
        ToastType.SYNC: "info.png",
    }
    filename = filename_map.get(kind, "info.png")
    path = TOAST_ASSETS / filename
    if path.exists():
        pix = QPixmap(str(path))
        if not pix.isNull():
            return pix.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
    return None


class ToastNotification(QFrame):
    """Floating modal banner at top-center of the screen that auto-dismisses after 4-5s.
    Styled with a clean white card, soft drop shadow, colored icon asset, and subtle close button.
    """

    dismissed = Signal()

    def __init__(
        self,
        text: str,
        kind: ToastType = ToastType.INFO,
        duration_ms: int = 4500,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("toastModal")
        fonts = get_font_family()

        self.kind = kind
        self._kind = kind
        self._duration_ms = duration_ms

        # Clean white card style with colored left accent
        self.setStyleSheet("""
            QFrame#toastModal {
                background-color: #FFFFFF;
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 14px;
            }
        """)

        # Soft elevated drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 32))
        shadow.setOffset(0, 5)
        self.setGraphicsEffect(shadow)

        self.setMinimumWidth(300)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 11, 16, 11)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Icon chip / image from toast asset folder
        self.icon_chip = QLabel()
        self.icon_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_chip.setFixedSize(22, 22)
        self.icon_chip.setStyleSheet("background: transparent; border: none;")
        pix = _get_icon_pixmap(kind, size=22)
        if pix is not None:
            self.icon_chip.setPixmap(pix)
        else:
            # Fallback character
            fallback_char = "✓" if kind == ToastType.SUCCESS else ("✕" if kind == ToastType.ERROR else "ℹ")
            self.icon_chip.setText(fallback_char)
        layout.addWidget(self.icon_chip)

        # Message Label (dark text on white background)
        self.msg_label = QLabel(text)
        self.msg_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.msg_label.setStyleSheet(f"""
            QLabel {{
                color: #1F2937;
                font-size: 13.5px;
                font-weight: 500;
                background: transparent;
                border: none;
                font-family: {fonts};
            }}
        """)
        layout.addWidget(self.msg_label, stretch=1)

        # Subtle close button
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(18, 18)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip("Dismiss")
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #9CA3AF;
                font-size: 13px;
                font-weight: 500;
                padding: 0;
            }
            QPushButton:hover {
                color: #4B5563;
            }
            QPushButton:pressed {
                color: #111827;
            }
        """)
        self.close_btn.clicked.connect(self.dismiss)
        layout.addWidget(self.close_btn)

        self.adjustSize()

        # Opacity effect for smooth fading
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        # Note: can only apply one graphics effect to a widget directly in Qt;
        # if shadow is active, we animate geometry slide down!
        self.setGraphicsEffect(shadow)

        # Timer to auto-dismiss
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        if duration_ms > 0:
            self._timer.start(duration_ms)

    def set_message(self, text: str) -> None:
        self.msg_label.setText(text)
        self.adjustSize()
        if self.parentWidget():
            self._reposition()

    def update_sync_progress(self, seconds: int) -> None:
        self.set_message(f"Syncing ({seconds}s)...")

    def show_animated(self) -> None:
        self.show()
        self.raise_()
        self.adjustSize()
        self._reposition()

        # Slide-down animation from y=-50 to y=20
        target_y = 20
        start_rect = QRect(self.x(), -50, self.width(), self.height())
        target_rect = QRect(self.x(), target_y, self.width(), self.height())

        self.setGeometry(start_rect)
        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(280)
        self._anim.setStartValue(start_rect)
        self._anim.setEndValue(target_rect)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def dismiss(self) -> None:
        self._timer.stop()
        # Slide up animation
        target_rect = QRect(self.x(), -60, self.width(), self.height())
        self._anim_out = QPropertyAnimation(self, b"geometry")
        self._anim_out.setDuration(220)
        self._anim_out.setStartValue(self.geometry())
        self._anim_out.setEndValue(target_rect)
        self._anim_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim_out.finished.connect(self._on_dismiss_finished)
        self._anim_out.start()

    def _on_dismiss_finished(self) -> None:
        self.hide()
        self.dismissed.emit()
        self.deleteLater()

    def _reposition(self) -> None:
        p = self.parentWidget()
        if p is None:
            return
        pw = p.width()
        x = (pw - self.width()) // 2
        self.move(x, self.y() if self.y() > 0 else 20)


class ToastManager:
    """Manages displaying and replacing top-center floating toasts in a host widget."""

    def __init__(self, host: QWidget) -> None:
        self.host = host
        self._current: ToastNotification | None = None
        self._sync_seconds: int = 0
        self._sync_timer: QTimer | None = None

    def show(self, text: str, kind: ToastType, duration_ms: int = 4500) -> ToastNotification:
        self.stop_sync_ticker()
        if self._current is not None:
            self._current.dismiss()
            self._current = None

        toast = ToastNotification(text, kind=kind, duration_ms=duration_ms, parent=self.host)
        self._current = toast
        toast.dismissed.connect(self._on_toast_dismissed)
        toast.show_animated()
        return toast

    def show_error(self, text: str) -> ToastNotification:
        # User error mapping:
        # - wrong password - red
        # - server is not online - red
        # - user is not online - red
        norm = text.lower().strip()
        display = text
        if "wrong password" in norm or "invalid_credentials" in norm or "password incorrect" in norm:
            display = "Wrong password"
        elif "network" in norm or "connection refused" in norm or "server is not online" in norm:
            display = "Server is not online"
        elif "offline" in norm or "not signed in" in norm or "user is not online" in norm:
            display = "User is not online"
        return self.show(display, kind=ToastType.ERROR, duration_ms=4500)

    def show_success(self, text: str) -> ToastNotification:
        # User success mapping:
        # - account created - green
        # - password changed! - green
        # - signed out - green
        # - signed out of all devices - green
        norm = text.lower().strip()
        display = text
        if "account created" in norm or "registered" in norm:
            display = "Account created"
        elif "password changed" in norm:
            display = "Password changed!"
        elif "signed out of all" in norm:
            display = "Signed out of all devices"
        elif "signed out" in norm:
            display = "Signed out"
        return self.show(display, kind=ToastType.SUCCESS, duration_ms=4500)

    def show_info(self, text: str) -> ToastNotification:
        # User info/sync mapping:
        # - profile progress synced! - blue
        # - app is up to date! - blue
        norm = text.lower().strip()
        display = text
        if "progress synced" in norm or "synced!" in norm:
            display = "Profile progress synced!"
        elif "up to date" in norm:
            display = "App is up to date!"
        return self.show(display, kind=ToastType.INFO, duration_ms=4500)

    def start_sync_toast(self) -> ToastNotification:
        self.stop_sync_ticker()
        self._sync_seconds = 1
        toast = self.show(f"Syncing ({self._sync_seconds}s)...", kind=ToastType.SYNC, duration_ms=0)
        self._sync_timer = QTimer(self.host)
        self._sync_timer.setInterval(1000)
        self._sync_timer.timeout.connect(self._on_sync_tick)
        self._sync_timer.start()
        return toast

    def _on_sync_tick(self) -> None:
        self._sync_seconds += 1
        if self._current is not None:
            self._current.set_message(f"Syncing ({self._sync_seconds}s)...")

    def finish_sync_toast(self) -> None:
        self.stop_sync_ticker()
        self.show("Profile progress synced!", kind=ToastType.INFO, duration_ms=4500)

    def stop_sync_ticker(self) -> None:
        if self._sync_timer is not None:
            self._sync_timer.stop()
            self._sync_timer = None

    def _on_toast_dismissed(self) -> None:
        self._current = None

    def reposition(self) -> None:
        if self._current is not None and self._current.isVisible():
            self._current._reposition()
