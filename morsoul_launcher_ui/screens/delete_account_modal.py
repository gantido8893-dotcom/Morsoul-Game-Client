"""Modern confirmation dialog for permanent account deletion."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from morsoul_launcher_ui.theme import get_font_family

_DARK_TEXT = "#1F2937"
_MUTED_TEXT = "#6B7280"
_DANGER_RED = "#E03E3E"
_DANGER_HOVER = "#F04848"
_DANGER_PRESSED = "#C53030"
_INPUT_BORDER = "#D1D5DB"
_WHITE = "#FFFFFF"


class DeleteAccountModal(QFrame):
    """Modern popup dialog for confirming permanent account deletion."""

    confirmed = Signal(str)  # Emits entered password
    cancelled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("deleteAccountModalCard")
        self.setFixedSize(480, 310)
        fonts = get_font_family()

        # Clean white card matching theme
        self.setStyleSheet("""
            QFrame#deleteAccountModalCard {
                background-color: #FFFFFF;
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 16px;
            }
        """)

        # Soft elevated drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 50))
        shadow.setOffset(0, 8)
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        warn_badge = QLabel("⚠️")
        warn_badge.setStyleSheet("font-size: 16px; background: transparent;")
        title_row.addWidget(warn_badge)

        title = QLabel("Delete Account")
        title.setStyleSheet(f"""
            font-size: 18px;
            font-weight: 600;
            color: {_DARK_TEXT};
            font-family: {fonts};
            background: transparent;
        """)
        title_row.addWidget(title)
        title_row.addStretch()
        title_box.addLayout(title_row)

        sub_warning = QLabel("This action is permanent and cannot be undone.")
        sub_warning.setStyleSheet(f"""
            color: {_DANGER_RED};
            font-size: 12px;
            font-weight: 500;
            font-family: {fonts};
            background: transparent;
        """)
        title_box.addWidget(sub_warning)
        header.addLayout(title_box)

        header.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #9CA3AF;
                font-size: 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                color: #374151;
            }
        """)
        close_btn.clicked.connect(self._on_cancel)
        header.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        layout.addSpacing(14)

        # ── Body text ─────────────────────────────────────────────────────────
        desc = QLabel(
            "All your local progress saves, cloud backups, and account information will be permanently "
            "deleted from Morsoul servers. Please enter your password to confirm deletion:"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"""
            color: {_MUTED_TEXT};
            font-size: 12.5px;
            font-weight: 400;
            line-height: 1.45;
            background: transparent;
            font-family: {fonts};
        """)
        layout.addWidget(desc)

        layout.addSpacing(12)

        # ── Password Input ────────────────────────────────────────────────────
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Enter your current password")
        self.password_input.setFixedHeight(38)
        self.password_input.setStyleSheet(f"""
            QLineEdit {{
                background: {_WHITE};
                border: 1.5px solid {_INPUT_BORDER};
                border-radius: 10px;
                padding: 0 12px;
                color: {_DARK_TEXT};
                font-size: 13px;
                font-family: {fonts};
            }}
            QLineEdit:focus {{
                border-color: {_DANGER_RED};
            }}
        """)
        self.password_input.returnPressed.connect(self._on_confirm)
        layout.addWidget(self.password_input)

        layout.addStretch()

        # ── Buttons Row ───────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setFixedHeight(38)
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_WHITE};
                border: 1.5px solid {_INPUT_BORDER};
                border-radius: 10px;
                color: {_DARK_TEXT};
                font-size: 13px;
                font-weight: 500;
                padding: 0 20px;
                font-family: {fonts};
            }}
            QPushButton:hover {{
                background-color: #F9FAFB;
                border-color: #9CA3AF;
            }}
            QPushButton:pressed {{
                background-color: #F3F4F6;
            }}
        """)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self.cancel_btn)

        self.confirm_btn = QPushButton("Delete Account")
        self.confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.confirm_btn.setFixedHeight(38)
        self.confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_DANGER_RED};
                color: {_WHITE};
                border-radius: 10px;
                border: none;
                font-size: 13px;
                font-weight: 600;
                padding: 0 22px;
                font-family: {fonts};
            }}
            QPushButton:hover {{
                background-color: {_DANGER_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {_DANGER_PRESSED};
            }}
        """)
        self.confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(self.confirm_btn)

        layout.addLayout(btn_row)

    def clear(self) -> None:
        self.password_input.clear()

    def _on_confirm(self) -> None:
        pw = self.password_input.text()
        if not pw:
            self.password_input.setFocus()
            win = self.window()
            if hasattr(win, "toast") and win.toast is not None:
                win.toast.show_error("Please enter your password to confirm.")
            return
        self.confirmed.emit(pw)
        self.clear()

    def _on_cancel(self) -> None:
        self.clear()
        self.cancelled.emit()

