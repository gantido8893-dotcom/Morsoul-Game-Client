"""Watch game.lock and trigger sync after the game closes."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from morsoul_core.paths import game_lock_path

log = logging.getLogger("morsoul.launcher.autosync")

SyncCallback = Callable[[], Coroutine[Any, Any, None]]


class _LockHandler(FileSystemEventHandler):
    def __init__(self, lock_path: Path, on_lock_removed: Callable[[], None]) -> None:
        super().__init__()
        self.lock_path = lock_path.resolve()
        self.on_lock_removed = on_lock_removed

    def on_deleted(self, event: FileSystemEvent) -> None:
        if Path(str(event.src_path)).resolve() == self.lock_path:
            self.on_lock_removed()


class GameLockWatcher:
    """Debounced watcher: when game.lock is removed, call the async sync callback."""

    def __init__(
        self,
        *,
        lock_path: Path | None = None,
        on_game_closed: SyncCallback,
        loop: asyncio.AbstractEventLoop,
        debounce_seconds: float = 5.0,
    ) -> None:
        self.lock_path = (lock_path or game_lock_path()).resolve()
        self.on_game_closed = on_game_closed
        self.loop = loop
        self.debounce_seconds = debounce_seconds
        self._observer: BaseObserver | None = None
        self._debounce_handle: asyncio.TimerHandle | None = None

    def _arm_debounce(self) -> None:
        if self._debounce_handle is not None:
            self._debounce_handle.cancel()
        self._debounce_handle = self.loop.call_later(
            self.debounce_seconds,
            lambda: asyncio.create_task(self.on_game_closed()),
        )

    def _on_closed_from_thread(self) -> None:
        self.loop.call_soon_threadsafe(self._arm_debounce)

    def start(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        handler = _LockHandler(self.lock_path, self._on_closed_from_thread)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.lock_path.parent), recursive=False)
        self._observer.start()
        log.info("watching %s", self.lock_path)

    def stop(self) -> None:
        if self._debounce_handle is not None:
            self._debounce_handle.cancel()
            self._debounce_handle = None
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None
