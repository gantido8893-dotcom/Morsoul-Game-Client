"""Run the HTTP bridge for Tauri / Electron / React frontend development."""

from __future__ import annotations

import logging
import sys

from morsoul_launcher.config import load_settings
from morsoul_launcher.controller import LauncherController
from morsoul_launcher.http_bridge import HTTPBridge
from morsoul_launcher.tokens import KeyringTokenStore, MemoryTokenStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

log = logging.getLogger("morsoul.launcher")


def main() -> None:
    """Start the HTTP bridge server."""
    log.info("Starting Morsoul Launcher HTTP Bridge on port 8081...")

    settings = load_settings()
    tokens: MemoryTokenStore | KeyringTokenStore
    if "--memory-tokens" in sys.argv:
        tokens = MemoryTokenStore()
    else:
        try:
            tokens = KeyringTokenStore()
        except Exception:
            tokens = MemoryTokenStore()

    controller = LauncherController(settings, tokens=tokens)
    bridge = HTTPBridge(controller, port=8081)
    bridge.run()


if __name__ == "__main__":
    main()
