"""App data folder locations shared by the launcher and the game service."""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir

_APP_NAME = "Morsoul"


def data_dir() -> Path:
    """Return the per-user data directory.

    Override with MORSOUL_DATA_DIR for tests and isolated runs.
    """
    override = os.environ.get("MORSOUL_DATA_DIR")
    if override:
        path = Path(override)
    else:
        path = Path(user_data_dir(_APP_NAME, appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def game_db_path() -> Path:
    return data_dir() / "game.db"


def game_db_bak_path() -> Path:
    return data_dir() / "game.db.bak"


def game_lock_path() -> Path:
    return data_dir() / "game.lock"


def stats_cache_path() -> Path:
    return data_dir() / "stats-cache.json"


def launcher_dir() -> Path:
    path = data_dir() / "launcher"
    path.mkdir(parents=True, exist_ok=True)
    return path


def launcher_state_path() -> Path:
    return launcher_dir() / "launcher-state.json"
