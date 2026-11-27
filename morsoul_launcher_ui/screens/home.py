"""Home screen — redesigned to match the new Morsoul UI mockup."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from morsoul_launcher import strings
from morsoul_launcher.appstate import AppState, AuthKind, GameKind, UpdateKind
from morsoul_launcher_ui.theme import ASSETS, get_font_family

# ── Asset paths ───────────────────────────────────────────────────────────────
_BI = ASSETS / "button_icons"


def _scaled_pix(path: str | None, w: int, h: int) -> QPixmap | None:
    if path is None:
        return None
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return None
    return QPixmap(str(p)).scaled(
        w,
        h,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


# ── Sidebar icon button ───────────────────────────────────────────────────────


class _SideBtn(QPushButton):
    """Sidebar nav icon — shows off/on PNG, no text, no border."""

    def __init__(self, icon_off: str, icon_on: str = "", *, checkable: bool = False, size: int = 32) -> None:
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


class _ChipLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)


# ── Pill action button (Play / Sync) ─────────────────────────────────────────


def _make_pill_btn(
    label: str,
    icon_name: str,
    *,
    gold: bool = False,
    min_width: int = 110,
    height: int = 52,
) -> QPushButton:
    fonts = get_font_family()
    radius = height // 2

    if gold:
        bg = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #E2BD62, stop:0.5 #CBA344, stop:1 #B28B2C)"
        bg_hov = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #F0D07C, stop:0.5 #DDB754, stop:1 #C49B38)"
        bg_prs = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #B28B2C, stop:1 #8F6D1F)"
        bg_dis = "rgba(80, 72, 54, 0.40)"
        fg = "#171204"
        fg_dis = "rgba(180, 170, 150, 0.40)"
        border = "1px solid rgba(255, 245, 200, 0.50)"
    else:
        bg = "rgba(26, 24, 20, 0.85)"
        bg_hov = "rgba(45, 40, 32, 0.95)"
        bg_prs = "rgba(18, 16, 12, 0.95)"
        bg_dis = "rgba(30,28,24,0.45)"
        fg = "#F0EDE6"
        fg_dis = "rgba(255,255,255,0.30)"
        border = "1.5px solid rgba(203, 163, 68, 0.45)"

    btn = QPushButton(f"  {label}")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedHeight(height)
    btn.setMinimumWidth(min_width)

    p = _BI / icon_name
    if p.exists():
        pix = QPixmap(str(p))
        btn.setIcon(QIcon(pix))
        btn.setIconSize(QSize(22, 22))

    btn.setStyleSheet(f"""
        QPushButton {{
            background: {bg};
            color: {fg};
            border: {border};
            border-radius: {radius}px;
            padding: 7px 18px;
            font-size: 16px;
            font-weight: 700;
            font-family: {fonts};
            letter-spacing: 0.5px;
            text-align: center;
            min-width: 120px;
        }}
        QPushButton:hover   {{ background: {bg_hov}; border: 1px solid rgba(255, 255, 255, 0.65); }}
        QPushButton:pressed {{ background: {bg_prs}; }}
        QPushButton:disabled {{
            background: rgba(35, 30, 22, 0.85);
            color: #E2BD62;
            border: 1px solid rgba(203, 163, 68, 0.50);
        }}
    """)
    return btn


# ── Main screen ───────────────────────────────────────────────────────────────


class HomeScreen(QWidget):
    check_updates = Signal()
    sync_clicked = Signal()
    launch_clicked = Signal()
    account_clicked = Signal()
    sync_chip_clicked = Signal()
    progress_clicked = Signal()
    minimize_clicked = Signal()
    close_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("homeRoot")

        # ── z-order layer 0: background image ────────────────────────────────
        self._bg = QFrame(self)
        self._bg.setObjectName("bgFrame")
        self._apply_bg()

        # ── z-order layer 1: full-screen dark vignette / gradient ─────────────
        self._gradient = QFrame(self)
        self._gradient.setObjectName("gradientOverlay")
        self._gradient.setStyleSheet(
            "QFrame#gradientOverlay {"
            "  background: qlineargradient("
            "    x1:0, y1:0, x2:1, y2:0,"
            "    stop:0   rgba(15,14,12,0.82),"
            "    stop:0.38 rgba(15,14,12,0.55),"
            "    stop:0.62 rgba(15,14,12,0.18),"
            "    stop:1   rgba(15,14,12,0.0)"
            "  );"
            "}"
        )

        # ── z-order layer 2: left sidebar ────────────────────────────────────
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

        # ── Top zone: game icon ───────────────────────────────────────────────
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

        # ── Mid zone: nav pill capsule ────────────────────────────────────────
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

        # User / Account — mutually exclusive with home
        self.icon_holder = _SideBtn("user_notclicked.png", "user_clicked.png", checkable=True, size=24)
        self.icon_holder.setToolTip("Account & Settings")
        self.icon_holder.clicked.connect(self._on_user_nav)
        mz.addWidget(self.icon_holder, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Home — mutually exclusive with user; starts active
        self.home_btn = _SideBtn("home_notclicked.png", "home_clicked.png", checkable=True, size=24)
        self.home_btn.setToolTip("Home")
        self.home_btn.setChecked(True)
        self.home_btn.clicked.connect(self._on_home_nav)
        mz.addWidget(self.home_btn, alignment=Qt.AlignmentFlag.AlignHCenter)

        sb.addWidget(mid_zone, alignment=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)

        # ── Bottom zone: updates icon ─────────────────────────────────────────
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

        # ── z-order layer 3: main content ─────────────────────────────────────
        self._content = QWidget(self)
        self._content.setObjectName("contentHost")
        self._content.setStyleSheet("background: transparent;")

        content_root = QVBoxLayout(self._content)
        content_root.setContentsMargins(0, 0, 0, 0)
        content_root.setSpacing(0)

        # title bar (minimize / close only)
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

        # centre column
        centre = QVBoxLayout()
        centre.setContentsMargins(32, 32, 32, 0)
        centre.setSpacing(0)

        centre.addStretch()

        # version pill
        self.update_chip = QLabel("Latest Ver.")
        self.update_chip.setObjectName("versionPill")
        self.update_chip.setFixedHeight(42)
        self.update_chip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        centre.addWidget(self.update_chip, alignment=Qt.AlignmentFlag.AlignLeft)
        centre.addSpacing(16)

        # genre badge
        genre_badge = QLabel("OCCULT INVESTIGATION • AGARTHA NOIR")
        genre_badge.setObjectName("genreBadge")
        genre_badge.setStyleSheet(f"""
            color: #CBA344;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 2.5px;
            background: transparent;
            font-family: {get_font_family()};
        """)
        centre.addWidget(genre_badge)

        # title
        brand = QLabel("MORSOUL")
        brand.setObjectName("brand")
        centre.addWidget(brand)

        sub = QLabel("World's Case")
        sub.setObjectName("brandSub")
        centre.addWidget(sub)
        centre.addSpacing(10)

        # decorative divider
        divider = QFrame()
        divider.setObjectName("brandDivider")
        divider.setFixedHeight(2)
        divider.setFixedWidth(140)
        divider.setStyleSheet("""
            QFrame#brandDivider {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(203, 163, 68, 0.85),
                    stop:0.7 rgba(203, 163, 68, 0.35),
                    stop:1.0 rgba(203, 163, 68, 0.0)
                );
                border: none;
            }
        """)
        centre.addWidget(divider)
        centre.addSpacing(14)

        # synopsis
        self.synopsis = QLabel(strings.SYNOPSIS)
        self.synopsis.setObjectName("synopsisBody")
        self.synopsis.setWordWrap(True)
        self.synopsis.setMaximumWidth(460)
        centre.addWidget(self.synopsis)
        centre.addSpacing(28)

        # ── Play + Sync inline below synopsis ─────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(12)

        self.launch_btn = _make_pill_btn("Play", "Launch.png", gold=True)
        self.launch_btn.clicked.connect(self.launch_clicked.emit)


        btn_row.addWidget(self.launch_btn)

        self.sync_btn = _make_pill_btn("Sync", "Sync.png", gold=True)
        self.sync_btn.clicked.connect(self.sync_clicked.emit)
        btn_row.addWidget(self.sync_btn)

        btn_row.addStretch()
        centre.addLayout(btn_row)

        # Update progress bar & percentage label
        self.update_progress_container = QWidget()
        self.update_progress_container.setStyleSheet("background: transparent;")
        prog_lay = QVBoxLayout(self.update_progress_container)
        prog_lay.setContentsMargins(0, 8, 0, 0)
        prog_lay.setSpacing(6)

        self.update_progress_lbl = QLabel("")
        fonts = get_font_family()
        self.update_progress_lbl.setStyleSheet(f"font-size: 12px; font-weight: 600; color: #E2BD62; font-family: {fonts};")
        prog_lay.addWidget(self.update_progress_lbl)

        self.update_progress_bar = QProgressBar()
        self.update_progress_bar.setFixedHeight(8)
        self.update_progress_bar.setTextVisible(False)
        self.update_progress_bar.setRange(0, 100)
        self.update_progress_bar.setValue(0)
        self.update_progress_bar.setMaximumWidth(380)
        self.update_progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(30, 28, 24, 0.7);
                border: 1px solid rgba(203, 163, 68, 0.35);
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #CBA344, stop:1 #E2BD62);
                border-radius: 3px;
            }
        """)
        prog_lay.addWidget(self.update_progress_bar)
        self.update_progress_container.hide()
        centre.addWidget(self.update_progress_container)

        # banner
        self.banner = QLabel("")
        self.banner.setObjectName("banner")
        self.banner.hide()
        centre.addSpacing(10)
        centre.addWidget(self.banner)

        centre.addStretch()

        self._centre_widget = QWidget()
        self._centre_widget.setStyleSheet("background:transparent;")
        self._centre_widget.setLayout(centre)
        content_root.addWidget(self._centre_widget, stretch=1)

        # footer: auth chip pinned bottom-right
        footer = QHBoxLayout()
        footer.setContentsMargins(32, 0, 32, 24)
        footer.addStretch()

        self.sync_chip = _ChipLabel(strings.NOT_SIGNED_IN)
        self.sync_chip.setObjectName("chip")
        self.sync_chip.setFixedHeight(42)
        self.sync_chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sync_chip.clicked.connect(self._on_sync_chip_clicked)

        footer.addWidget(self.sync_chip, alignment=Qt.AlignmentFlag.AlignVCenter)
        content_root.addLayout(footer)

        # hidden progress link — kept for main_window.py wiring compat
        self.progress_link = QPushButton("My Progress")
        self.progress_link.setObjectName("subtleLink")
        self.progress_link.hide()
        self.progress_link.clicked.connect(self.progress_clicked.emit)

        self._is_offline_mode: bool = False

    # ── Nav mutual exclusion ──────────────────────────────────────────────────

    def _on_sync_chip_clicked(self) -> None:
        self.sync_chip_clicked.emit()

    def _on_user_nav(self) -> None:
        """User clicked — highlight user, un-highlight home, open account."""
        if getattr(self, "_is_offline_mode", False):
            self.icon_holder.setChecked(False)
            self.home_btn.setChecked(True)
            self.account_clicked.emit()
            return
        self.icon_holder.setChecked(True)
        self.home_btn.setChecked(False)
        self.account_clicked.emit()

    def _on_home_nav(self) -> None:
        """Home clicked — highlight home, un-highlight user. No other action."""
        self.home_btn.setChecked(True)
        self.icon_holder.setChecked(False)

    # ── Geometry ──────────────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        self._bg.setGeometry(0, 0, w, h)
        self._gradient.setGeometry(0, 0, w, h)
        self._sidebar.setGeometry(0, 0, 90, h)
        self._content.setGeometry(90, 0, w - 90, h)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        w, h = self.width(), self.height()
        self._bg.setGeometry(0, 0, w, h)
        self._gradient.setGeometry(0, 0, w, h)
        self._sidebar.setGeometry(0, 0, 90, h)
        self._content.setGeometry(90, 0, w - 90, h)
        self._bg.lower()
        self._gradient.raise_()
        self._sidebar.raise_()
        self._content.raise_()
        self._animate_content_entrance()

    def _animate_content_entrance(self) -> None:
        if hasattr(self, "_anim_entrance") and self._anim_entrance.state() == QPropertyAnimation.State.Running:
            return
        curr_pos = self._centre_widget.pos()
        self._anim_entrance = QPropertyAnimation(self._centre_widget, b"pos", self)
        self._anim_entrance.setDuration(260)
        self._anim_entrance.setStartValue(curr_pos + QPoint(0, 12))
        self._anim_entrance.setEndValue(curr_pos)
        self._anim_entrance.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_entrance.start()

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
                f"QFrame {{ border-image: url({found.as_posix()}) 0 0 0 0 stretch stretch; }}"
            )
        else:
            self._bg.setStyleSheet(
                "QFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                " stop:0 #1a2a1a, stop:0.5 #2a3a28, stop:1 #0d1a12); }"
            )

    # ── State rendering ───────────────────────────────────────────────────────

    def render_state(self, state: AppState) -> None:
        self._is_offline_mode = (
            state.auth.kind == AuthKind.OFFLINE_MODE or state.network.value == "offline"
        )
        if self._is_offline_mode:
            self.icon_holder.setChecked(False)
            self.home_btn.setChecked(True)

        # version pill - if offline, show "You are offline. You can still play." in top pill
        uk = state.update.kind
        pct = int(state.update.progress * 100) if state.update.progress else 0
        if self._is_offline_mode:
            self.update_chip.setText("You are offline. You can still play.")
        elif uk == UpdateKind.AVAILABLE:
            self.update_chip.setText("Update Available")
        elif uk == UpdateKind.DOWNLOADING:
            self.update_chip.setText(f"Updating {pct}%" if pct > 0 else "Updating...")
        elif uk in {UpdateKind.APPLYING, UpdateKind.VERIFYING}:
            self.update_chip.setText(f"Installing {pct}%" if pct > 0 else "Installing...")
        elif uk == UpdateKind.FAILED:
            self.update_chip.setText(strings.UPDATE_FAILED)
        else:
            self.update_chip.setText(strings.UP_TO_DATE)

        # auth/mode chip at bottom-right:
        # "if it's offline it will say 'Offline Mode' if it's in online mode you can say 'Online Mode'"
        if self._is_offline_mode:
            self.sync_chip.setText("Offline Mode")
        else:
            self.sync_chip.setText("Online Mode")

        # launch button & progress display
        applying = state.update.kind in {
            UpdateKind.DOWNLOADING,
            UpdateKind.APPLYING,
            UpdateKind.VERIFYING,
        }
        running = state.game == GameKind.RUNNING
        self.launch_btn.setEnabled(not applying and not running)
        if applying:
            self.update_progress_container.show()
            self.update_progress_bar.setValue(pct)
            status_txt = getattr(state.update, "status_text", "") or ""
            if state.update.kind in {UpdateKind.APPLYING, UpdateKind.VERIFYING}:
                self.launch_btn.setText(f"  Installing... {pct}%" if pct > 0 else "  Installing...")
                self.update_progress_lbl.setText(f"Installing: {status_txt}" if status_txt else f"Installing game files... {pct}%")
            else:
                self.launch_btn.setText(f"  Updating... {pct}%" if pct > 0 else "  Updating...")
                self.update_progress_lbl.setText(f"Updating: {status_txt}" if status_txt else f"Downloading update... {pct}%")
        else:
            self.update_progress_container.hide()
            if state.update.kind == UpdateKind.AVAILABLE:
                self.launch_btn.setText("  Update")
            elif running:
                self.launch_btn.setText(f"  {strings.GAME_RUNNING}")
            else:
                self.launch_btn.setText("  Play")

        # banner: hide offline banner so the long empty box does not display
        active_banners = [
            b for b in state.banners if b.id != "offline" and "offline" not in b.message.lower()
        ]
        if active_banners:
            self.banner.setText(active_banners[-1].message)
            self.banner.show()
        else:
            self.banner.hide()
