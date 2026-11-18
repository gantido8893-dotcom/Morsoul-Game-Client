"""Entry point for building MorsoulLauncher.exe."""

from __future__ import annotations

import sys

from morsoul_launcher_ui.app import assets_ready, run


def main() -> None:
    assets_ready()
    sys.exit(run())


if __name__ == "__main__":
    main()
