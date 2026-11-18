"""UI entry: wire settings, controller, bridge, and main window."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from morsoul_launcher.config import load_settings
from morsoul_launcher.controller import LauncherController
from morsoul_launcher.tokens import KeyringTokenStore, MemoryTokenStore
from morsoul_launcher_ui.bridge import ControllerBridge
from morsoul_launcher_ui.main_window import MainWindow
from morsoul_launcher_ui.theme import load_application_fonts

log = logging.getLogger("morsoul.launcher.ui")


def run(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    argv = argv if argv is not None else sys.argv

    # Prefer .env next to the project; fall back to process env.
    settings = load_settings()
    tokens: MemoryTokenStore | KeyringTokenStore
    if "--memory-tokens" in argv:
        tokens = MemoryTokenStore()
    else:
        try:
            tokens = KeyringTokenStore()
        except Exception:
            log.warning("keyring unavailable; using in-memory tokens for this session")
            tokens = MemoryTokenStore()

    controller = LauncherController(settings, tokens=tokens)
    app = QApplication(argv)
    app.setApplicationName("Morsoul: World's Case")

    # Load any custom .ttf / .otf fonts from assets/fonts
    load_application_fonts()

    bridge = ControllerBridge(controller)
    bridge.start()
    window = MainWindow(bridge)
    window.show()
    window.show_auth_if_needed()
    bridge.call_async("on_launcher_open")

    code = app.exec()
    bridge.stop()
    return int(code)


def assets_ready() -> Path:
    from morsoul_launcher_ui.theme import ASSETS

    root = ASSETS
    try:
        (root / "bg").mkdir(parents=True, exist_ok=True)
        (root / "screenshots").mkdir(parents=True, exist_ok=True)
        (root / "fonts").mkdir(parents=True, exist_ok=True)

        readme_fonts = root / "fonts" / "README.txt"
        if not readme_fonts.exists():
            readme_fonts.write_text(
                "Drop any custom .ttf or .otf font files here (e.g. Cinzel, Celtic, etc.).\n"
                "They will be automatically registered and applied at launcher startup.\n",
                encoding="utf-8",
            )

        readme_shots = root / "screenshots" / "README.txt"
        if not readme_shots.exists():
            readme_shots.write_text(
                "Drop game screenshots here as 01.png … 06.png (or .jpg).\n",
                encoding="utf-8",
            )
    except OSError:
        pass

    return root
