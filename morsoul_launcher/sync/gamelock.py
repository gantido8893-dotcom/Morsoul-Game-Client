"""Detect whether the game service holds game.lock."""

from __future__ import annotations

import json
import os
from pathlib import Path

from morsoul_core.paths import game_lock_path


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but not owned by us
    except OSError:
        # Windows: os.kill may raise OSError for dead processes
        if os.name == "nt":
            try:
                import ctypes

                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            except Exception:
                return False
        return False
    return True


def is_game_running(lock_path: Path | None = None) -> bool:
    path = lock_path or game_lock_path()
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        pid = int(data.get("pid", 0))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False
    return _pid_alive(pid)


def write_lock_for_tests(path: Path, pid: int | None = None) -> None:
    """Test helper: write a game.lock for the given (or current) PID."""
    path.write_text(
        json.dumps({"pid": pid if pid is not None else os.getpid(), "startedAt": 0}), encoding="utf-8"
    )
