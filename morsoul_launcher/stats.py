"""Fetch community stats and write stats-cache.json for the game."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from morsoul_core.paths import stats_cache_path
from morsoul_launcher.api import ApiClient, ApiError, NetworkError

log = logging.getLogger("morsoul.launcher.stats")


async def refresh_stats_cache(
    api: ApiClient,
    *,
    path: Path | None = None,
) -> bool:
    """GET /stats and write cache. Failures are silent and keep the old file."""
    path = path or stats_cache_path()
    try:
        body = await api.stats()
    except (ApiError, NetworkError, OSError):
        log.info("stats refresh skipped")
        return False
    except Exception:
        log.exception("stats refresh failed")
        return False
    payload: dict[str, Any] = dict(body)
    payload["updatedAt"] = int(time.time())
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return True
    except OSError:
        log.exception("could not write stats cache")
        return False
