"""My Progress overlay + conflict dialog styled with clean, modern card theme."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from morsoul_launcher import strings
from morsoul_launcher.appstate import AppState, ProfileView, SyncState
from morsoul_launcher.profile_service import format_playtime
from morsoul_launcher_ui.theme import get_font_family

_DARK_TEXT = "#1F2937"
_MUTED_TEXT = "#6B7280"
_SUBTLE_TEXT = "#9CA3AF"
_WHITE = "#FFFFFF"

_SYNC_LABELS = {
    SyncState.SYNCED: strings.SYNCED,
    SyncState.LOCAL_NEWER: strings.THIS_DEVICE_NEWER,
    SyncState.CLOUD_NEWER: strings.CLOUD_NEWER,
    SyncState.CONFLICT: strings.NEEDS_CHOICE,
    SyncState.LOCAL_ONLY: strings.THIS_DEVICE_ONLY,
    SyncState.CLOUD_ONLY: strings.CLOUD_ONLY,
    SyncState.SYNCING: strings.SYNCING,
    SyncState.ERROR: "Error",
    SyncState.SKIPPED: "Skipped",
}


class ProgressOverlay(QFrame):
    """Modern progress manager overlay card with profile switching and sync controls."""

    sync_all = Signal()
    sync_one = Signal(str)
    download = Signal(str)
    delete_cloud = Signal(str)
    resolve = Signal(str, str)  # profile_id, keep_local|keep_cloud
    switch_profile = Signal(str)  # profile_id to activate
    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("progressOverlayCard")
        self.setFixedSize(680, 520)
        fonts = get_font_family()

        # Clean white card matching modern toast & modal system
        self.setStyleSheet("""
            QFrame#progressOverlayCard {
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
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        # ── Header ────────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        title = QLabel(strings.MY_PROGRESS)
        title.setStyleSheet(f"""
            font-size: 19px;
            font-weight: 600;
            color: {_DARK_TEXT};
            font-family: {fonts};
            background: transparent;
            border: none;
        """)
        title_box.addWidget(title)

        subtitle = QLabel("Select and manage your local & cloud investigation profiles:")
        subtitle.setStyleSheet(f"""
            color: {_MUTED_TEXT};
            font-size: 12.5px;
            font-weight: 400;
            font-family: {fonts};
            background: transparent;
            border: none;
        """)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)

        header.addStretch()

        # Sync All button in header row
        self.sync_all_btn = QPushButton(f"⟳  {strings.SYNC_ALL}")
        self.sync_all_btn.setFixedHeight(34)
        self.sync_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sync_all_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #1F2937;
                color: #FFFFFF;
                font-weight: 600;
                font-size: 12px;
                border-radius: 8px;
                border: none;
                padding: 0 16px;
                font-family: {fonts};
            }}
            QPushButton:hover {{
                background-color: #374151;
            }}
            QPushButton:pressed {{
                background-color: #111827;
            }}
        """)
        self.sync_all_btn.clicked.connect(self.sync_all.emit)
        header.addWidget(self.sync_all_btn)

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
        header.addWidget(close_btn)

        layout.addLayout(header)

        # ── Scroll Area for Profile Cards ─────────────────────────────────────
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #E5E7EB;
                border-radius: 3px;
                min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: #D1D5DB;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self.list_host = QWidget()
        self.list_host.setStyleSheet("background: transparent; border: none;")
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 4, 6, 4)
        self.list_layout.setSpacing(12)
        self.scroll_area.setWidget(self.list_host)
        layout.addWidget(self.scroll_area, stretch=1)

        # Clean empty label (no black background)
        self.empty = QLabel(strings.EMPTY_PROFILES)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setStyleSheet(f"""
            color: {_SUBTLE_TEXT};
            font-size: 13px;
            font-weight: 400;
            padding: 30px;
            font-family: {fonts};
            background: transparent;
            border: none;
        """)
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)

    def render_state(self, state: AppState) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item:
                w = item.widget()
                if w:
                    w.deleteLater()

        profiles = list(state.profiles) if state.profiles else []

        self.empty.setVisible(not profiles)
        for idx, p in enumerate(profiles):
            is_active = (idx == 0)
            self.list_layout.addWidget(self._row(p, is_active=is_active))
        self.list_layout.addStretch()

    def _row(self, p: ProfileView, is_active: bool = False) -> QWidget:
        fonts = get_font_family()
        row = QFrame()

        if is_active:
            row.setStyleSheet("""
                QFrame {
                    background-color: #F0FDF4;
                    border: 1.5px solid #86EFAC;
                    border-radius: 12px;
                }
            """)
        else:
            row.setStyleSheet("""
                QFrame {
                    background-color: #F9FAFB;
                    border: 1.5px solid #E5E7EB;
                    border-radius: 12px;
                }
                QFrame:hover {
                    background-color: #F3F4F6;
                    border-color: #D1D5DB;
                }
            """)

        lay = QVBoxLayout(row)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        # Top row: Name, Case subtitle, Sync status tag
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)

        name_lbl = QLabel(p.display_name or p.profile_id)
        name_lbl.setStyleSheet(f"""
            color: {_DARK_TEXT};
            font-size: 15px;
            font-weight: 600;
            font-family: {fonts};
            background: transparent;
            border: none;
        """)
        top.addWidget(name_lbl)

        case_lbl = QLabel(f"·  {p.current_case_id or 'Case 1: The Hollow Core'}")
        case_lbl.setStyleSheet(f"""
            color: {_MUTED_TEXT};
            font-size: 12px;
            font-weight: 400;
            font-family: {fonts};
            background: transparent;
            border: none;
        """)
        top.addWidget(case_lbl)

        top.addStretch()

        # Status badge
        sync_text = _SYNC_LABELS.get(p.sync_state, p.sync_state.value)
        status_lbl = QLabel(sync_text.upper())
        if p.sync_state == SyncState.SYNCED:
            badge_style = "background: #DEF7EC; color: #03543F; border: 1px solid #BCF0DA;"
        elif p.sync_state == SyncState.LOCAL_ONLY:
            badge_style = "background: #E1EFFE; color: #1E429F; border: 1px solid #B4C6FC;"
        elif p.sync_state == SyncState.CLOUD_ONLY:
            badge_style = "background: #EDEBFE; color: #5521B5; border: 1px solid #DCD7FE;"
        elif p.sync_state == SyncState.CONFLICT:
            badge_style = "background: #FEF08A; color: #854D0E; border: 1px solid #FDE047;"
        else:
            badge_style = "background: #F3F4F6; color: #4B5563; border: 1px solid #E5E7EB;"

        status_lbl.setStyleSheet(f"""
            {badge_style}
            font-size: 10.5px;
            font-weight: 600;
            border-radius: 6px;
            padding: 3px 8px;
            font-family: {fonts};
        """)
        top.addWidget(status_lbl)
        lay.addLayout(top)

        # Middle row: Meta stats
        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.setSpacing(16)

        time_str = format_playtime(p.playtime) if p.playtime > 0 else "0 mins"
        stats_text = (
            f"Solved: <b>{p.cases_completed}/6</b>     "
            f"Runic Logs: <b>{p.runic_logs}/4</b>     "
            f"Playtime: <b>{time_str}</b>"
        )
        meta_lbl = QLabel(stats_text)
        meta_lbl.setStyleSheet(f"""
            color: #4B5563;
            font-size: 12px;
            font-family: {fonts};
            background: transparent;
            border: none;
        """)
        stats_row.addWidget(meta_lbl)
        stats_row.addStretch()
        lay.addLayout(stats_row)

        # Bottom row: Switch button & sync actions
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)

        if is_active:
            active_badge = QLabel("✓ Active Profile")
            active_badge.setStyleSheet(f"""
                QLabel {{
                    background-color: #DCFCE7;
                    color: #15803D;
                    font-size: 11.5px;
                    font-weight: 600;
                    border-radius: 6px;
                    padding: 4px 12px;
                    border: 1px solid #86EFAC;
                    font-family: {fonts};
                }}
            """)
            actions.addWidget(active_badge)
        else:
            switch_btn = QPushButton("Switch to Profile")
            switch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            switch_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #1F2937;
                    color: #FFFFFF;
                    font-size: 11.5px;
                    font-weight: 600;
                    border-radius: 6px;
                    border: none;
                    padding: 5px 14px;
                    font-family: {fonts};
                }}
                QPushButton:hover {{
                    background-color: #374151;
                }}
                QPushButton:pressed {{
                    background-color: #111827;
                }}
            """)
            switch_btn.clicked.connect(lambda _, pid=p.profile_id: self.switch_profile.emit(pid))
            actions.addWidget(switch_btn)

        actions.addSpacing(6)

        btn_css = f"""
            QPushButton {{
                background-color: #FFFFFF;
                border: 1.5px solid #D1D5DB;
                border-radius: 6px;
                color: #374151;
                font-size: 11px;
                font-weight: 500;
                padding: 4px 10px;
                font-family: {fonts};
            }}
            QPushButton:hover {{
                background-color: #F3F4F6;
                border-color: #9CA3AF;
            }}
        """

        if p.sync_state == SyncState.CLOUD_ONLY:
            dl_btn = QPushButton(f"⬇  {strings.DOWNLOAD_TO_DEVICE}")
            dl_btn.setStyleSheet(btn_css)
            dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            dl_btn.clicked.connect(lambda: self.download.emit(p.profile_id))
            actions.addWidget(dl_btn)
        else:
            sync_btn = QPushButton(f"⟳  {strings.SYNC_NOW}")
            sync_btn.setStyleSheet(btn_css)
            sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            sync_btn.clicked.connect(lambda: self.sync_one.emit(p.profile_id))
            actions.addWidget(sync_btn)

        if p.sync_state == SyncState.CONFLICT:
            choose = QPushButton(f"⚠  {strings.NEEDS_CHOICE}")
            choose.setCursor(Qt.CursorShape.PointingHandCursor)
            choose.setStyleSheet(f"""
                QPushButton {{
                    background-color: #FEF08A;
                    border: 1px solid #EAB308;
                    border-radius: 6px;
                    color: #854D0E;
                    font-size: 11px;
                    font-weight: 600;
                    padding: 4px 10px;
                    font-family: {fonts};
                }}
            """)
            choose.clicked.connect(lambda: self._conflict(p))
            actions.addWidget(choose)

        del_btn = QPushButton("Delete Cloud Copy")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #FFFFFF;
                border: 1px solid #FCA5A5;
                border-radius: 6px;
                color: #DC2626;
                font-size: 11px;
                font-weight: 500;
                padding: 4px 10px;
                font-family: {fonts};
            }}
            QPushButton:hover {{
                background-color: #FEE2E2;
                border-color: #EF4444;
            }}
        """)
        del_btn.clicked.connect(lambda: self._confirm_delete(p.profile_id))
        actions.addWidget(del_btn)
        actions.addStretch()

        lay.addLayout(actions)
        return row

    def _confirm_delete(self, profile_id: str) -> None:
        r = QMessageBox.question(self, strings.DELETE_CLOUD, strings.DELETE_CLOUD_CONFIRM)
        if r == QMessageBox.StandardButton.Yes:
            self.delete_cloud.emit(profile_id)

    def _conflict(self, p: ProfileView) -> None:
        fonts = get_font_family()
        dlg = QDialog(self)
        dlg.setWindowTitle(strings.NEEDS_CHOICE)
        dlg.setFixedSize(500, 310)
        dlg.setStyleSheet("""
            QDialog {
                background-color: #FFFFFF;
                color: #1F2937;
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 14px;
            }
        """)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        t = QLabel(strings.REVISION_CONFLICT)
        t.setStyleSheet(f"color: #1F2937; font-size: 15px; font-weight: 600; font-family: {fonts};")
        lay.addWidget(t)

        cards = QHBoxLayout()
        cards.setSpacing(12)

        local_time = format_playtime(p.playtime)
        local = QLabel(
            f"<b>This Device</b><br><br>"
            f"Case: {p.current_case_id or '—'}<br>"
            f"Completed: {p.cases_completed}/6<br>"
            f"Runic Logs: {p.runic_logs}/4<br>"
            f"Playtime: {local_time}"
        )

        cloud_s = p.cloud_summary or {}
        c_playtime = int(cloud_s.get("playtime") or 0)
        cloud_time = format_playtime(c_playtime)
        cloud = QLabel(
            f"<b>Cloud Copy</b><br><br>"
            f"Case: {cloud_s.get('currentCaseID') or '—'}<br>"
            f"Completed: {cloud_s.get('casesCompleted') or 0}/6<br>"
            f"Runic Logs: {cloud_s.get('runicLogs') or 0}/4<br>"
            f"Playtime: {cloud_time}"
        )

        card_css = f"""
            QLabel {{
                background-color: #F9FAFB;
                border: 1.5px solid #E5E7EB;
                border-radius: 8px;
                padding: 12px;
                color: #374151;
                font-size: 12px;
                font-family: {fonts};
            }}
        """
        for w in (local, cloud):
            w.setStyleSheet(card_css)
            cards.addWidget(w)
        lay.addLayout(cards)

        buttons = QDialogButtonBox()
        keep_l = buttons.addButton(strings.KEEP_LOCAL, QDialogButtonBox.ButtonRole.AcceptRole)
        keep_c = buttons.addButton(strings.KEEP_CLOUD, QDialogButtonBox.ButtonRole.DestructiveRole)
        later = buttons.addButton(strings.DECIDE_LATER, QDialogButtonBox.ButtonRole.RejectRole)
        lay.addWidget(buttons)

        def _choose_local() -> None:
            self.resolve.emit(p.profile_id, "keep_local")
            dlg.accept()

        def _choose_cloud() -> None:
            self.resolve.emit(p.profile_id, "keep_cloud")
            dlg.accept()

        keep_l.clicked.connect(_choose_local)
        keep_c.clicked.connect(_choose_cloud)
        later.clicked.connect(dlg.reject)
        dlg.exec()
