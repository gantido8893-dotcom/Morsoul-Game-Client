"""Modern Forgot Password modal supporting Email OTP and Email Verification flows."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from morsoul_launcher_ui.theme import get_font_family

_GOLD = "#CBA344"
_GOLD_HOVER = "#E0BA58"
_DARK_TEXT = "#1F2937"
_MUTED_TEXT = "#6B7280"
_SUBTLE_TEXT = "#9CA3AF"
_INPUT_BORDER = "#D1D5DB"
_INPUT_FOCUS = "#CBA344"
_WHITE = "#FFFFFF"
_BG = "#FFFFFF"


class ForgotPasswordModal(QFrame):
    """Modern recovery modal with Email OTP and Email Verification tabs."""

    reset_success = Signal(str)  # Emits success message
    reset_failed = Signal(str)  # Emits error message
    send_code_requested = Signal(str, str)  # (email, method: "otp" | "link")
    reset_requested = Signal(str, str, str)  # (email, code, new_pw)
    notify_error = Signal(str)
    notify_success = Signal(str)
    notify_info = Signal(str)
    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("forgotPasswordCard")
        self.setFixedSize(500, 430)
        fonts = get_font_family()

        self._countdown: int = 0
        self._target_btn: QPushButton | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

        # Clean white card
        self.setStyleSheet(f"""
            QFrame#forgotPasswordCard {{
                background-color: {_BG};
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 16px;
            }}
        """)

        # Soft drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 50))
        shadow.setOffset(0, 8)
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("Password Recovery")
        title.setStyleSheet(f"""
            color: {_DARK_TEXT};
            font-size: 18px;
            font-weight: 600;
            font-family: {fonts};
            background: transparent;
        """)
        title_box.addWidget(title)

        subtitle = QLabel("Choose your preferred recovery method below")
        subtitle.setStyleSheet(f"""
            color: {_MUTED_TEXT};
            font-size: 12.5px;
            font-weight: 400;
            font-family: {fonts};
            background: transparent;
        """)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)

        header.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #9CA3AF;
                font-size: 15px;
                font-weight: 500;
            }
            QPushButton:hover {
                color: #374151;
            }
        """)
        close_btn.clicked.connect(self.closed.emit)
        header.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        layout.addSpacing(18)

        # ── Method Tab Toggle Bar ─────────────────────────────────────────────
        tab_bar = QFrame()
        tab_bar.setStyleSheet("""
            QFrame {
                background-color: #F3F4F6;
                border-radius: 10px;
                border: none;
            }
        """)
        tab_bar.setFixedHeight(40)
        tb_layout = QHBoxLayout(tab_bar)
        tb_layout.setContentsMargins(4, 4, 4, 4)
        tb_layout.setSpacing(4)

        self.tab_otp_btn = QPushButton("Email OTP Code")
        self.tab_otp_btn.setCheckable(True)
        self.tab_otp_btn.setChecked(True)
        self.tab_otp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tab_otp_btn.clicked.connect(lambda: self._select_tab(0))

        self.tab_link_btn = QPushButton("Email Verification Link")
        self.tab_link_btn.setCheckable(True)
        self.tab_link_btn.setChecked(False)
        self.tab_link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tab_link_btn.clicked.connect(lambda: self._select_tab(1))

        self._apply_tab_styles()
        tb_layout.addWidget(self.tab_otp_btn)
        tb_layout.addWidget(self.tab_link_btn)
        layout.addWidget(tab_bar)

        layout.addSpacing(18)

        # ── Stacked Pages for Methods ─────────────────────────────────────────
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: transparent; border: none;")

        # Page 0: OTP Form
        self.page_otp = self._build_otp_page(fonts)
        self.stack.addWidget(self.page_otp)

        # Page 1: Verification Link Form
        self.page_link = self._build_link_page(fonts)
        self.stack.addWidget(self.page_link)

        layout.addWidget(self.stack)

        # Hidden status label kept for back-compatibility
        self.status_lbl = QLabel("")
        self.status_lbl.setVisible(False)

    def _apply_tab_styles(self) -> None:
        fonts = get_font_family()
        active = f"""
            QPushButton {{
                background-color: {_WHITE};
                color: {_DARK_TEXT};
                font-weight: 600;
                font-size: 12.5px;
                border-radius: 7px;
                border: none;
                padding: 0 4px;
                font-family: {fonts};
            }}
        """
        inactive = f"""
            QPushButton {{
                background-color: transparent;
                color: {_MUTED_TEXT};
                font-weight: 500;
                font-size: 12.5px;
                border-radius: 7px;
                border: none;
                padding: 0 4px;
                font-family: {fonts};
            }}
            QPushButton:hover {{
                color: {_DARK_TEXT};
            }}
        """
        self.tab_otp_btn.setStyleSheet(active if self.tab_otp_btn.isChecked() else inactive)
        self.tab_link_btn.setStyleSheet(active if self.tab_link_btn.isChecked() else inactive)

    def _select_tab(self, idx: int) -> None:
        self.tab_otp_btn.setChecked(idx == 0)
        self.tab_link_btn.setChecked(idx == 1)
        self._apply_tab_styles()
        self.stack.setCurrentIndex(idx)

    def _show_toast_error(self, message: str) -> None:
        self.notify_error.emit(message)
        win = self.window()
        if hasattr(win, "toast") and win.toast is not None:
            win.toast.show_error(message)

    def _show_toast_success(self, message: str) -> None:
        self.notify_success.emit(message)
        win = self.window()
        if hasattr(win, "toast") and win.toast is not None:
            win.toast.show_success(message)

    def _show_toast_info(self, message: str) -> None:
        self.notify_info.emit(message)
        win = self.window()
        if hasattr(win, "toast") and win.toast is not None:
            win.toast.show_info(message)

    # ── Page 0: Email OTP ─────────────────────────────────────────────────────

    def _build_otp_page(self, fonts: str) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        input_css = f"""
            QLineEdit {{
                background: {_WHITE};
                border: 1.5px solid {_INPUT_BORDER};
                border-radius: 10px;
                padding: 0 14px;
                color: {_DARK_TEXT};
                font-size: 13px;
                font-weight: 400;
                min-height: 40px;
                font-family: {fonts};
            }}
            QLineEdit:focus {{
                border-color: {_INPUT_FOCUS};
            }}
            QLineEdit::placeholder {{
                color: {_SUBTLE_TEXT};
            }}
        """

        # Row 1: Email + Send OTP button
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.otp_email = QLineEdit()
        self.otp_email.setPlaceholderText("Enter your account email")
        self.otp_email.setStyleSheet(input_css)
        row1.addWidget(self.otp_email, stretch=1)

        self.otp_send_btn = QPushButton("Send Code")
        self.otp_send_btn.setFixedHeight(40)
        self.otp_send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.otp_send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #F3F4F6;
                border: 1.5px solid {_INPUT_BORDER};
                border-radius: 10px;
                color: {_DARK_TEXT};
                font-weight: 600;
                font-size: 12.5px;
                padding: 0 18px;
                font-family: {fonts};
            }}
            QPushButton:hover {{
                background-color: #E5E7EB;
            }}
            QPushButton:pressed {{
                background-color: #D1D5DB;
            }}
            QPushButton:disabled {{
                color: {_SUBTLE_TEXT};
                background-color: #F9FAFB;
            }}
        """)
        self.otp_send_btn.clicked.connect(self._send_otp)
        row1.addWidget(self.otp_send_btn)
        lay.addLayout(row1)

        # Row 2: 6-Digit OTP Code
        self.otp_code = QLineEdit()
        self.otp_code.setPlaceholderText("Enter 6-digit OTP code")
        self.otp_code.setStyleSheet(input_css)
        lay.addWidget(self.otp_code)

        # Row 3: New Password
        self.otp_new_pw = QLineEdit()
        self.otp_new_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.otp_new_pw.setPlaceholderText("New password")
        self.otp_new_pw.setStyleSheet(input_css)
        lay.addWidget(self.otp_new_pw)

        # Row 4: Confirm Password
        self.otp_confirm_pw = QLineEdit()
        self.otp_confirm_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.otp_confirm_pw.setPlaceholderText("Confirm new password")
        self.otp_confirm_pw.setStyleSheet(input_css)
        lay.addWidget(self.otp_confirm_pw)

        lay.addSpacing(4)

        # Submit button
        self.otp_submit_btn = QPushButton("Reset Password with OTP")
        self.otp_submit_btn.setFixedHeight(42)
        self.otp_submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.otp_submit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_DARK_TEXT};
                color: {_WHITE};
                font-weight: 600;
                font-size: 13.5px;
                border-radius: 10px;
                border: none;
                font-family: {fonts};
            }}
            QPushButton:hover {{
                background-color: #374151;
            }}
            QPushButton:pressed {{
                background-color: #111827;
            }}
        """)
        self.otp_submit_btn.clicked.connect(self._submit_otp_reset)
        lay.addWidget(self.otp_submit_btn)

        lay.addStretch()
        return page

    # ── Page 1: Email Verification Link ───────────────────────────────────────

    def _build_link_page(self, fonts: str) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        input_css = f"""
            QLineEdit {{
                background: {_WHITE};
                border: 1.5px solid {_INPUT_BORDER};
                border-radius: 10px;
                padding: 0 14px;
                color: {_DARK_TEXT};
                font-size: 13px;
                font-weight: 400;
                min-height: 40px;
                font-family: {fonts};
            }}
            QLineEdit:focus {{
                border-color: {_INPUT_FOCUS};
            }}
            QLineEdit::placeholder {{
                color: {_SUBTLE_TEXT};
            }}
        """

        # Row 1: Email + Send link button
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.link_email = QLineEdit()
        self.link_email.setPlaceholderText("Enter your account email")
        self.link_email.setStyleSheet(input_css)
        row1.addWidget(self.link_email, stretch=1)

        self.link_send_btn = QPushButton("Send Link")
        self.link_send_btn.setFixedHeight(40)
        self.link_send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.link_send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #F3F4F6;
                border: 1.5px solid {_INPUT_BORDER};
                border-radius: 10px;
                color: {_DARK_TEXT};
                font-weight: 600;
                font-size: 12.5px;
                padding: 0 18px;
                font-family: {fonts};
            }}
            QPushButton:hover {{
                background-color: #E5E7EB;
            }}
            QPushButton:pressed {{
                background-color: #D1D5DB;
            }}
            QPushButton:disabled {{
                color: {_SUBTLE_TEXT};
                background-color: #F9FAFB;
            }}
        """)
        self.link_send_btn.clicked.connect(self._send_link)
        row1.addWidget(self.link_send_btn)
        lay.addLayout(row1)

        # Row 2: Verification Token
        self.link_token = QLineEdit()
        self.link_token.setPlaceholderText("Paste verification token from email")
        self.link_token.setStyleSheet(input_css)
        lay.addWidget(self.link_token)

        # Row 3: New Password
        self.link_new_pw = QLineEdit()
        self.link_new_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.link_new_pw.setPlaceholderText("New password")
        self.link_new_pw.setStyleSheet(input_css)
        lay.addWidget(self.link_new_pw)

        # Row 4: Confirm Password
        self.link_confirm_pw = QLineEdit()
        self.link_confirm_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.link_confirm_pw.setPlaceholderText("Confirm new password")
        self.link_confirm_pw.setStyleSheet(input_css)
        lay.addWidget(self.link_confirm_pw)

        lay.addSpacing(4)

        # Submit button
        self.link_submit_btn = QPushButton("Verify & Reset Password")
        self.link_submit_btn.setFixedHeight(42)
        self.link_submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.link_submit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_DARK_TEXT};
                color: {_WHITE};
                font-weight: 600;
                font-size: 13.5px;
                border-radius: 10px;
                border: none;
                font-family: {fonts};
            }}
            QPushButton:hover {{
                background-color: #374151;
            }}
            QPushButton:pressed {{
                background-color: #111827;
            }}
        """)
        self.link_submit_btn.clicked.connect(self._submit_link_reset)
        lay.addWidget(self.link_submit_btn)

        lay.addStretch()
        return page

    # ── Actions ───────────────────────────────────────────────────────────────

    def _send_otp(self) -> None:
        email = self.otp_email.text().strip()
        if not email or "@" not in email:
            self._show_toast_error("Please enter a valid email address.")
            return

        self._start_countdown(self.otp_send_btn)
        self._show_toast_info(f"Sending OTP code to {email}...")
        self.send_code_requested.emit(email, "otp")

    def _send_link(self) -> None:
        email = self.link_email.text().strip()
        if not email or "@" not in email:
            self._show_toast_error("Please enter a valid email address.")
            return

        self._start_countdown(self.link_send_btn)
        self._show_toast_info(f"Sending verification link to {email}...")
        self.send_code_requested.emit(email, "link")

    def _start_countdown(self, btn: QPushButton) -> None:
        self._countdown = 30
        self._target_btn = btn
        self._target_btn.setEnabled(False)
        self._target_btn.setText(f"{self._countdown}s")
        self._timer.start()

    def _on_tick(self) -> None:
        self._countdown -= 1
        if self._countdown <= 0:
            self._timer.stop()
            if self._target_btn is not None:
                self._target_btn.setEnabled(True)
                self._target_btn.setText("Resend")
        else:
            if self._target_btn is not None:
                self._target_btn.setText(f"{self._countdown}s")

    def on_code_sent(self, msg: str = "Verification code sent to your email!") -> None:
        self._show_toast_success(msg)

    def on_code_failed(self, error_msg: str) -> None:
        self._timer.stop()
        if self._target_btn is not None:
            self._target_btn.setEnabled(True)
            self._target_btn.setText("Send")
        self._show_toast_error(error_msg)

    def _submit_otp_reset(self) -> None:
        email = self.otp_email.text().strip()
        code = self.otp_code.text().strip()
        pw = self.otp_new_pw.text()
        cpw = self.otp_confirm_pw.text()

        if not email or "@" not in email:
            self._show_toast_error("Please enter a valid email address.")
            return
        if not code:
            self._show_toast_error("Please enter the 6-digit OTP code.")
            return
        if len(pw) < 8:
            self._show_toast_error("Password must be at least 8 characters.")
            return
        if pw != cpw:
            self._show_toast_error("Passwords do not match.")
            return

        self.reset_requested.emit(email, code, pw)

    def _submit_link_reset(self) -> None:
        email = self.link_email.text().strip()
        tok = self.link_token.text().strip()
        pw = self.link_new_pw.text()
        cpw = self.link_confirm_pw.text()

        if not email or "@" not in email:
            self._show_toast_error("Please enter a valid email address.")
            return
        if not tok:
            self._show_toast_error("Please enter the verification token.")
            return
        if len(pw) < 8:
            self._show_toast_error("Password must be at least 8 characters.")
            return
        if pw != cpw:
            self._show_toast_error("Passwords do not match.")
            return

        self.reset_requested.emit(email, tok, pw)
