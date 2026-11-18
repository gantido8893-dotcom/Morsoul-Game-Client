"""Async HTTP client for the Morsoul cloud API."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger("morsoul.launcher.api")

UrlProvider = Callable[[], str]
TokenProvider = Callable[[], str | None]
ConfigRefresher = Callable[[], Awaitable[str | None]]


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: Any = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        self.retry_after = retry_after


class ConflictError(ApiError):
    def __init__(self, status: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(status, code, message, details)
        d = details or {}
        self.server_revision = int(d.get("serverRevision", 0))
        self.state_hash = str(d.get("stateHash", ""))
        self.summary = d.get("summary")


class AuthError(ApiError):
    pass


class RateLimitedError(ApiError):
    pass


class NetworkError(ApiError):
    def __init__(self, message: str = "Can't reach the server") -> None:
        super().__init__(0, "NETWORK", message)


class AuthSession(BaseModel):
    model_config = ConfigDict(extra="ignore")
    userID: str
    username: str
    sessionToken: str
    expiresAt: Any


class MeResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    userID: str
    username: str
    role: str
    email: str | None = None
    createdAt: str | None = None
    passwordChangedAt: str | None = None


class SaveSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")
    currentCaseID: str | None = None
    casesCompleted: int = 0
    runicLogs: int = 0
    reputation: int = 0
    ending: str | None = None
    playtime: int = 0


class SaveListItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    profileID: str
    displayName: str
    revision: int
    stateHash: str
    summary: SaveSummary | dict = Field(default_factory=dict)
    updatedAt: Any = None


class PutSaveResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    revision: int
    summary: SaveSummary | dict = Field(default_factory=dict)


class ApiClient:
    def __init__(
        self,
        *,
        base_url: UrlProvider | str,
        token: TokenProvider | str | None = None,
        launcher_key: str | None = None,
        refresh_server_config: ConfigRefresher | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = (lambda: base_url) if isinstance(base_url, str) else base_url
        if callable(token) or token is None:
            self._token: TokenProvider = token or (lambda: None)
        else:
            tok_val = token
            self._token = lambda: tok_val
        self._launcher_key = launcher_key
        self._refresh_server_config = refresh_server_config
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(15.0, connect=5.0),
            follow_redirects=True,
        )
        self._config_refreshed = False

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> ApiClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    def _headers(self, *, auth: bool) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if auth:
            tok = self._token()
            if tok:
                headers["Authorization"] = f"Bearer {tok}"
        if self._launcher_key:
            headers["X-Launcher-Key"] = self._launcher_key
        return headers

    def _raise_for_error(self, resp: httpx.Response) -> None:
        if resp.status_code < 400:
            return
        retry_after = None
        if "Retry-After" in resp.headers:
            try:
                retry_after = int(resp.headers["Retry-After"])
            except ValueError:
                retry_after = None
        code, message, details = "HTTP_ERROR", "Request could not be completed.", None
        try:
            body = resp.json()
            err = body.get("error") or {}
            code = str(err.get("code") or code)
            message = str(err.get("message") or message)
            details = err.get("details")
        except Exception:
            pass
        if resp.status_code == 429 or code == "RATE_LIMITED":
            raise RateLimitedError(resp.status_code, code, message, details, retry_after)
        if resp.status_code == 401 or code == "INVALID_SESSION":
            raise AuthError(resp.status_code, code, message, details, retry_after)
        if resp.status_code == 409 and code == "REVISION_CONFLICT":
            raise ConflictError(resp.status_code, code, message, details)
        raise ApiError(resp.status_code, code, message, details, retry_after)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        json: Any = None,
        retry_get: bool = True,
    ) -> httpx.Response:
        attempts = 0
        refreshed = False
        while True:
            attempts += 1
            url = self._base_url().rstrip("/") + "/api/v1" + path
            try:
                log.info("HTTP %s %s", method, url)
                resp = await self._client.request(method, url, headers=self._headers(auth=auth), json=json)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                log.warning("HTTP %s %s failed: %s", method, url, exc)
                if not refreshed and self._refresh_server_config is not None:
                    refreshed = True
                    new_url = await self._refresh_server_config()
                    if new_url:
                        log.info("server config refreshed after network error")
                        continue
                raise NetworkError("Can't reach the server. You can still play") from exc

            if resp.status_code in {502, 503, 504} and method.upper() == "GET" and retry_get and attempts < 3:
                await asyncio.sleep(0.2 * attempts)
                continue
            if resp.status_code >= 400:
                # never retry PUT
                self._raise_for_error(resp)
            return resp

    async def register(self, username: str, password: str, email: str | None = None) -> AuthSession:
        body: dict[str, Any] = {"username": username, "password": password}
        if email:
            body["email"] = email
        resp = await self._request("POST", "/auth/register", auth=False, json=body, retry_get=False)
        return AuthSession.model_validate(resp.json())

    async def login(self, username: str, password: str) -> AuthSession:
        resp = await self._request(
            "POST",
            "/auth/login",
            auth=False,
            json={"username": username, "password": password},
            retry_get=False,
        )
        return AuthSession.model_validate(resp.json())

    async def logout(self) -> None:
        await self._request("POST", "/auth/logout", retry_get=False)

    async def logout_all(self) -> None:
        await self._request("POST", "/auth/logout-all", retry_get=False)

    async def me(self) -> MeResponse:
        resp = await self._request("GET", "/auth/me")
        return MeResponse.model_validate(resp.json())

    async def change_password(self, current: str, new: str) -> dict[str, Any]:
        resp = await self._request(
            "POST",
            "/auth/change-password",
            json={"currentPassword": current, "newPassword": new},
            retry_get=False,
        )
        return resp.json()

    async def delete_account(self, password: str) -> None:
        await self._request("DELETE", "/auth/account", json={"password": password}, retry_get=False)

    async def request_password_reset(self, email: str, method: str = "otp") -> dict[str, Any]:
        resp = await self._request(
            "POST",
            "/auth/forgot-password/request",
            auth=False,
            json={"email": email, "method": method},
            retry_get=False,
        )
        return resp.json()

    async def reset_password(self, email: str, code: str, new_password: str) -> dict[str, Any]:
        resp = await self._request(
            "POST",
            "/auth/forgot-password/reset",
            auth=False,
            json={"email": email, "code": code, "newPassword": new_password},
            retry_get=False,
        )
        return resp.json()

    async def list_saves(self) -> list[SaveListItem]:
        resp = await self._request("GET", "/saves")
        return [SaveListItem.model_validate(i) for i in resp.json()]

    async def get_latest(self, profile_id: str) -> dict[str, Any]:
        resp = await self._request("GET", f"/saves/{profile_id}/latest")
        return resp.json()

    async def put_save(self, profile_id: str, base_revision: int, snapshot: dict) -> PutSaveResult:
        # PUT is never retried automatically
        resp = await self._request(
            "PUT",
            f"/saves/{profile_id}",
            json={"baseRevision": base_revision, "snapshot": snapshot},
            retry_get=False,
        )
        return PutSaveResult.model_validate(resp.json())

    async def delete_save(self, profile_id: str) -> None:
        await self._request("DELETE", f"/saves/{profile_id}", retry_get=False)

    async def history(self, profile_id: str) -> list[dict[str, Any]]:
        resp = await self._request("GET", f"/saves/{profile_id}/history")
        return list(resp.json())

    async def history_revision(self, profile_id: str, revision: int) -> dict[str, Any]:
        resp = await self._request("GET", f"/saves/{profile_id}/history/{revision}")
        return resp.json()

    async def stats(self) -> dict[str, Any]:
        resp = await self._request("GET", "/stats")
        return resp.json()

    async def updates_manifest(self) -> dict[str, Any]:
        resp = await self._request("GET", "/updates/manifest", auth=False)
        return resp.json()

    async def health(self) -> dict[str, Any]:
        resp = await self._request("GET", "/health", auth=False)
        return resp.json()


async def fetch_server_url(config_url: str, *, client: httpx.AsyncClient | None = None) -> str | None:
    owns = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
    try:
        resp = await client.get(config_url)
        resp.raise_for_status()
        data = resp.json()
        url = data.get("serverURL")
        return str(url) if url else None
    except Exception:
        return None
    finally:
        if owns:
            await client.aclose()
