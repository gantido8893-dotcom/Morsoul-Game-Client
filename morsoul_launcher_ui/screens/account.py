"""Account and settings screen matching Frame 3 (synced progress) and Frame 5 (no synced progress) mockups."""

from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from morsoul_core.paths import data_dir
from morsoul_launcher import strings
from morsoul_launcher.appstate import AppState
from morsoul_launcher.profile_service import ProfileDisplayData, fetch_profile_display_data
from morsoul_launcher_ui.theme import ASSETS, get_font_family

_BI = ASSETS / "button_icons"
_GOLD = "#CBA344"
_TEXT_MUTED = "#9C988F"
_TEXT_SUBTLE = "#808080"
_WHITE = "#FFFFFF"
_APP_VERSION = "v0.1.0"


class _SideBtn(QPushButton):
    """Sidebar nav icon matching HomeScreen."""

    def __init__(self, icon_off: str, icon_on: str = "", *, checkable: bool = False, size: int = 24) -> None:
        super().__init__()
        self._path_off = _BI / icon_off
        self._path_on = (_BI / icon_on) if icon_on else None
        self.setCheckable(checkable)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self._refresh()
        if checkable:
            self.toggled.connect(lambda _: self._refresh())

    def _refresh(self) -> None:
        use_on = self.isChecked() and self._path_on is not None
        path = self._path_on if use_on else self._path_off
        if path and path.exists():
            self.setIcon(QIcon(str(path)))
            self.setIconSize(QSize(self.width(), self.height()))


