"""Qt ↔ asyncio bridge. UI calls controller methods through this adapter only."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Coroutine
from typing import Any

from PySide6.QtCore import QObject, Signal

from morsoul_launcher.appstate import AppState
from morsoul_launcher.controller import LauncherController


class ControllerBridge(QObject):
    state_changed = Signal(object)  # AppState
    call_finished = Signal(str, object)  # method name, result
    call_failed = Signal(str, str)  # method name, message

    def __init__(self, controller: LauncherController, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="launcher-asyncio", daemon=True)
        controller.on_state(self._on_state)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2)

    def _on_state(self, state: AppState) -> None:
        self.state_changed.emit(state)

    def submit(self, name: str, coro: Coroutine[Any, Any, Any]) -> None:
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)

        def _done(f: Any) -> None:
            try:
                result = f.result()
                self.call_finished.emit(name, result)
            except Exception as exc:
                self.call_failed.emit(name, str(exc))

        fut.add_done_callback(_done)

    def call(self, method: str, *args: Any, **kwargs: Any) -> None:
        fn: Callable[..., Any] = getattr(self.controller, method)
        result = fn(*args, **kwargs)
        if asyncio.iscoroutine(result):
            self.submit(method, result)
        else:
            self.call_finished.emit(method, result)

    def call_async(self, method: str, *args: Any, **kwargs: Any) -> None:
        fn = getattr(self.controller, method)
        self.submit(method, fn(*args, **kwargs))
