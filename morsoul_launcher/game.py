"""Launch the Unity game executable and detect running state via game.lock."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from morsoul_launcher.sync.gamelock import is_game_running

log = logging.getLogger("morsoul.launcher.game")


@dataclass
class LaunchResult:
    ok: bool
    message: str = ""


def launch_game(
    exe_path: Path | None,
    *,
    user_id: str | None = None,
    db_path: Path | None = None,
    lock_path: Path | None = None,
) -> LaunchResult:
    if is_game_running(lock_path):
        return LaunchResult(False, "Game is already running")
    if exe_path is None or not Path(exe_path).exists():
        return LaunchResult(False, "Game executable was not found")
    try:
        cmd = [str(exe_path)]
        if user_id:
            cmd.extend(["--user-id", str(user_id)])
        if db_path:
            cmd.extend(["--db-path", str(db_path)])
        log.info("Launching game: %s", cmd)
        subprocess.Popen(  # noqa: S603 — path comes from config
            cmd,
            cwd=str(Path(exe_path).parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return LaunchResult(True)
    except OSError as exc:
        log.exception("launch failed")
        return LaunchResult(False, f"Could not start the game: {exc}")


def game_is_running(lock_path: Path | None = None) -> bool:
    return is_game_running(lock_path)