class AccountOverlay(QWidget):
    """Full-screen user account and profile interface matching Frame 3 & Frame 5."""

    change_password = Signal(str, str)
    change_email = Signal(str, str)  # password, new_email
    sign_out = Signal()
    sign_out_all = Signal()
    request_sign_out_all = Signal()
    delete_account = Signal(str)
    request_delete_account = Signal()
    delete_cloud = Signal(str)
    download_data = Signal()
    setting_toggled = Signal(str, bool)
    reset_server_url = Signal()
    closed = Signal()  # Emitted when Home icon is clicked
    check_updates = Signal()
    minimize_clicked = Signal()
    close_clicked = Signal()
    switch_profile_clicked = Signal()
    view_update_log = Signal()
    view_client_log = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("accountRoot")
        fonts = get_font_family()

        # ── Background layer ──────────────────────────────────────────────────
        self._bg = QFrame(self)
        self._bg.setObjectName("accountBgFrame")
        self._apply_bg()

        # ── Dark background overlay (matching Frames 3 & 5) ───────────────────
        self._dark_overlay = QFrame(self)
        self._dark_overlay.setObjectName("accountDarkOverlay")
        self._dark_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._dark_overlay.setStyleSheet(
            "QFrame#accountDarkOverlay {  background-color: rgba(10, 10, 10, 0.68);}"
        )

        # ── Left sidebar (reusing HomeScreen layout & styling) ───────────────
        self._sidebar = QFrame(self)
        self._sidebar.setObjectName("sidebarFrame")
        self._sidebar.setFixedWidth(90)
        self._sidebar.setStyleSheet(
            "QFrame#sidebarFrame {"
            "  background: transparent;"
            "  border: none;"
            "}"
        )

        sb = QVBoxLayout(self._sidebar)
        sb.setContentsMargins(0, 0, 0, 0)
        sb.setSpacing(0)

        # Top zone: game icon
        top_zone = QWidget()
        top_zone.setFixedHeight(68)
        top_zone.setContentsMargins(0, 30, 0, 0)
        top_zone.setStyleSheet("background: transparent;")
        tz = QVBoxLayout(top_zone)
        tz.setContentsMargins(0, 0, 0, 0)
        tz.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        game_icon_path = ASSETS / "game_icon.png"
        if game_icon_path.exists():
            gi = QLabel()
            pix = QPixmap(str(game_icon_path)).scaled(
                40,
                40,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            gi.setPixmap(pix)
            gi.setAlignment(Qt.AlignmentFlag.AlignCenter)
            gi.setStyleSheet("background: transparent;")
            tz.addWidget(gi, alignment=Qt.AlignmentFlag.AlignHCenter)
        sb.addWidget(top_zone)

        # Mid zone: nav pill capsule
        mid_zone = QFrame()
        mid_zone.setObjectName("midZone")
        mid_zone.setStyleSheet("""
            QFrame#midZone {
                background: rgba(36, 32, 26, 0.45);
                border-radius: 27px;
                border: none;
            }
        """)
        mid_zone.setFixedWidth(54)
        mz = QVBoxLayout(mid_zone)
        mz.setContentsMargins(0, 25, 0, 25)
        mz.setSpacing(28)
        mz.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)

        self.user_nav_btn = _SideBtn("user_notclicked.png", "user_clicked.png", checkable=True, size=24)
        self.user_nav_btn.setToolTip("Account & Settings")
        self.user_nav_btn.setChecked(True)
        mz.addWidget(self.user_nav_btn, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.home_nav_btn = _SideBtn("home_notclicked.png", "home_clicked.png", checkable=True, size=24)
        self.home_nav_btn.setToolTip("Home")
        self.home_nav_btn.setChecked(False)
        self.home_nav_btn.clicked.connect(self.closed.emit)
        mz.addWidget(self.home_nav_btn, alignment=Qt.AlignmentFlag.AlignHCenter)

        sb.addWidget(mid_zone, alignment=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)

        # Bottom zone: updates icon
        bot_zone = QWidget()
        bot_zone.setFixedHeight(60)
        bot_zone.setStyleSheet("background: transparent;")
        bz = QVBoxLayout(bot_zone)
        bz.setContentsMargins(0, 0, 0, 30)
        bz.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)

        self.update_btn = _SideBtn("updates_icon.png", size=32)
        self.update_btn.setToolTip(strings.CHECK_UPDATES)
        self.update_btn.clicked.connect(self.check_updates.emit)
        bz.addWidget(self.update_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        sb.addWidget(bot_zone)

        # ── Main content area ─────────────────────────────────────────────────
        self._content = QWidget(self)
        self._content.setObjectName("accountContentHost")
        self._content.setStyleSheet("background: transparent;")

        content_root = QVBoxLayout(self._content)
        content_root.setContentsMargins(0, 0, 0, 0)
        content_root.setSpacing(0)

        # ── Title bar (minimize / close only, exactly matching HomeScreen) ───
        self._title_bar = QWidget(self._content)
        self._title_bar.setFixedHeight(40)
        self._title_bar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._title_bar.setStyleSheet("background: transparent;")
        tb = QHBoxLayout(self._title_bar)
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

        content_root.addWidget(self._title_bar)

        # ── Inner Main Container (Brought down, matching Frames 3 & 5) ─────────
        inner_host = QWidget(self._content)
        inner_host.setStyleSheet("background: transparent;")
        inner_root = QVBoxLayout(inner_host)
        inner_root.setContentsMargins(0, 0, 0, 0)
        inner_root.setSpacing(0)
        inner_root.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        # Grid container locks width to 1096px (aligning avatar, cards, and bottom bar)
        self.grid_container = QWidget()
        self.grid_container.setFixedWidth(1096)
        self.grid_container.setStyleSheet("background: transparent;")

        cl = QVBoxLayout(self.grid_container)
        cl.setContentsMargins(0, 24, 0, 24)
        cl.setSpacing(0)

        # ── Header Row: Avatar + User Info on Left, Sign Out on Right ─────────
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(14)

        # Avatar circle chip with letter (e.g. "U")
        self.avatar_circle = QFrame()
        self.avatar_circle.setFixedSize(48, 48)
        self.avatar_circle.setStyleSheet("""
            QFrame {
                background-color: #D4A843;
                border-radius: 24px;
                border: none;
            }
        """)
        av_lay = QVBoxLayout(self.avatar_circle)
        av_lay.setContentsMargins(0, 0, 0, 0)
        av_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.avatar_label = QLabel("U")
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setStyleSheet(f"""
            color: {_WHITE};
            font-size: 19px;
            font-weight: 700;
            background: transparent;
            border: none;
            font-family: {fonts};
        """)
        av_lay.addWidget(self.avatar_label)
        header_row.addWidget(self.avatar_circle)

        # User header labels
        user_header_box = QVBoxLayout()
        user_header_box.setContentsMargins(0, 2, 0, 2)
        user_header_box.setSpacing(2)
        user_header_box.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.username_header = QLabel("")
        self.username_header.setStyleSheet(f"""
            color: {_WHITE};
            font-size: 17px;
            font-weight: 700;
            background: transparent;
            border: none;
            font-family: {fonts};
        """)
        user_header_box.addWidget(self.username_header)

        self.email_header = QLabel("")
        self.email_header.setStyleSheet(f"""
            color: {_TEXT_MUTED};
            font-size: 13px;
            font-weight: 400;
            background: transparent;
            border: none;
            font-family: {fonts};
        """)
        user_header_box.addWidget(self.email_header)
        header_row.addLayout(user_header_box)

        header_row.addStretch()

        # Red "Sign Out" button (aligned to right edge of Card 3)
        self.sign_out_btn = QPushButton("Sign Out")
        self.sign_out_btn.setObjectName("accSignOutBtn")
        self.sign_out_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sign_out_btn.setStyleSheet(f"""
            QPushButton#accSignOutBtn {{
                background-color: #E03E3E;
                color: #FFFFFF;
                border-radius: 8px;
                padding: 7px 22px;
                font-weight: 700;
                font-size: 13px;
                border: none;
                font-family: {fonts};
            }}
            QPushButton#accSignOutBtn:hover {{
                background-color: #F04848;
            }}
            QPushButton#accSignOutBtn:pressed {{
                background-color: #C53030;
            }}
        """)
        self.sign_out_btn.clicked.connect(self.sign_out.emit)
        header_row.addWidget(self.sign_out_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        cl.addLayout(header_row)
        cl.addSpacing(22)

        # ── Center 3-Card Layout (Fixed height 365px) ─────────────────────────
        cards_row = QHBoxLayout()
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setSpacing(18)
        cards_row.setAlignment(Qt.AlignmentFlag.AlignTop)

        card_style = """
            QFrame#accNavCard,
            QFrame#accInfoCard,
            QFrame#accProgressCard,
            QFrame#accSettingsCard,
            QFrame#accPrivacySecCard,
            QFrame#accPrivacyCloudCard,
            QFrame#accAboutGameCard,
            QFrame#accAboutCreditsCard {
                background-color: rgba(32, 30, 26, 0.58);
                border: 1px solid rgba(203, 163, 68, 0.14);
                border-radius: 16px;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """

        # ── Card 1: Left Navigation Menu ("User Account") ─────────────────────
        self.nav_card = QFrame()
        self.nav_card.setObjectName("accNavCard")
        self.nav_card.setFixedSize(210, 365)
        self.nav_card.setStyleSheet(card_style)

        nc_layout = QVBoxLayout(self.nav_card)
        nc_layout.setContentsMargins(24, 24, 24, 24)
        nc_layout.setSpacing(6)

        nav_title = QLabel("User Account")
        nav_title.setStyleSheet(f"""
            color: {_WHITE};
            font-size: 16px;
            font-weight: 700;
            background: transparent;
            border: none;
            font-family: {fonts};
        """)
        nc_layout.addWidget(nav_title)
        nc_layout.addSpacing(14)

        self._tabs = ["Profile", "Settings", "Privacy", "About"]
        self._tab_buttons: list[QPushButton] = []

        for idx, name in enumerate(self._tabs):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(34)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {_GOLD if idx == 0 else "#C8C8C8"};
                    font-size: 14px;
                    font-weight: {"700" if idx == 0 else "500"};
                    text-align: left;
                    padding-left: 2px;
                    border: none;
                    font-family: {fonts};
                }}
                QPushButton:hover {{
                    color: {_WHITE};
                }}
            """)
            btn.clicked.connect(lambda _, i=idx: self._select_tab(i))
            self._tab_buttons.append(btn)
            nc_layout.addWidget(btn)

        nc_layout.addStretch()
        cards_row.addWidget(self.nav_card)

        # Stacked view host for middle + right contents (switches between Profile view and other tabs)
        self.main_stack = QStackedWidget()
        self.main_stack.setStyleSheet("background: transparent; border: none;")

        # Page 0: Profile View (Dual cards: Account Info Card + Profile Progress Card)
        self.profile_dual_view = QWidget()
        self.profile_dual_view.setStyleSheet("background: transparent; border: none;")
        pd_layout = QHBoxLayout(self.profile_dual_view)
        pd_layout.setContentsMargins(0, 0, 0, 0)
        pd_layout.setSpacing(18)

        # ── Card 2: Middle Card ("User Account Information") ──────────────────
        self.account_info_card = QFrame()
        self.account_info_card.setObjectName("accInfoCard")
        self.account_info_card.setFixedSize(410, 365)
        self.account_info_card.setStyleSheet(card_style)

        aic_lay = QVBoxLayout(self.account_info_card)
        aic_lay.setContentsMargins(28, 24, 28, 24)
        aic_lay.setSpacing(0)

        # 1. Username
        lbl_un = QLabel("Username")
        lbl_un.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 12px; font-weight: 500; background: transparent; border: none; font-family: {fonts};"
        )
        aic_lay.addWidget(lbl_un)
        aic_lay.addSpacing(3)

        self.val_username = QLabel("")
        self.val_username.setStyleSheet(
            f"color: {_WHITE}; font-size: 16px; font-weight: 700; background: transparent; border: none; font-family: {fonts};"
        )
        aic_lay.addWidget(self.val_username)
        aic_lay.addSpacing(18)

        # 2. Email
        lbl_em = QLabel("Email")
        lbl_em.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 12px; font-weight: 500; background: transparent; border: none; font-family: {fonts};"
        )
        aic_lay.addWidget(lbl_em)
        aic_lay.addSpacing(3)

        self.val_email = QLabel("")
        self.val_email.setStyleSheet(
            f"color: {_WHITE}; font-size: 14px; font-weight: 400; background: transparent; border: none; font-family: {fonts};"
        )
        aic_lay.addWidget(self.val_email)
        aic_lay.addSpacing(18)

        # 3. Password
        lbl_pw = QLabel("Password")
        lbl_pw.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 12px; font-weight: 500; background: transparent; border: none; font-family: {fonts};"
        )
        aic_lay.addWidget(lbl_pw)
        aic_lay.addSpacing(3)

        self.val_password = QLabel("***************")
        self.val_password.setStyleSheet(
            f"color: {_WHITE}; font-size: 14px; font-weight: 400; letter-spacing: 1.5px; background: transparent; border: none; font-family: {fonts};"
        )
        aic_lay.addWidget(self.val_password)
        aic_lay.addSpacing(2)

        self.val_last_changed = QLabel("Last changed 24hrs ago")
        self.val_last_changed.setStyleSheet(
            f"color: {_TEXT_SUBTLE}; font-size: 11px; background: transparent; border: none; font-family: {fonts};"
        )
        aic_lay.addWidget(self.val_last_changed)
        aic_lay.addSpacing(18)

        # 4. Account Created at
        lbl_ac = QLabel("Account Created at:")
        lbl_ac.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 12px; font-weight: 500; background: transparent; border: none; font-family: {fonts};"
        )
        aic_lay.addWidget(lbl_ac)
        aic_lay.addSpacing(3)

        self.val_account_created = QLabel("November 5, 2026")
        self.val_account_created.setStyleSheet(
            f"color: {_WHITE}; font-size: 13px; font-weight: 500; background: transparent; border: none; font-family: {fonts};"
        )
        aic_lay.addWidget(self.val_account_created)

        aic_lay.addStretch()
        pd_layout.addWidget(self.account_info_card)

        # ── Card 3: Right Card ("Profile & Progress" - Frame 3 / Frame 5) ─────
        self.progress_card = QFrame()
        self.progress_card.setObjectName("accProgressCard")
        self.progress_card.setFixedSize(440, 365)
        self.progress_card.setStyleSheet(card_style)

        pc_lay = QVBoxLayout(self.progress_card)
        pc_lay.setContentsMargins(28, 24, 28, 24)
        pc_lay.setSpacing(0)

        # Row 1: Profile Name + Switch Profile Button
        pn_row = QHBoxLayout()
        pn_row.setContentsMargins(0, 0, 0, 0)
        pn_box = QVBoxLayout()
        pn_box.setContentsMargins(0, 0, 0, 0)
        pn_box.setSpacing(3)

        lbl_pn = QLabel("Profile Name")
        lbl_pn.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 12px; font-weight: 500; background: transparent; border: none; font-family: {fonts};"
        )
        pn_box.addWidget(lbl_pn)

        self.val_profile_name = QLabel("Ibn Al-haytham")
        self.val_profile_name.setStyleSheet(
            f"color: {_WHITE}; font-size: 16px; font-weight: 700; background: transparent; border: none; font-family: {fonts};"
        )
        pn_box.addWidget(self.val_profile_name)
        pn_row.addLayout(pn_box)

        pn_row.addStretch()

        self.switch_profile_btn = QPushButton("Switch Profile")
        self.switch_profile_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.switch_profile_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.10);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 8px;
                color: #FFFFFF;
                font-size: 12px;
                font-weight: 600;
                padding: 6px 14px;
                font-family: {fonts};
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.18);
            }}
            QPushButton:pressed {{
                background-color: rgba(255, 255, 255, 0.08);
            }}
        """)
        self.switch_profile_btn.clicked.connect(self.switch_profile_clicked.emit)
        pn_row.addWidget(self.switch_profile_btn, alignment=Qt.AlignmentFlag.AlignTop)
        pc_lay.addLayout(pn_row)
        pc_lay.addSpacing(18)

        # Row 2: Playtime
        lbl_pt = QLabel("Playtime")
        lbl_pt.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 12px; font-weight: 500; background: transparent; border: none; font-family: {fonts};"
        )
        pc_lay.addWidget(lbl_pt)
        pc_lay.addSpacing(3)

        self.val_playtime = QLabel("12 Hrs 3 mins")
        self.val_playtime.setStyleSheet(
            f"color: {_WHITE}; font-size: 14px; font-weight: 400; background: transparent; border: none; font-family: {fonts};"
        )
        pc_lay.addWidget(self.val_playtime)
        pc_lay.addSpacing(18)

        # Row 3: Cases Solved
        lbl_cs = QLabel("Cases Solved")
        lbl_cs.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 12px; font-weight: 500; background: transparent; border: none; font-family: {fonts};"
        )
        pc_lay.addWidget(lbl_cs)
        pc_lay.addSpacing(3)

        self.val_cases_solved = QLabel("2/6")
        self.val_cases_solved.setStyleSheet(
            f"color: {_WHITE}; font-size: 14px; font-weight: 400; background: transparent; border: none; font-family: {fonts};"
        )
        pc_lay.addWidget(self.val_cases_solved)
        pc_lay.addSpacing(18)

        # Row 4: Runic Logs
        lbl_rl = QLabel("Runic Logs")
        lbl_rl.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 12px; font-weight: 500; background: transparent; border: none; font-family: {fonts};"
        )
        pc_lay.addWidget(lbl_rl)
        pc_lay.addSpacing(3)

        self.val_runic_logs = QLabel("2/4")
        self.val_runic_logs.setStyleSheet(
            f"color: {_WHITE}; font-size: 14px; font-weight: 400; background: transparent; border: none; font-family: {fonts};"
        )
        pc_lay.addWidget(self.val_runic_logs)
        pc_lay.addSpacing(16)

        # Row 5: Last Synced
        self.val_last_synced = QLabel("Last Synced 20 mins")
        self.val_last_synced.setStyleSheet(
            f"color: {_TEXT_SUBTLE}; font-size: 12px; background: transparent; border: none; font-family: {fonts};"
        )
        pc_lay.addWidget(self.val_last_synced)

        pc_lay.addStretch()
        pd_layout.addWidget(self.progress_card)

        self.main_stack.addWidget(self.profile_dual_view)

        # Sub-pages for other tabs (Settings, Privacy, About)
        self.settings_subpage = self._build_settings_page(card_style, fonts)
        self.privacy_subpage = self._build_privacy_page(card_style, fonts)
        self.about_subpage = self._build_about_page(card_style, fonts)

        self.main_stack.addWidget(self.settings_subpage)  # Page 1
        self.main_stack.addWidget(self.privacy_subpage)  # Page 2
        self.main_stack.addWidget(self.about_subpage)  # Page 3

        cards_row.addWidget(self.main_stack)
        cl.addLayout(cards_row)

        cl.addSpacing(20)

        # ── Bottom Bar: Translucent Update / Notification Panel ───────────────
        self.bottom_bar = QFrame()
        self.bottom_bar.setObjectName("accBottomBar")
        self.bottom_bar.setFixedSize(1096, 56)
        self.bottom_bar.setStyleSheet("""
            QFrame#accBottomBar {
                background-color: rgba(38, 38, 38, 0.52);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }
        """)

        bb_lay = QHBoxLayout(self.bottom_bar)
        bb_lay.setContentsMargins(24, 0, 24, 0)

        # Left: Update/Notification text
        notif_box = QVBoxLayout()
        notif_box.setContentsMargins(0, 0, 0, 0)
        notif_box.setSpacing(2)
        notif_box.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        lbl_notif = QLabel("Update/Notification:")
        lbl_notif.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 11px; font-weight: 500; background: transparent; border: none; font-family: {fonts};"
        )
        notif_box.addWidget(lbl_notif)

        self.val_notification = QLabel("No new notifications or updates")
        self.val_notification.setStyleSheet(
            f"color: {_WHITE}; font-size: 13px; font-weight: 400; background: transparent; border: none; font-family: {fonts};"
        )
        notif_box.addWidget(self.val_notification)

        bb_lay.addLayout(notif_box)
        bb_lay.addStretch()

        # Right: Game update status pill badge
        self.val_version_pill = QLabel("Game is up to date (V 1.0)")
        self.val_version_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.val_version_pill.setStyleSheet(f"""
            QLabel {{
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 12px;
                color: #D0D0D0;
                font-size: 12px;
                font-weight: 500;
                padding: 5px 16px;
                font-family: {fonts};
            }}
        """)
        bb_lay.addWidget(self.val_version_pill, alignment=Qt.AlignmentFlag.AlignVCenter)

        cl.addWidget(self.bottom_bar)

        inner_root.addWidget(self.grid_container)
        content_root.addWidget(inner_host, stretch=1)

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
                f"QFrame#accountBgFrame {{ border-image: url({found.as_posix()}) 0 0 0 0 stretch stretch; }}"
            )
        else:
            self._bg.setStyleSheet(
                "QFrame#accountBgFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                " stop:0 #1a2a1a, stop:0.5 #2a3a28, stop:1 #0d1a12); }"
            )

    # ── Sub-pages builders for Settings, Privacy, and About ───────────────────

    def _build_settings_page(self, card_style: str, fonts: str) -> QWidget:
        subpage = QWidget()
        subpage.setStyleSheet("background: transparent; border: none;")
        sp_layout = QHBoxLayout(subpage)
        sp_layout.setContentsMargins(0, 0, 0, 0)
        sp_layout.setSpacing(18)

        self.settings_card = QFrame()
        self.settings_card.setObjectName("accSettingsCard")
        self.settings_card.setFixedSize(410, 365)
        self.settings_card.setStyleSheet(card_style)

        lay = QVBoxLayout(self.settings_card)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(0)

        title = QLabel("Launcher Settings")
        title.setStyleSheet(
            f"color: {_GOLD}; font-size: 15px; font-weight: 600; background: transparent; border: none; font-family: {fonts};"
        )
        lay.addWidget(title)
        lay.addSpacing(20)

        # 4 Toggles
        cb_style = f"""
            QCheckBox {{
                color: #E6E6E6;
                font-size: 13px;
                font-weight: 400;
                spacing: 12px;
                background: transparent;
                border: none;
                font-family: {fonts};
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid rgba(255, 255, 255, 0.25);
                background-color: rgba(30, 30, 34, 0.70);
            }}
            QCheckBox::indicator:checked {{
                background-color: {_GOLD};
                border-color: {_GOLD};
            }}
            QCheckBox::indicator:hover {{
                border-color: #FFFFFF;
            }}
        """

        self.toggle_sync_close = QCheckBox("Sync when the game closes")
        self.toggle_sync_open = QCheckBox("Sync when the launcher opens")
        self.toggle_check_updates = QCheckBox("Check for updates on start")
        self.toggle_close_on_start = QCheckBox("Close the launcher when the game starts")

        self.toggle_sync_close.setChecked(True)
        self.toggle_sync_open.setChecked(True)
        self.toggle_check_updates.setChecked(True)
        self.toggle_close_on_start.setChecked(False)

        for cb, key in [
            (self.toggle_sync_close, "sync_on_game_close"),
            (self.toggle_sync_open, "sync_on_launcher_open"),
            (self.toggle_check_updates, "check_updates_on_start"),
            (self.toggle_close_on_start, "close_launcher_on_game_start"),
        ]:
            cb.setStyleSheet(cb_style)
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.toggled.connect(lambda val, k=key: self.setting_toggled.emit(k, val))
            lay.addWidget(cb)
            lay.addSpacing(16)

        lay.addStretch()

        # Dummy hidden QLineEdit to preserve backwards-compatibility with controller/bridge calls
        self.server_lbl = QLineEdit("http://127.0.0.1:8080")
        self.server_lbl.setVisible(False)

        sp_layout.addWidget(self.settings_card)
        sp_layout.addStretch()
        return subpage

    def _build_privacy_page(self, card_style: str, fonts: str) -> QWidget:
        subpage = QWidget()
        subpage.setStyleSheet("background: transparent; border: none;")
        sp_layout = QHBoxLayout(subpage)
        sp_layout.setContentsMargins(0, 0, 0, 0)
        sp_layout.setSpacing(18)

        # ── Shared styles ─────────────────────────────────────────────────────
        input_style = f"""
            QLineEdit {{
                background: rgba(30, 30, 32, 0.75);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 8px;
                padding: 0 12px;
                color: #FFFFFF;
                font-size: 12px;
                font-weight: 400;
                min-height: 34px;
                max-height: 34px;
                font-family: {fonts};
            }}
            QLineEdit:focus {{
                border-color: {_GOLD};
            }}
        """

        section_title_style = (
            f"color: {_WHITE}; font-size: 13px; font-weight: 600;"
            f" background: transparent; border: none; font-family: {fonts};"
        )

        hint_style = (
            f"color: {_TEXT_SUBTLE}; font-size: 11px; font-weight: 400;"
            f" background: transparent; border: none; font-family: {fonts};"
        )

        btn_accent_style = f"""
            QPushButton {{
                background-color: {_GOLD};
                color: #1A1600;
                font-weight: 600;
                font-size: 12px;
                border-radius: 8px;
                padding: 0 18px;
                min-height: 32px;
                border: none;
                font-family: {fonts};
            }}
            QPushButton:hover {{
                background-color: #E0BA58;
            }}
            QPushButton:pressed {{
                background-color: #A88930;
            }}
        """

        btn_outline_style = f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 8px;
                color: #D0D0D0;
                font-size: 12px;
                font-weight: 500;
                padding: 0 16px;
                min-height: 32px;
                font-family: {fonts};
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.12);
                border-color: rgba(255, 255, 255, 0.25);
                color: #FFFFFF;
            }}
            QPushButton:pressed {{
                background-color: rgba(255, 255, 255, 0.04);
            }}
        """

        separator_style = (
            "background-color: rgba(255, 255, 255, 0.07);"
            " min-height: 1px; max-height: 1px; border: none;"
        )

        # ── Card 1: Password & Security (410 x 365) ──────────────────────────
        self.privacy_sec_card = QFrame()
        self.privacy_sec_card.setObjectName("accPrivacySecCard")
        self.privacy_sec_card.setFixedSize(410, 365)
        self.privacy_sec_card.setStyleSheet(card_style)

        lay1 = QVBoxLayout(self.privacy_sec_card)
        lay1.setContentsMargins(24, 20, 24, 20)
        lay1.setSpacing(0)

        # Card header
        sec_title = QLabel("Password & Security")
        sec_title.setStyleSheet(
            f"color: {_GOLD}; font-size: 15px; font-weight: 600;"
            f" background: transparent; border: none; font-family: {fonts};"
        )
        lay1.addWidget(sec_title)
        lay1.addSpacing(4)

        sec_desc = QLabel("Manage your password and account email address.")
        sec_desc.setStyleSheet(hint_style)
        sec_desc.setWordWrap(True)
        lay1.addWidget(sec_desc)
        lay1.addSpacing(12)

        # ── Section: Change Password ──────────────────────────────────────────
        pw_section_lbl = QLabel("Change Password")
        pw_section_lbl.setStyleSheet(section_title_style)
        lay1.addWidget(pw_section_lbl)
        lay1.addSpacing(6)

        self.current_pw = QLineEdit()
        self.current_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.current_pw.setPlaceholderText("Current password")
        self.current_pw.setStyleSheet(input_style)
        lay1.addWidget(self.current_pw)
        lay1.addSpacing(6)

        # New & confirm password side by side
        pw_row = QHBoxLayout()
        pw_row.setSpacing(8)

        self.new_pw = QLineEdit()
        self.new_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_pw.setPlaceholderText("New password")
        self.new_pw.setStyleSheet(input_style)
        pw_row.addWidget(self.new_pw)

        self.new_pw2 = QLineEdit()
        self.new_pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_pw2.setPlaceholderText("Confirm password")
        self.new_pw2.setStyleSheet(input_style)
        pw_row.addWidget(self.new_pw2)
        lay1.addLayout(pw_row)
        lay1.addSpacing(8)

        # Update button + message row
        pw_btn_row = QHBoxLayout()
        pw_btn_row.setSpacing(8)

        self.msg_label = QLabel("")
        self.msg_label.setStyleSheet(
            f"color: #FF6B6B; font-size: 11px; font-weight: 400;"
            f" background: transparent; border: none; font-family: {fonts};"
        )
        pw_btn_row.addWidget(self.msg_label, stretch=1)

        change_btn = QPushButton("Update Password")
        change_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        change_btn.setStyleSheet(btn_accent_style)
        change_btn.clicked.connect(self._change_password)
        pw_btn_row.addWidget(change_btn)
        lay1.addLayout(pw_btn_row)
        lay1.addSpacing(10)

        # ── Separator ─────────────────────────────────────────────────────────
        sep1 = QFrame()
        sep1.setStyleSheet(separator_style)
        lay1.addWidget(sep1)
        lay1.addSpacing(10)

        # ── Section: Change Email ─────────────────────────────────────────────
        email_section_lbl = QLabel("Update Email Address")
        email_section_lbl.setStyleSheet(section_title_style)
        lay1.addWidget(email_section_lbl)
        lay1.addSpacing(6)

        email_row = QHBoxLayout()
        email_row.setSpacing(8)

        self.new_email_input = QLineEdit()
        self.new_email_input.setPlaceholderText("New email address")
        self.new_email_input.setStyleSheet(input_style)
        email_row.addWidget(self.new_email_input, stretch=1)

        self.email_pw_input = QLineEdit()
        self.email_pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.email_pw_input.setPlaceholderText("Password")
        self.email_pw_input.setStyleSheet(input_style)
        self.email_pw_input.setFixedWidth(130)
        email_row.addWidget(self.email_pw_input)
        lay1.addLayout(email_row)
        lay1.addSpacing(8)

        email_btn_row = QHBoxLayout()
        email_btn_row.setSpacing(8)

        self.email_msg_label = QLabel("")
        self.email_msg_label.setStyleSheet(
            f"color: #FF6B6B; font-size: 11px; font-weight: 400;"
            f" background: transparent; border: none; font-family: {fonts};"
        )
        email_btn_row.addWidget(self.email_msg_label, stretch=1)

        email_save_btn = QPushButton("Update Email")
        email_save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        email_save_btn.setStyleSheet(btn_accent_style)
        email_save_btn.clicked.connect(self._change_email)
        email_btn_row.addWidget(email_save_btn)
        lay1.addLayout(email_btn_row)

        lay1.addStretch()

        # ── Card 2: Account Actions & Danger Zone (440 x 365) ────────────────
        self.privacy_cloud_card = QFrame()
        self.privacy_cloud_card.setObjectName("accPrivacyCloudCard")
        self.privacy_cloud_card.setFixedSize(440, 365)
        self.privacy_cloud_card.setStyleSheet(card_style)

        card2_outer_lay = QVBoxLayout(self.privacy_cloud_card)
        card2_outer_lay.setContentsMargins(0, 0, 0, 0)
        card2_outer_lay.setSpacing(0)

        # Smooth modern scroll area
        self.privacy_scroll = QScrollArea()
        self.privacy_scroll.setWidgetResizable(True)
        self.privacy_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.privacy_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.privacy_scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 6px;
                margin: 6px 4px 6px 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(203, 163, 68, 0.35);
                min-height: 24px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(203, 163, 68, 0.65);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent; border: none;")
        lay2 = QVBoxLayout(scroll_content)
        lay2.setContentsMargins(24, 20, 24, 20)
        lay2.setSpacing(0)

        # ── Cloud Saves Management ────────────────────────────────────────────
        cloud_lbl = QLabel("Cloud Saves Management")
        cloud_lbl.setStyleSheet(
            f"color: {_GOLD}; font-size: 15px; font-weight: 600;"
            f" background: transparent; border: none; font-family: {fonts};"
        )
        lay2.addWidget(cloud_lbl)
        lay2.addSpacing(4)

        cloud_desc = QLabel("Manage synced cloud save profiles and local data exports.")
        cloud_desc.setStyleSheet(hint_style)
        cloud_desc.setWordWrap(True)
        lay2.addWidget(cloud_desc)
        lay2.addSpacing(12)

        self.cloud_profiles_container = QVBoxLayout()
        self.cloud_profiles_container.setSpacing(6)
        lay2.addLayout(self.cloud_profiles_container)

        lay2.addSpacing(12)

        # ── Separator ─────────────────────────────────────────────────────────
        sep2 = QFrame()
        sep2.setStyleSheet(separator_style)
        lay2.addWidget(sep2)
        lay2.addSpacing(12)

        # ── Account Data & Sessions ───────────────────────────────────────────
        data_section_lbl = QLabel("Account Data & Sessions")
        data_section_lbl.setStyleSheet(section_title_style)
        lay2.addWidget(data_section_lbl)
        lay2.addSpacing(4)

        data_desc = QLabel(
            "Export a copy of your account data or sign out from all active sessions on other devices."
        )
        data_desc.setStyleSheet(hint_style)
        data_desc.setWordWrap(True)
        lay2.addWidget(data_desc)
        lay2.addSpacing(8)

        data_row = QHBoxLayout()
        data_row.setSpacing(8)

        dl_btn = QPushButton("Download My Data")
        dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dl_btn.setStyleSheet(btn_outline_style)
        dl_btn.clicked.connect(self.download_data.emit)
        data_row.addWidget(dl_btn)

        out_all = QPushButton("Sign Out All Devices")
        out_all.setCursor(Qt.CursorShape.PointingHandCursor)
        out_all.setStyleSheet(btn_outline_style)
        out_all.clicked.connect(self._prompt_sign_out_all)
        data_row.addWidget(out_all)

        data_row.addStretch()
        lay2.addLayout(data_row)

        lay2.addSpacing(12)

        # ── Separator ─────────────────────────────────────────────────────────
        sep3 = QFrame()
        sep3.setStyleSheet(separator_style)
        lay2.addWidget(sep3)
        lay2.addSpacing(10)

        # ── Danger Zone ───────────────────────────────────────────────────────
        danger_box = QFrame()
        danger_box.setStyleSheet("""
            QFrame {
                background-color: rgba(224, 62, 62, 0.08);
                border: 1px solid rgba(224, 62, 62, 0.20);
                border-radius: 10px;
            }
        """)
        danger_lay = QVBoxLayout(danger_box)
        danger_lay.setContentsMargins(14, 12, 14, 12)
        danger_lay.setSpacing(6)

        danger_title_row = QHBoxLayout()
        danger_title_row.setSpacing(0)

        danger_title = QLabel("Danger Zone")
        danger_title.setStyleSheet(
            f"color: #FF8A8A; font-size: 13px; font-weight: 600;"
            f" background: transparent; border: none; font-family: {fonts};"
        )
        danger_title_row.addWidget(danger_title)
        danger_title_row.addStretch()
        danger_lay.addLayout(danger_title_row)

        danger_text = QLabel(
            "Permanently delete your account and all associated cloud saves. "
            "This action is irreversible."
        )
        danger_text.setWordWrap(True)
        danger_text.setStyleSheet(
            f"color: #C89898; font-size: 11px; font-weight: 400;"
            f" background: transparent; border: none; font-family: {fonts};"
        )
        danger_lay.addWidget(danger_text)

        del_btn_row = QHBoxLayout()
        del_btn_row.addStretch()

        del_acc_btn = QPushButton("Delete Account")
        del_acc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_acc_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(224, 62, 62, 0.85);
                color: #FFFFFF;
                font-size: 12px;
                font-weight: 600;
                border-radius: 8px;
                border: none;
                padding: 0 18px;
                min-height: 30px;
                font-family: {fonts};
            }}
            QPushButton:hover {{
                background-color: #F04848;
            }}
            QPushButton:pressed {{
                background-color: #C53030;
            }}
        """)
        del_acc_btn.clicked.connect(self._prompt_delete_account)
        del_btn_row.addWidget(del_acc_btn)
        danger_lay.addLayout(del_btn_row)

        lay2.addWidget(danger_box)
        lay2.addStretch()

        self.privacy_scroll.setWidget(scroll_content)
        card2_outer_lay.addWidget(self.privacy_scroll)

        sp_layout.addWidget(self.privacy_sec_card)
        sp_layout.addWidget(self.privacy_cloud_card)
        return subpage

    def _prompt_sign_out_all(self) -> None:
        self.request_sign_out_all.emit()
        self.sign_out_all.emit()

    def _prompt_delete_account(self) -> None:
        self.request_delete_account.emit()

    def _build_about_page(self, card_style: str, fonts: str) -> QWidget:
        subpage = QWidget()
        subpage.setStyleSheet("background: transparent; border: none;")
        sp_layout = QHBoxLayout(subpage)
        sp_layout.setContentsMargins(0, 0, 0, 0)
        sp_layout.setSpacing(18)

        # ── Card 1: Game Info & Overview (410 x 365) ─────────────────────────
        self.about_game_card = QFrame()
        self.about_game_card.setObjectName("accAboutGameCard")
        self.about_game_card.setFixedSize(410, 365)
        self.about_game_card.setStyleSheet(card_style)

        lay1 = QVBoxLayout(self.about_game_card)
        lay1.setContentsMargins(28, 24, 28, 24)
        lay1.setSpacing(0)

        # Header: Title & Version
        head_row = QHBoxLayout()
        head_row.setContentsMargins(0, 0, 0, 0)
        title = QLabel(strings.APP_TITLE)
        title.setStyleSheet(
            f"color: {_GOLD}; font-size: 15px; font-weight: 600; background: transparent; border: none; font-family: {fonts};"
        )
        head_row.addWidget(title)
        head_row.addStretch()

        ver = QLabel(f"Client Version: {_APP_VERSION}")
        ver.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 12px; font-weight: 400; background: transparent; border: none; font-family: {fonts};"
        )
        head_row.addWidget(ver)
        lay1.addLayout(head_row)
        lay1.addSpacing(14)

        # Action buttons: View Update Log & View Client Log
        btn_style = f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 6px;
                color: #FFFFFF;
                font-size: 12px;
                font-weight: 500;
                padding: 0 14px;
                font-family: {fonts};
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.15);
            }}
        """

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        update_log_btn = QPushButton("View Update Log")
        update_log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        update_log_btn.setFixedHeight(32)
        update_log_btn.setStyleSheet(btn_style)
        update_log_btn.clicked.connect(self.view_update_log.emit)
        btn_row.addWidget(update_log_btn)

        client_log_btn = QPushButton("View Client Log")
        client_log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        client_log_btn.setFixedHeight(32)
        client_log_btn.setStyleSheet(btn_style)
        client_log_btn.clicked.connect(self.view_client_log.emit)
        btn_row.addWidget(client_log_btn)
        lay1.addLayout(btn_row)
        lay1.addSpacing(20)

        # "About the Game"
        lbl_about = QLabel("About the Game")
        lbl_about.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 12px; font-weight: 500; background: transparent; border: none; font-family: {fonts};"
        )
        lay1.addWidget(lbl_about)
        lay1.addSpacing(6)

        about_body = QLabel(
            "Centuries after a catastrophic mana disaster birthed the fantasy world of Agartha, "
            "the scattered consciousness of ancient detective Arthur Conan Doyle awakens inside an abandoned "
            "golem with no memory of his past. Solve intricate arcane mysteries, decipher ancient runic logs, "
            "and restore order to the realm."
        )
        about_body.setWordWrap(True)
        about_body.setStyleSheet(
            f"color: #D0D0D0; font-size: 13px; font-weight: 400; line-height: 1.5; background: transparent; border: none; font-family: {fonts};"
        )
        lay1.addWidget(about_body)
        lay1.addStretch()

        # ── Card 2: Creators / Credits, Purpose & Privacy Policy (440 x 365) ─
        self.about_credits_card = QFrame()
        self.about_credits_card.setObjectName("accAboutCreditsCard")
        self.about_credits_card.setFixedSize(440, 365)
        self.about_credits_card.setStyleSheet(card_style)

        lay2 = QVBoxLayout(self.about_credits_card)
        lay2.setContentsMargins(28, 24, 28, 24)
        lay2.setSpacing(0)

        # 1. Creators / Credits
        lbl_credits = QLabel("Creators / Credits")
        lbl_credits.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 12px; font-weight: 500; background: transparent; border: none; font-family: {fonts};"
        )
        lay2.addWidget(lbl_credits)
        lay2.addSpacing(4)

        credits_body = QLabel(
            "Developed by Tombois and Badbois.\n"
            "Game Design & Narrative: Wade Honrado\n"
            "Artwork & Concept: Tombois and Badbois\n"
            "Audio & Atmosphere: Unity"
        )
        credits_body.setStyleSheet(
            f"color: #D0D0D0; font-size: 12px; font-weight: 400; line-height: 1.4; background: transparent; border: none; font-family: {fonts};"
        )
        lay2.addWidget(credits_body)
        lay2.addSpacing(14)

        # 2. Purpose
        lbl_purpose = QLabel("Purpose")
        lbl_purpose.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 12px; font-weight: 500; background: transparent; border: none; font-family: {fonts};"
        )
        lay2.addWidget(lbl_purpose)
        lay2.addSpacing(4)

        purpose_body = QLabel(
            "The Morsoul Launcher serves as the secure portal for game updates, tamper-evident local SQLite/SQLCipher "
            "save storage, and seamless encrypted cloud synchronization across your workstations."
        )
        purpose_body.setWordWrap(True)
        purpose_body.setStyleSheet(
            f"color: #D0D0D0; font-size: 12px; font-weight: 400; line-height: 1.4; background: transparent; border: none; font-family: {fonts};"
        )
        lay2.addWidget(purpose_body)
        lay2.addSpacing(14)

        # 3. Privacy Policy
        lbl_priv = QLabel("Privacy Policy")
        lbl_priv.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 12px; font-weight: 500; background: transparent; border: none; font-family: {fonts};"
        )
        lay2.addWidget(lbl_priv)
        lay2.addSpacing(4)

        priv_body = QLabel(
            "We respect your privacy. Local progress files are secured using industry-standard SQLCipher AES-256 encryption. "
            "Cloud backups are transmitted exclusively over encrypted HTTPS sessions and are only accessible via your authenticated account."
        )
        priv_body.setWordWrap(True)
        priv_body.setStyleSheet(
            f"color: #D0D0D0; font-size: 12px; font-weight: 400; line-height: 1.4; background: transparent; border: none; font-family: {fonts};"
        )
        lay2.addWidget(priv_body)
        lay2.addStretch()

        sp_layout.addWidget(self.about_game_card)
        sp_layout.addWidget(self.about_credits_card)
        return subpage

    # ── Tab switching ─────────────────────────────────────────────────────────

    def _select_tab(self, index: int) -> None:
        self.main_stack.setCurrentIndex(index)
        fonts = get_font_family()
        for i, btn in enumerate(self._tab_buttons):
            if i == index:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent;
                        color: {_GOLD};
                        font-size: 14px;
                        font-weight: 700;
                        text-align: left;
                        padding-left: 2px;
                        border: none;
                        font-family: {fonts};
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent;
                        color: #C8C8C8;
                        font-size: 14px;
                        font-weight: 500;
                        text-align: left;
                        padding-left: 2px;
                        border: none;
                        font-family: {fonts};
                    }}
                    QPushButton:hover {{
                        color: {_WHITE};
                    }}
                """)

    def _change_password(self) -> None:
        if self.new_pw.text() != self.new_pw2.text():
            self.set_message("Passwords do not match", ok=False)
            return
        self.change_password.emit(self.current_pw.text(), self.new_pw.text())

    def _change_email(self) -> None:
        email = self.new_email_input.text().strip()
        pw = self.email_pw_input.text()
        if not email:
            self.set_email_message("Please enter a new email address", ok=False)
            return
        if not pw:
            self.set_email_message("Password is required to change email", ok=False)
            return
        self.change_email.emit(pw, email)

    def _open_logs(self) -> None:
        path = data_dir() / "logs"
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(path))
        except Exception:
            pass

    # ── State rendering (Dynamic Data from Database & State) ───────────────────

    def render_state(self, state: AppState) -> None:
        """Fetch dynamic data from local database & state, and format UI for Frame 3 / Frame 5."""
        fonts = get_font_family()
        data: ProfileDisplayData = fetch_profile_display_data(state)

        # Header
        self.avatar_label.setText(data.avatar_letter)
        self.username_header.setText(data.username)
        self.email_header.setText(data.email)

        # Middle Card: Account Info
        self.val_username.setText(data.username)
        self.val_email.setText(data.email)
        self.val_password.setText(data.password_masked)
        self.val_last_changed.setText(data.password_last_changed)
        self.val_account_created.setText(data.account_created_at)

        # Right Card: Profile Progress (Frame 3 vs Frame 5)
        self.val_profile_name.setText(data.profile_name)
        self.val_playtime.setText(data.playtime)
        self.val_cases_solved.setText(data.cases_solved)
        self.val_runic_logs.setText(data.runic_logs)
        self.val_last_synced.setText(data.last_synced)

        # Bottom Bar: Notification & Update Status
        self.val_notification.setText(data.notification_text)
        self.val_version_pill.setText(data.game_version_status)

        # Settings subpage
        self.server_lbl.setText(state.server_url or "http://127.0.0.1:8080")

        # Privacy subpage: Cloud saves list
        # Clear existing items
        while self.cloud_profiles_container.count():
            item = self.cloud_profiles_container.takeAt(0)
            if item:
                w = item.widget()
                if w:
                    w.deleteLater()

        if not state.profiles:
            empty_lbl = QLabel("No cloud profiles currently synced.")
            empty_lbl.setStyleSheet(
                f"color: {_TEXT_MUTED}; font-size: 12px; font-weight: 400; background: transparent; border: none; font-family: {fonts};"
            )
            self.cloud_profiles_container.addWidget(empty_lbl)
        else:
            for p in state.profiles:
                row = QFrame()
                row.setStyleSheet("""
                    QFrame {
                        background-color: rgba(36, 36, 40, 0.60);
                        border: 1px solid rgba(255, 255, 255, 0.08);
                        border-radius: 6px;
                    }
                """)
                r_lay = QHBoxLayout(row)
                r_lay.setContentsMargins(12, 6, 12, 6)

                p_name = QLabel(p.display_name or p.profile_id)
                p_name.setStyleSheet(
                    f"color: #FFFFFF; font-size: 12px; font-weight: 500; background: transparent; border: none; font-family: {fonts};"
                )
                r_lay.addWidget(p_name, stretch=1)

                p_status = QLabel(str(p.sync_state.value).upper())
                p_status.setStyleSheet(
                    "color: #CBA344; font-size: 11px; font-weight: 500; background: transparent; border: none;"
                )
                r_lay.addWidget(p_status)

                del_cloud_btn = QPushButton("Delete Cloud Copy")
                del_cloud_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                del_cloud_btn.setFixedHeight(26)
                del_cloud_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: rgba(224, 62, 62, 0.20);
                        border: 1px solid rgba(224, 62, 62, 0.40);
                        border-radius: 4px;
                        color: #FFB4B4;
                        font-size: 11px;
                        font-weight: 500;
                        padding: 0 10px;
                        font-family: {fonts};
                    }}
                    QPushButton:hover {{
                        background-color: rgba(224, 62, 62, 0.40);
                        color: #FFFFFF;
                    }}
                """)
                del_cloud_btn.clicked.connect(lambda _, pid=p.profile_id: self.delete_cloud.emit(pid))
                r_lay.addWidget(del_cloud_btn)

                self.cloud_profiles_container.addWidget(row)

    def set_message(self, text: str, ok: bool = False) -> None:
        self.msg_label.setStyleSheet("color: #5BB85D;" if ok else "color: #FF6B6B;")
        self.msg_label.setText(text)
        if ok:
            self.current_pw.clear()
            self.new_pw.clear()
            self.new_pw2.clear()
        if hasattr(self, "_msg_timer") and self._msg_timer is not None:
            self._msg_timer.stop()
        if text:
            self._msg_timer = QTimer(self)
            self._msg_timer.setSingleShot(True)
            self._msg_timer.timeout.connect(lambda: self.msg_label.setText(""))
            self._msg_timer.start(5000)

    def set_email_message(self, text: str, ok: bool = False) -> None:
        self.email_msg_label.setStyleSheet("color: #5BB85D;" if ok else "color: #FF6B6B;")
        self.email_msg_label.setText(text)
        if ok:
            self.new_email_input.clear()
            self.email_pw_input.clear()
        if hasattr(self, "_email_msg_timer") and self._email_msg_timer is not None:
            self._email_msg_timer.stop()
        if text:
            self._email_msg_timer = QTimer(self)
            self._email_msg_timer.setSingleShot(True)
            self._email_msg_timer.timeout.connect(lambda: self.email_msg_label.setText(""))
            self._email_msg_timer.start(5000)

    # ── Geometry layout ───────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        self._bg.setGeometry(0, 0, w, h)
        self._dark_overlay.setGeometry(0, 0, w, h)
        self._sidebar.setGeometry(0, 0, 90, h)
        self._content.setGeometry(90, 0, w - 90, h)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        w, h = self.width(), self.height()
        self._bg.setGeometry(0, 0, w, h)
        self._dark_overlay.setGeometry(0, 0, w, h)
        self._sidebar.setGeometry(0, 0, 90, h)
        self._content.setGeometry(90, 0, w - 90, h)
        self._bg.lower()
        self._dark_overlay.stackUnder(self._sidebar)
        self.user_nav_btn.setChecked(True)
        self.home_nav_btn.setChecked(False)
        self._select_tab(0)
