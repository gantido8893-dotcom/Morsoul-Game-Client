"""Modern confirmation dialog for signing out of all devices."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from morsoul_launcher_ui.theme import get_font_family

_DARK_TEXT = "#1F2937"
_MUTED_TEXT = "#6B7280"
_INPUT_BORDER = "#D1D5DB"
_WHITE = "#FFFFFF"


class SignOutAllModal(QFrame):
    """Modern popup dialog for confirming signing out of all devices."""

    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("signOutAllModalCard")
        self.setFixedSize(460, 250)
        fonts = get_font_family()

        # Clean white card matching theme
        self.setStyleSheet("""
            QFrame#signOutAllModalCard {
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

        icon = QLabel("📱")
        icon.setStyleSheet("font-size: 20px; background: transparent;")
        header.addWidget(icon)

        title = QLabel("Sign Out of All Devices")
        title.setStyleSheet(f"""
            font-size: 17px;
            font-weight: 600;
            color: {_DARK_TEXT};
            font-family: {fonts};
            background: transparent;
        """)
        header.addWidget(title)
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
        close_btn.clicked.connect(self.cancelled.emit)
        header.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        layout.addSpacing(14)

        # ── Body text ─────────────────────────────────────────────────────────
        desc = QLabel(
            "Are you sure you want to log out on all devices? You will be signed out of this launcher "
            "and all other active sessions across your computers. You will need to enter your credentials "
            "to log back in."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"""
            color: {_MUTED_TEXT};
            font-size: 13px;
            font-weight: 400;
            line-height: 1.5;
            background: transparent;
            font-family: {fonts};
        """)
        layout.addWidget(desc)

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
        self.cancel_btn.clicked.connect(self.cancelled.emit)
        btn_row.addWidget(self.cancel_btn)

        self.confirm_btn = QPushButton("Sign Out All Devices")
        self.confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.confirm_btn.setFixedHeight(38)
        self.confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_DARK_TEXT};
                color: {_WHITE};
                border-radius: 10px;
                border: none;
                font-size: 13px;
                font-weight: 600;
                padding: 0 22px;
                font-family: {fonts};
            }}
            QPushButton:hover {{
                background-color: #374151;
            }}
            QPushButton:pressed {{
                background-color: #111827;
            }}
        """)
        self.confirm_btn.clicked.connect(self.confirmed.emit)
        btn_row.addWidget(self.confirm_btn)

        layout.addLayout(btn_row)

