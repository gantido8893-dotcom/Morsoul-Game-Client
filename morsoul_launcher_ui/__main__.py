"""Launch the Morsoul desktop client UI."""

from __future__ import annotations


def main() -> None:
    from morsoul_launcher_ui.app import assets_ready, run

    assets_ready()
    raise SystemExit(run())


if __name__ == "__main__":
    main()
