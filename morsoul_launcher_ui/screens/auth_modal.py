"""Sign in / register full screen matching Frame 2 mockup."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from morsoul_launcher_ui.theme import ASSETS, get_font_family

_GOLD = "#E9D088"
_GOLD_HOVER = "#E0BA58"
_GOLD_PRESSED = "#9E7B28"


class AuthModal(QWidget):
    """Full-screen auth interface matching Frame 2 mockup."""

    login_requested = Signal(str, str)
    register_requested = Signal(str, str, object)
    offline_requested = Signal()
    forgot_password_requested = Signal()
    closed = Signal()  # Emitted on "Return to Home" or window close
    minimize_clicked = Signal()
    close_clicked = Signal()
    resized = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("authRoot")
        self._mode = "login"
        fonts = get_font_family()

        # ── Background layer ──────────────────────────────────────────────────
        self._bg = QFrame(self)
        self._bg.setObjectName("authBgFrame")
        self._apply_bg()

        # ── Dark gradient / vignette over left half ───────────────────────────
        self._gradient = QFrame(self)
        self._gradient.setObjectName("authGradientOverlay")
        self._gradient.setStyleSheet(
            "QFrame#authGradientOverlay {"
            "  background: qlineargradient("
            "    x1:0, y1:0, x2:1, y2:0,"
            "    stop:0.0  rgba(10, 10, 10, 0.90),"
            "    stop:0.40 rgba(12, 12, 12, 0.84),"
            "    stop:0.55 rgba(15, 15, 15, 0.52),"
            "    stop:0.72 rgba(18, 18, 18, 0.40),"
            "    stop:0.82 rgba(18, 18, 18, 0.20),"
            "    stop:0.90 rgba(18, 18, 18, 0.10),"
            "    stop:1.0  rgba(0, 0, 0, 0.0)"
            "  );"
            "}"
        )

        # ── Top bar with window controls ──────────────────────────────────────
        self._top_bar = QWidget(self)
        self._top_bar.setStyleSheet("background: transparent;")
        tb = QHBoxLayout(self._top_bar)
        tb.setContentsMargins(0, 10, 16, 0)
        tb.setSpacing(4)
        tb.addStretch()

        self.min_btn = QPushButton("—")
        self.min_btn.setObjectName("winBtn")
        self.min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.min_btn.setToolTip("Minimize")
        self.min_btn.clicked.connect(self.minimize_clicked.emit)
        tb.addWidget(self.min_btn)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("winCloseBtn")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip("Close")
        self.close_btn.clicked.connect(self.close_clicked.emit)
        tb.addWidget(self.close_btn)

        # ── Back button (Top left, matching Frame 2 mockup) ────────────────────
        self.back_btn = QPushButton(self)
        self.back_btn.setObjectName("authBackBtn")
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.setFixedSize(36, 36)
        self.back_btn.setToolTip("Back to Home")
        back_icon_path = ASSETS / "button_icons" / "back.png"
        if back_icon_path.exists():
            pix = QPixmap(str(back_icon_path))
            self.back_btn.setIcon(QIcon(pix))
            self.back_btn.setIconSize(QSize(20, 20))
        else:
            self.back_btn.setText("〈")
        self.back_btn.setStyleSheet("""
            QPushButton#authBackBtn {
                background: transparent;
                border: none;
                border-radius: 18px;
                padding: 0;
            }
            QPushButton#authBackBtn:hover {
                background: rgba(255, 255, 255, 0.12);
            }
            QPushButton#authBackBtn:pressed {
                background: rgba(255, 255, 255, 0.06);
            }
        """)
        self.back_btn.clicked.connect(self.closed.emit)

        # ── Left form container ───────────────────────────────────────────────
        self._form_card = QWidget(self)
        self._form_card.setFixedWidth(360)
        self._form_card.setStyleSheet("background: transparent;")

        fc_layout = QVBoxLayout(self._form_card)
        fc_layout.setContentsMargins(0, 0, 0, 0)
        fc_layout.setSpacing(5)
        fc_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Emblem Icon (Compass/Eye)
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent;")
        icon_path = ASSETS / "game_icon.png"
        if icon_path.exists():
            pix = QPixmap(str(icon_path)).scaled(
                52,
                52,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.icon_label.setPixmap(pix)
        fc_layout.addWidget(self.icon_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        fc_layout.addSpacing(6)

        # Title: "Welcome Back"
        self.title_label = QLabel("Welcome Back")
        self.title_label.setObjectName("authTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet(f"""
            QLabel#authTitle {{
                color: {_GOLD};
                font-size: 28px;
                font-weight: 600;
                letter-spacing: 0.5px;
                background: transparent;
                font-family: {fonts};
            }}
        """)
        fc_layout.addWidget(self.title_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Subtitle
        self.subtitle_label = QLabel("Sign in to access your launcher and\nsync your progress online")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setStyleSheet(f"""
            color: #9C988F;
            font-size: 13px;
            font-weight: 400;
            line-height: 1.3;
            background: transparent;
            font-family: {fonts};
        """)
        fc_layout.addWidget(self.subtitle_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        fc_layout.addSpacing(18)

        # ── Form Inputs Container with robust spacing ─────────────────────────
        inputs_widget = QWidget()
        inputs_widget.setStyleSheet("background: transparent;")
        self._inputs_layout = QVBoxLayout(inputs_widget)
        self._inputs_layout.setContentsMargins(0, 0, 0, 0)
        self._inputs_layout.setSpacing(18)
        self._inputs_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        input_style = f"""
            QLineEdit {{
                background: rgba(20, 22, 26, 0.60);
                border: 1px solid rgba(255, 255, 255, 0.20);
                border-radius: 8px;
                color: #F0EDE6;
                font-weight: 500;
                font-size: 14px;
                padding: 0 16px;
                font-family: {fonts};
            }}
            QLineEdit:focus {{
                border: 1px solid #CBA344;
                background: rgba(20, 22, 26, 0.85);
            }}
            QLineEdit::placeholder {{
                color: rgba(255, 255, 255, 0.38);
                font-size: 14px;
            }}
        """

        # Username input
        self.user = QLineEdit()
        self.user.setObjectName("authUsernameInput")
        self.user.setPlaceholderText("Username")
        self.user.setFixedHeight(44)
        self.user.setFixedWidth(280)
        self.user.setStyleSheet(input_style)
        self._inputs_layout.addWidget(self.user, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Email input (shown in register mode)
        self.email = QLineEdit()
        self.email.setObjectName("authEmailInput")
        self.email.setPlaceholderText("Email (optional)")
        self.email.setFixedHeight(44)
        self.email.setFixedWidth(280)
        self.email.setStyleSheet(input_style)
        self.email.hide()
        self._inputs_layout.addWidget(self.email, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Password input
        self.password = QLineEdit()
        self.password.setObjectName("authPasswordInput")
        self.password.setPlaceholderText("Password")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setFixedHeight(44)
        self.password.setFixedWidth(280)
        self.password.setStyleSheet(input_style)
        self._inputs_layout.addWidget(self.password, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Confirm password input (shown in register mode)
        self.password2 = QLineEdit()
        self.password2.setObjectName("authPassword2Input")
        self.password2.setPlaceholderText("Confirm Password")
        self.password2.setEchoMode(QLineEdit.EchoMode.Password)
        self.password2.setFixedHeight(44)
        self.password2.setFixedWidth(280)
        self.password2.setStyleSheet(input_style)
        self.password2.hide()
        self._inputs_layout.addWidget(self.password2, alignment=Qt.AlignmentFlag.AlignHCenter)

        fc_layout.addWidget(inputs_widget, alignment=Qt.AlignmentFlag.AlignHCenter)

        # "Forgot Password?" link row (centered)
        self.forgot_row = QWidget()
        self.forgot_row.setFixedWidth(280)
        self.forgot_row.setStyleSheet("background: transparent;")
        fr_layout = QHBoxLayout(self.forgot_row)
        fr_layout.setContentsMargins(0, 4, 0, 6)
        fr_layout.addStretch()

        fc_layout.addSpacing(5)
        self.forgot_btn = QPushButton("Forgot Password?")
        self.forgot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.forgot_btn.setFlat(True)
        self.forgot_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: #5C7CBF;
                font-size: 12px;
                font-weight: 500;
                font-family: {fonts};
            }}
            QPushButton:hover {{
                color: #7898DB;
                text-decoration: underline;
            }}
        """)
        self.forgot_btn.clicked.connect(self.forgot_password_requested.emit)
        fr_layout.addWidget(self.forgot_btn)
        fc_layout.addWidget(self.forgot_row, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Error label
        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setStyleSheet(
            "color: #FF6B6B; font-size: 12px; background: transparent; padding: 2px 0;"
        )
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        fc_layout.addWidget(self.error_label)

        # "Log In" / "Register" Button
        fc_layout.addSpacing(10)
        self.submit = QPushButton("Log In")
        self.submit.setObjectName("authSubmitBtn")
        self.submit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit.setFixedHeight(46)
        self.submit.setFixedWidth(280)
        self.submit.setStyleSheet(f"""
            QPushButton#authSubmitBtn {{
                background-color: #CBA344;
                color: #171204;
                font-size: 15px;
                font-weight: 600;
                border-radius: 8px;
                padding: 0 16px;
                border: none;
                font-family: {fonts};
                letter-spacing: 0.3px;
            }}
            QPushButton#authSubmitBtn:hover {{
                background-color: #DBB552;
            }}
            QPushButton#authSubmitBtn:pressed {{
                background-color: #B58F2E;
            }}
            QPushButton#authSubmitBtn:disabled {{
                background: rgba(80, 72, 54, 0.40);
                color: rgba(180, 170, 150, 0.40);
                border: none;
            }}
        """)
        self.submit.clicked.connect(self._on_submit)
        fc_layout.addWidget(self.submit, alignment=Qt.AlignmentFlag.AlignHCenter)
        fc_layout.addSpacing(16)

        # "Don't have an account? Register Here" footer row
        self.toggle_row = QWidget()
        self.toggle_row.setStyleSheet("background: transparent;")
        tr_layout = QHBoxLayout(self.toggle_row)
        tr_layout.setContentsMargins(0, 0, 0, 0)
        tr_layout.setSpacing(4)
        tr_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.toggle_prefix = QLabel("Don't have an account?")
        self.toggle_prefix.setStyleSheet(
            f"color: #A09C94; font-size: 13px; background: transparent; font-family: {fonts};"
        )
        tr_layout.addWidget(self.toggle_prefix)

        self.toggle_btn = QPushButton("Register Here")
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.setFlat(True)
        self.toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: #5C7CBF;
                font-size: 13px;
                font-weight: 500;
                font-family: {fonts};
            }}
            QPushButton:hover {{
                color: #7898DB;
                text-decoration: underline;
            }}
        """)
        self.toggle_btn.clicked.connect(self._toggle_mode)
        tr_layout.addWidget(self.toggle_btn)
        fc_layout.addWidget(self.toggle_row)

        # Offline option (subtle)
        self.offline_btn = QPushButton("Play Offline")
        self.offline_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.offline_btn.setFlat(True)
        self.offline_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: rgba(255, 255, 255, 0.35);
                font-size: 12px;
                margin-top: 6px;
                font-family: {fonts};
            }}
            QPushButton:hover {{
                color: rgba(255, 255, 255, 0.70);
            }}
        """)
        self.offline_btn.clicked.connect(self.offline_requested.emit)
        fc_layout.addWidget(self.offline_btn, alignment=Qt.AlignmentFlag.AlignHCenter)

        # ── Bottom right status pill ("Log In" / "Register") ──────────────────
        self.return_home_btn = QPushButton("Log In", self)
        self.return_home_btn.setObjectName("returnHomeBtn")
        self.return_home_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.return_home_btn.setStyleSheet(f"""
            QPushButton#returnHomeBtn {{
                background: rgba(45, 45, 45, 0.45);
                color: #D8D4CC;
                border: none;
                border-radius: 18px;
                font-size: 13px;
                font-weight: 600;
                padding: 8px 24px;
                font-family: {fonts};
                letter-spacing: 0.3px;
            }}
            QPushButton#returnHomeBtn:hover {{
                background: rgba(65, 65, 65, 0.65);
                color: #FFFFFF;
            }}
            QPushButton#returnHomeBtn:pressed {{
                background: rgba(30, 30, 30, 0.65);
            }}
        """)
        self.return_home_btn.clicked.connect(self._on_submit)

    # ── Background ────────────────────────────────────────────────────────────

    def _apply_bg(self) -> None:
        bg_files = [
            ASSETS / "bg" / "home.jpg",
            ASSETS / "bg" / "home.png",
            ASSETS / "bg" / "bg.jpg",
            ASSETS / "bg" / "bg.png",
        ]
        found = next((f for f in bg_files if f.exists()), None)
        if found:
            self._bg.setStyleSheet(
                f"QFrame#authBgFrame {{ border-image: url({found.as_posix()}) 0 0 0 0 stretch stretch; }}"
            )
        else:
            self._bg.setStyleSheet(
                "QFrame#authBgFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                " stop:0 #1a2a1a, stop:0.5 #2a3a28, stop:1 #0d1a12); }"
            )

    # ── Geometry layout ───────────────────────────────────────────────────────

    def _reposition_form(self) -> None:
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        self._bg.setGeometry(0, 0, w, h)
        self._gradient.setGeometry(0, 0, w, h)
        self._top_bar.setGeometry(0, 0, w, 40)
        self.back_btn.setGeometry(28, 16, 36, 36)

        # Form card sizing & positioning
        fc_w = 360
        self._form_card.setFixedWidth(fc_w)
        self._form_card.adjustSize()
        fc_h = self._form_card.sizeHint().height()

        left_center_x = max(32, int(w * 0.28) - fc_w // 2)
        center_y = max(36, (h - fc_h) // 2)
        self._form_card.setGeometry(left_center_x, center_y, fc_w, fc_h)

        # Bottom right status pill ("Log In" / "Register")
        btn_w = max(100, self.return_home_btn.sizeHint().width() + 28)
        btn_h = 38
        self.return_home_btn.setGeometry(w - btn_w - 32, h - btn_h - 28, btn_w, btn_h)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reposition_form()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._bg.lower()
        self._gradient.raise_()
        self._form_card.raise_()
        self._top_bar.raise_()
        self.back_btn.raise_()
        self.return_home_btn.raise_()
        self._reposition_form()
        self._animate_form_entrance()

    def _animate_form_entrance(self) -> None:
        if hasattr(self, "_form_anim") and self._form_anim.state() == QPropertyAnimation.State.Running:
            return
        target_pos = self._form_card.pos()
        start_pos = QPoint(target_pos.x(), target_pos.y() + 20)
        self._form_card.move(start_pos)
        self._form_anim = QPropertyAnimation(self._form_card, b"pos", self)
        self._form_anim.setDuration(300)
        self._form_anim.setStartValue(start_pos)
        self._form_anim.setEndValue(target_pos)
        self._form_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._form_anim.start()

    # ── Mode toggle ───────────────────────────────────────────────────────────

    def _toggle_mode(self) -> None:
        self.error_label.hide()
        if self._mode == "login":
            self._mode = "register"
            self.title_label.setText("Create Account")
            self.subtitle_label.setText(
                "Create an account to access your launcher and\nsync your progress online"
            )
            self.email.show()
            self.password2.show()
            self.forgot_row.hide()
            self.submit.setText("Register")
            self.toggle_prefix.setText("Already have an account?")
            self.toggle_btn.setText("Log In")
            self.return_home_btn.setText("Register")
        else:
            self._mode = "login"
            self.title_label.setText("Welcome Back")
            self.subtitle_label.setText("Sign in to access your launcher and\nsync your progress online")
            self.email.hide()
            self.password2.hide()
            self.forgot_row.show()
            self.submit.setText("Log In")
            self.toggle_prefix.setText("Don't have an account?")
            self.toggle_btn.setText("Register Here")
            self.return_home_btn.setText("Log In")

        self._reposition_form()
        self.resized.emit()

    # ── Form handling ─────────────────────────────────────────────────────────

    def _on_submit(self) -> None:
        self.error_label.hide()
        u = self.user.text().strip()
        p = self.password.text()

        if not u:
            self.set_error("Username is required")
            return
        if not p:
            self.set_error("Password is required")
            return

        if self._mode == "login":
            self.login_requested.emit(u, p)
        else:
            p2 = self.password2.text()
            if p != p2:
                self.set_error("Passwords do not match")
                return
            e = self.email.text().strip() or None
            self.register_requested.emit(u, p, e)

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()
        self._reposition_form()

    def set_busy(self, busy: bool) -> None:
        self.submit.setEnabled(not busy)
        self.user.setEnabled(not busy)
        self.password.setEnabled(not busy)
        self.email.setEnabled(not busy)
        self.password2.setEnabled(not busy)

    def clear(self) -> None:
        self.user.clear()
        self.password.clear()
        self.email.clear()
        self.password2.clear()
        self.error_label.hide()
        self._reposition_form()
