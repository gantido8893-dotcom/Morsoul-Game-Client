"""Colors, fonts, and shared styles — Poppins + new Morsoul UI."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtGui import QFontDatabase

log = logging.getLogger("morsoul.launcher.theme")

# ── Colors ────────────────────────────────────────────────────────────────────
GOLD = "#CBA344"
GOLD_LIGHT = "#E8C86A"
GOLD_DARK = "#9E7B28"
PARCHMENT = "#C8A84B"
PARCHMENT_HOVER = "#E2C889"
PARCHMENT_BORDER = "#B8995A"
DARK_TEXT = "#1C1812"
DARK = "#121212"
WHITE = "#FFFFFF"
MODAL_BG = "#FFFFFF"
MODAL_INPUT = "#FFFFFF"
MODAL_BORDER = "#D6D6D6"
MODAL_BTN = "#363636"
MODAL_BTN_HOVER = "#484848"
MODAL_BTN_TEXT = "#DFC47E"

# ── Window size ───────────────────────────────────────────────────────────────
WINDOW_W = 1260
WINDOW_H = 750


# ── Paths ─────────────────────────────────────────────────────────────────────
def _find_assets_dir() -> Path:
    local = Path(__file__).resolve().parent / "assets"
    if local.is_dir():
        return local
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass_pkg = Path(sys._MEIPASS) / "morsoul_launcher_ui" / "assets"
        if meipass_pkg.is_dir():
            return meipass_pkg
        meipass_root = Path(sys._MEIPASS) / "assets"
        if meipass_root.is_dir():
            return meipass_root
    exe_assets = Path(sys.executable).parent / "assets"
    if exe_assets.is_dir():
        return exe_assets
    return local


ASSETS = _find_assets_dir()
FONTS_DIR = ASSETS / "fonts"

_LOADED_FONT_FAMILY: str | None = None


def load_application_fonts() -> str:
    """Scan assets/fonts for .ttf/.otf files and register them with Qt."""
    global _LOADED_FONT_FAMILY
    if _LOADED_FONT_FAMILY is not None:
        return _LOADED_FONT_FAMILY

    try:
        FONTS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    loaded_families: list[str] = []
    for ext in ("*.ttf", "*.otf"):
        for font_file in sorted(FONTS_DIR.glob(ext)):
            font_id = QFontDatabase.addApplicationFont(str(font_file))
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                loaded_families.extend(families)
                log.info("Loaded font: %s from %s", families, font_file.name)

    # Prefer Poppins if present; fall back to clean system sans-serifs
    poppins = [f for f in loaded_families if "Poppins" in f]
    if poppins:
        primary = f'"{poppins[0]}", '
    elif loaded_families:
        primary = f'"{loaded_families[0]}", '
    else:
        primary = ""

    _LOADED_FONT_FAMILY = f'{primary}"Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif'
    return _LOADED_FONT_FAMILY


def get_font_family() -> str:
    return _LOADED_FONT_FAMILY or load_application_fonts()


def stylesheet() -> str:  # noqa: PLR0915  (long but one function)
    fonts = get_font_family()
    return f"""

    /* ── Window shell ─────────────────────────────────────────────────── */
    QMainWindow {{
        background-color: {DARK};
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 14px;
    }}

    QWidget#homeRoot,
    QWidget#authRoot,
    QWidget#accountRoot {{
        background-color: transparent;
        color: {WHITE};
        font-family: {fonts};
    }}

    /* ── Window control buttons ───────────────────────────────────────── */
    QPushButton#winBtn {{
        background: transparent;
        color: rgba(255,255,255,0.70);
        border: none;
        font-size: 16px;
        font-weight: 400;
        min-width: 34px;
        max-width: 34px;
        min-height: 28px;
        max-height: 28px;
        border-radius: 4px;
        padding: 0;
        font-family: {fonts};
    }}
    QPushButton#winBtn:hover {{
        background: rgba(255,255,255,0.12);
        color: {WHITE};
    }}
    QPushButton#winCloseBtn {{
        background: transparent;
        color: rgba(255,255,255,0.70);
        border: none;
        font-size: 16px;
        font-weight: 400;
        min-width: 34px;
        max-width: 34px;
        min-height: 28px;
        max-height: 28px;
        border-radius: 4px;
        padding: 0;
        font-family: {fonts};
    }}
    QPushButton#winCloseBtn:hover {{
        background: #C42B1C;
        color: {WHITE};
    }}

    /* ── Branding ─────────────────────────────────────────────────────── */
    QLabel#brand {{
        color: #DFC47E;
        font-size: 72px;
        font-weight: 800;
        font-family: {fonts};
        letter-spacing: 6px;
        background: transparent;
    }}
    QLabel#brandSub {{
        color: {GOLD};
        font-size: 24px;
        font-weight: 700;
        font-family: {fonts};
        letter-spacing: 2px;
        background: transparent;
        margin-top: -6px;
    }}

    /* ── Synopsis ─────────────────────────────────────────────────────── */
    QLabel#synopsisBody {{
        color: rgba(235, 230, 220, 0.88);
        font-size: 13.5px;
        font-weight: 400;
        line-height: 1.55;
        font-family: {fonts};
        background: transparent;
    }}

    /* ── Version / status pill (top-left) ────────────────────────────── */
    QLabel#versionPill {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 rgba(28, 25, 22, 0.88),
            stop:1 rgba(42, 37, 32, 0.78)
        );
        color: #E6E1D6;
        padding: 9px 20px;
        border-radius: 18px;
        border: 1px solid rgba(203, 163, 68, 0.40);
        font-size: 13px;
        font-weight: 600;
        font-family: {fonts}; 
        letter-spacing: 0.3px;
    }}

    /* ── Auth / status chip (bottom-right) ───────────────────────────── */
    QLabel#chip {{
        background: rgba(36, 32, 26, 0.50);
        color: #E6E1D6;
        padding: 9px 20px;
        border-radius: 18px;
        border: none;
        font-size: 13px;
        font-weight: 600;
        font-family: {fonts};
        letter-spacing: 0.3px;
    }}
    QLabel#chip:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 rgba(44, 38, 30, 0.95),
            stop:1 rgba(58, 50, 40, 0.90)
        );
        border: 1px solid rgba(203, 163, 68, 0.70);
        color: #FFFFFF;
    }}

    /* ── Play button ──────────────────────────────────────────────────── */
    QPushButton#playBtn {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #E2BD62,
            stop:0.5 #CBA344,
            stop:1 #B28B2C
        );
        color: #171204;
        border: 1px solid rgba(255, 245, 200, 0.45);
        border-radius: 20px;
        padding: 8px 22px;
        font-size: 15px;
        font-weight: 800;
        font-family: {fonts};
        letter-spacing: 0.5px;
        min-width: 110px;
        min-height: 40px;
    }}
    QPushButton#playBtn:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #F0D07C,
            stop:0.5 #DDB754,
            stop:1 #C49B38
        );
        border: 1px solid rgba(255, 255, 255, 0.75);
    }}
    QPushButton#playBtn:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #B28B2C,
            stop:1 #8F6D1F
        );
    }}
    QPushButton#playBtn:disabled {{
        background: rgba(80, 72, 54, 0.40);
        color: rgba(180, 170, 150, 0.40);
        border: 1px solid rgba(255, 255, 255, 0.08);
    }}

    /* ── Sync button ──────────────────────────────────────────────────── */
    QPushButton#syncBtn {{
        background-color: rgba(26, 24, 20, 0.85);
        color: #F0EDE6;
        border: 1.5px solid rgba(203, 163, 68, 0.45);
        border-radius: 20px;
        padding: 8px 20px;
        font-size: 14px;
        font-weight: 700;
        font-family: {fonts};
        letter-spacing: 0.4px;
        min-width: 90px;
        min-height: 40px;
    }}
    QPushButton#syncBtn:hover {{
        background-color: rgba(45, 40, 32, 0.95);
        border: 1.5px solid rgba(203, 163, 68, 0.85);
        color: #FFDF85;
    }}
    QPushButton#syncBtn:pressed {{
        background-color: rgba(20, 18, 15, 0.95);
        border: 1.5px solid rgba(203, 163, 68, 0.60);
    }}

    /* ── Banner ───────────────────────────────────────────────────────── */
    QLabel#banner {{
        background-color: rgba(30,28,24,0.92);
        color: {GOLD_LIGHT};
        padding: 8px 16px;
        border-radius: 8px;
        border: 1px solid rgba(203, 163, 68, 0.45);
        font-size: 12.5px;
        font-family: {fonts};
        font-weight: 500;
    }}

    /* ── Custom Scrollbar ────────────────────────────────────────────── */
    QScrollBar:vertical {{
        border: none;
        background: rgba(20, 20, 20, 0.35);
        width: 8px;
        margin: 0;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(203, 163, 68, 0.45);
        min-height: 24px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: rgba(203, 163, 68, 0.75);
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    /* ── Tooltip ─────────────────────────────────────────────────────── */
    QToolTip {{
        background-color: #1A1916;
        color: #E2DAC8;
        border: 1px solid rgba(203, 163, 68, 0.40);
        padding: 6px 10px;
        border-radius: 6px;
        font-size: 12px;
        font-family: {fonts};
    }}

    /* ── Subtle text link ─────────────────────────────────────────────── */
    QPushButton#subtleLink {{
        color: {GOLD};
        font-size: 12px;
        font-family: {fonts};
        border: none;
        background: transparent;
        padding: 2px 4px;
    }}
    QPushButton#subtleLink:hover {{
        color: {GOLD_LIGHT};
        text-decoration: underline;
    }}

    /* ── Overlay host ─────────────────────────────────────────────────── */
    QWidget#overlayHost {{
        background-color: rgba(0,0,0,0.58);
    }}

    /* ── Auth modal ───────────────────────────────────────────────────── */
    QFrame#authModalCard {{
        background-color: {MODAL_BG};
        border-radius: 14px;
        border: 1.5px solid {GOLD};
    }}
    QLabel#authBrand {{
        color: {GOLD};
        font-size: 34px;
        font-weight: 700;
        font-family: {fonts};
        letter-spacing: 3px;
    }}
    QLineEdit#authField {{
        background-color: {MODAL_INPUT};
        border: 1.5px solid {MODAL_BORDER};
        border-radius: 8px;
        padding: 9px 14px;
        font-size: 13px;
        color: #222222;
        font-family: {fonts};
        font-weight: 500;
    }}
    QLineEdit#authField:focus {{
        border: 1.5px solid {GOLD};
    }}
    QPushButton#authLink {{
        color: {GOLD};
        font-family: {fonts};
        font-weight: 600;
        font-size: 13px;
        letter-spacing: 0.5px;
        border: none;
        background: transparent;
        padding: 4px 2px;
    }}
    QPushButton#authLink:hover {{
        color: {GOLD_LIGHT};
    }}
    QPushButton#loginBtn {{
        background-color: {MODAL_BTN};
        color: {MODAL_BTN_TEXT};
        border: none;
        border-radius: 8px;
        padding: 11px;
        font-size: 14px;
        font-weight: 700;
        letter-spacing: 1.5px;
        font-family: {fonts};
    }}
    QPushButton#loginBtn:hover {{
        background-color: {MODAL_BTN_HOVER};
        color: {GOLD_LIGHT};
    }}
    QPushButton#loginBtn:pressed {{
        background-color: #252525;
    }}
    QPushButton#modalCloseBtn {{
        color: #666666;
        font-size: 18px;
        font-weight: bold;
        border: none;
        background: transparent;
        padding: 4px;
    }}
    QPushButton#modalCloseBtn:hover {{
        color: #111111;
    }}
    QPushButton#offlineLink {{
        color: #888888;
        font-size: 12px;
        font-family: {fonts};
        border: none;
        background: transparent;
    }}
    QPushButton#offlineLink:hover {{
        color: #444444;
        text-decoration: underline;
    }}

    /* ── Legacy parchment buttons (kept for back-compat if used elsewhere) */
    QPushButton#parchmentSync {{
        background-color: {PARCHMENT};
        color: {DARK_TEXT};
        border-radius: 10px;
        padding: 9px 12px;
        font-size: 14px;
        font-family: {fonts};
        font-weight: 700;
        letter-spacing: 0.5px;
        min-width: 120px;
    }}
    QPushButton#parchmentSync:hover {{
        background-color: {PARCHMENT_HOVER};
    }}
    QPushButton#parchmentLaunch {{
        background-color: {PARCHMENT};
        color: {DARK_TEXT};
        border-radius: 10px;
        padding: 13px 24px;
        font-size: 15px;
        font-family: {fonts};
        font-weight: 700;
        letter-spacing: 0.5px;
        min-width: 140px;
    }}
    QPushButton#parchmentLaunch:hover {{
        background-color: {PARCHMENT_HOVER};
    }}
    QPushButton#parchmentLaunch:disabled {{
        background-color: #7D705C;
        color: #4A4234;
    }}
    """
