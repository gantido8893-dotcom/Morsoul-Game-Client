"""HTTP bridge for Tauri / Electron / React frontend communication."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from typing import Any

from aiohttp import web

from morsoul_launcher.appstate import AppState
from morsoul_launcher.controller import LauncherController

log = logging.getLogger("morsoul.launcher.http_bridge")


class HTTPBridge:
    """Exposes LauncherController via HTTP and WebSockets for desktop/web frontends."""

    def __init__(self, controller: LauncherController, port: int = 8081) -> None:
        self.controller = controller
        self.port = port
        self.app = web.Application()
        self._websockets: set[web.WebSocketResponse] = set()
        self.controller.on_state(self._on_state_changed)
        self._setup_routes()

    def _state_dict(self) -> dict[str, Any]:
        """Convert current AppState dataclass into a JSON-compatible dict."""
        return asdict(self.controller.state)

    def _on_state_changed(self, _state: AppState) -> None:
        """Broadcast state updates to all active WebSocket clients."""
        if not self._websockets:
            return
        payload = json.dumps({"type": "state", "state": self._state_dict()})
        for ws in list(self._websockets):
            if not ws.closed:
                try:
                    asyncio.create_task(ws.send_str(payload))
                except RuntimeError:
                    pass

    @staticmethod
    async def _get_json(request: web.Request) -> dict[str, Any]:
        """Safely parse JSON request body, returning empty dict if missing or invalid."""
        try:
            return await request.json()
        except Exception:
            return {}

    def _setup_routes(self) -> None:
        # System / State / Realtime
        self.app.router.add_get("/health", self.health)
        self.app.router.add_get("/state", self.get_state)
        self.app.router.add_get("/ws", self.ws_handler)

        # Auth
        self.app.router.add_post("/auth/login", self.login)
        self.app.router.add_post("/auth/register", self.register)
        self.app.router.add_post("/auth/logout", self.logout)
        self.app.router.add_post("/auth/logout-all", self.logout_all)
        self.app.router.add_post("/auth/logout_all", self.logout_all)
        self.app.router.add_post("/auth/offline", self.play_offline)
        self.app.router.add_post("/auth/change-password", self.change_password)
        self.app.router.add_post("/auth/change_password", self.change_password)
        self.app.router.add_post("/auth/delete-account", self.delete_account)
        self.app.router.add_post("/auth/delete_account", self.delete_account)

        # Game
        self.app.router.add_post("/game/launch", self.launch_game)
        self.app.router.add_get("/game/status", self.game_status)

        # Sync & Profiles
        self.app.router.add_post("/sync/start", self.start_sync)
        self.app.router.add_post("/sync/all", self.start_sync)
        self.app.router.add_post("/sync/profile", self.sync_profile)
        self.app.router.add_post("/sync/profile/{profile_id}", self.sync_profile)
        self.app.router.add_post("/sync/resolve", self.resolve_conflict)
        self.app.router.add_post("/sync/download", self.download_profile)
        self.app.router.add_post("/sync/download/{profile_id}", self.download_profile)
        self.app.router.add_post("/sync/delete-cloud", self.delete_cloud_profile)
        self.app.router.add_post("/sync/delete_cloud", self.delete_cloud_profile)
        self.app.router.add_delete("/sync/cloud/{profile_id}", self.delete_cloud_profile)
        self.app.router.add_get("/profiles", self.refresh_profiles)
        self.app.router.add_post("/profiles/refresh", self.refresh_profiles)
        self.app.router.add_get("/profiles/{profile_id}/history", self.profile_history)
        self.app.router.add_post("/profiles/history", self.profile_history)

        # Updates
        self.app.router.add_post("/updates/check", self.check_updates)
        self.app.router.add_get("/updates/check", self.check_updates)
        self.app.router.add_post("/updates/apply", self.apply_update)
        self.app.router.add_post("/updates/cancel", self.cancel_update)

        # Lifecycle
        self.app.router.add_post("/lifecycle/open", self.on_open)
        self.app.router.add_post("/lifecycle/close", self.on_close)

        # CORS for development
        self.app.middlewares.append(self._cors_middleware)

    @web.middleware
    async def _cors_middleware(self, request: web.Request, handler: Any) -> web.StreamResponse:
        """Add CORS headers for frontend development."""
        if request.method == "OPTIONS":
            return web.Response(
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                }
            )

        response = await handler(request)
        if isinstance(response, web.Response):
            response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    async def ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        """WebSocket endpoint for real-time state broadcasts."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._websockets.add(ws)
        try:
            await ws.send_str(json.dumps({"type": "state", "state": self._state_dict()}))
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    if msg.data == "ping":
                        await ws.send_str("pong")
                    elif msg.data == "state":
                        await ws.send_str(json.dumps({"type": "state", "state": self._state_dict()}))
                elif msg.type == web.WSMsgType.ERROR:
                    log.error("ws connection closed with exception %s", ws.exception())
        finally:
            self._websockets.discard(ws)
        return ws

    async def health(self, _request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({"status": "ok"})

    async def get_state(self, _request: web.Request) -> web.Response:
        """Get current application state."""
        return web.json_response(self._state_dict())

    async def login(self, request: web.Request) -> web.Response:
        """Handle login request."""
        data = await self._get_json(request)
        username = data.get("username", "")
        password = data.get("password", "")

        try:
            res = await self.controller.sign_in(username, password)
            if not res.ok:
                return web.json_response(
                    {"success": False, "error": res.message, "code": res.code, "state": self._state_dict()},
                    status=400,
                )
            return web.json_response({"success": True, "state": self._state_dict()})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def register(self, request: web.Request) -> web.Response:
        """Handle registration request."""
        data = await self._get_json(request)
        username = data.get("username", "")
        password = data.get("password", "")
        email = data.get("email")

        try:
            res = await self.controller.register(username, password, email)
            if not res.ok:
                return web.json_response(
                    {"success": False, "error": res.message, "code": res.code, "state": self._state_dict()},
                    status=400,
                )
            return web.json_response({"success": True, "state": self._state_dict()})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def logout(self, _request: web.Request) -> web.Response:
        """Handle logout request."""
        try:
            await self.controller.sign_out()
            return web.json_response({"success": True, "state": self._state_dict()})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def logout_all(self, _request: web.Request) -> web.Response:
        """Handle logout from all active sessions."""
        try:
            await self.controller.sign_out_all()
            return web.json_response({"success": True, "state": self._state_dict()})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def play_offline(self, _request: web.Request) -> web.Response:
        """Set offline mode."""
        try:
            await self.controller.continue_offline()
            return web.json_response({"success": True, "state": self._state_dict()})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def change_password(self, request: web.Request) -> web.Response:
        """Change account password."""
        data = await self._get_json(request)
        current_pw = data.get("current") or data.get("current_password") or ""
        new_pw = data.get("new") or data.get("new_password") or ""
        try:
            res = await self.controller.change_password(current_pw, new_pw)
            if not res.ok:
                return web.json_response(
                    {"success": False, "error": res.message, "code": res.code, "state": self._state_dict()},
                    status=400,
                )
            return web.json_response({"success": True, "message": res.message, "state": self._state_dict()})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def delete_account(self, request: web.Request) -> web.Response:
        """Delete account."""
        data = await self._get_json(request)
        password = data.get("password", "")
        try:
            res = await self.controller.delete_account(password)
            if not res.ok:
                return web.json_response(
                    {"success": False, "error": res.message, "code": res.code, "state": self._state_dict()},
                    status=400,
                )
            return web.json_response({"success": True, "state": self._state_dict()})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def launch_game(self, _request: web.Request) -> web.Response:
        """Launch the game."""
        try:
            res = self.controller.launch_game()
            if not res.ok:
                return web.json_response(
                    {"success": False, "error": res.message, "code": res.code, "state": self._state_dict()},
                    status=400,
                )
            return web.json_response({"success": True, "message": res.message, "state": self._state_dict()})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def game_status(self, _request: web.Request) -> web.Response:
        """Check if game process is currently running."""
        try:
            running = self.controller.is_game_running()
            return web.json_response({"running": running, "state": self._state_dict()})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def start_sync(self, _request: web.Request) -> web.Response:
        """Start profile synchronization across all profiles."""
        try:
            outcomes = await self.controller.sync_all()
            return web.json_response(
                {
                    "success": True,
                    "outcomes": [asdict(o) for o in outcomes],
                    "state": self._state_dict(),
                }
            )
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def sync_profile(self, request: web.Request) -> web.Response:
        """Sync a single profile."""
        data = await self._get_json(request)
        pid = request.match_info.get("profile_id") or data.get("profile_id") or ""
        if not pid:
            return web.json_response({"success": False, "error": "profile_id is required"}, status=400)
        try:
            outcome = await self.controller.sync_profile(pid)
            return web.json_response(
                {
                    "success": True,
                    "outcome": asdict(outcome),
                    "state": self._state_dict(),
                }
            )
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def resolve_conflict(self, request: web.Request) -> web.Response:
        """Resolve a sync conflict by choosing 'keep_local' or 'keep_cloud'."""
        data = await self._get_json(request)
        pid = data.get("profile_id", "")
        choice = data.get("choice", "")
        if choice not in {"keep_local", "keep_cloud"}:
            return web.json_response(
                {"success": False, "error": "choice must be 'keep_local' or 'keep_cloud'"},
                status=400,
            )
        try:
            outcome = await self.controller.resolve_conflict(pid, choice)
            return web.json_response(
                {
                    "success": True,
                    "outcome": asdict(outcome),
                    "state": self._state_dict(),
                }
            )
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def download_profile(self, request: web.Request) -> web.Response:
        """Download cloud profile save to local disk."""
        data = await self._get_json(request)
        pid = request.match_info.get("profile_id") or data.get("profile_id") or ""
        if not pid:
            return web.json_response({"success": False, "error": "profile_id is required"}, status=400)
        try:
            outcome = await self.controller.download_profile(pid)
            return web.json_response(
                {
                    "success": True,
                    "outcome": asdict(outcome),
                    "state": self._state_dict(),
                }
            )
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def delete_cloud_profile(self, request: web.Request) -> web.Response:
        """Delete cloud profile save."""
        data = await self._get_json(request)
        pid = request.match_info.get("profile_id") or data.get("profile_id") or ""
        if not pid:
            return web.json_response({"success": False, "error": "profile_id is required"}, status=400)
        try:
            res = await self.controller.delete_cloud_profile(pid)
            return web.json_response(
                {
                    "success": res.ok,
                    "message": res.message,
                    "state": self._state_dict(),
                }
            )
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def refresh_profiles(self, _request: web.Request) -> web.Response:
        """Refresh local and cloud profile views."""
        try:
            await self.controller.refresh_profiles()
            return web.json_response(
                {
                    "success": True,
                    "profiles": [asdict(p) for p in self.controller.state.profiles],
                    "state": self._state_dict(),
                }
            )
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def profile_history(self, request: web.Request) -> web.Response:
        """Load history snapshots for a profile."""
        data = await self._get_json(request)
        pid = request.match_info.get("profile_id") or data.get("profile_id") or ""
        if not pid:
            return web.json_response({"success": False, "error": "profile_id is required"}, status=400)
        try:
            history = await self.controller.load_history(pid)
            return web.json_response({"success": True, "history": history})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def check_updates(self, _request: web.Request) -> web.Response:
        """Check for game updates."""
        try:
            info = await self.controller.check_updates()
            return web.json_response(
                {
                    "success": True,
                    "available": getattr(info, "available", False) if info else False,
                    "state": self._state_dict(),
                }
            )
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def apply_update(self, _request: web.Request) -> web.Response:
        """Download and apply available update."""
        try:
            res = await self.controller.apply_update()
            if not res.ok:
                return web.json_response(
                    {"success": False, "error": res.message, "state": self._state_dict()},
                    status=400,
                )
            return web.json_response({"success": True, "state": self._state_dict()})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def cancel_update(self, _request: web.Request) -> web.Response:
        """Cancel ongoing update."""
        try:
            self.controller.cancel_update()
            return web.json_response({"success": True, "state": self._state_dict()})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def on_open(self, _request: web.Request) -> web.Response:
        """Notify controller that launcher has opened."""
        try:
            await self.controller.on_launcher_open()
            return web.json_response({"success": True, "state": self._state_dict()})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def on_close(self, _request: web.Request) -> web.Response:
        """Notify controller that launcher is closing."""
        try:
            await self.controller.on_launcher_close()
            return web.json_response({"success": True, "state": self._state_dict()})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def start(self) -> None:
        """Start the HTTP server asynchronously."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", self.port)
        await site.start()
        log.info("HTTP bridge running on http://localhost:%d", self.port)

    def run(self) -> None:
        """Run the HTTP server (blocking)."""
        web.run_app(self.app, host="localhost", port=self.port)
