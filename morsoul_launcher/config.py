"""Launcher settings from the environment."""

from __future__ import annotations

import base64
import sys
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LauncherSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    server_config_url: str | None = Field(None, validation_alias="SERVER_CONFIG_URL")
    default_server_url: str = Field("http://127.0.0.1:8080", validation_alias="DEFAULT_SERVER_URL")
    launcher_key: str | None = Field(None, validation_alias="LAUNCHER_KEY")
    save_hmac_key: str = Field(..., validation_alias="SAVE_HMAC_KEY")
    update_public_key: str | None = Field(None, validation_alias="UPDATE_PUBLIC_KEY")
    game_exe_path: Path | None = Field(None, validation_alias="GAME_EXE_PATH")
    game_install_dir: Path | None = Field(None, validation_alias="GAME_INSTALL_DIR")
    app_version: str = Field("0.1.0", validation_alias="APP_VERSION")
    content_dir: Path | None = Field(None, validation_alias="CONTENT_DIR")

    @field_validator("save_hmac_key")
    @classmethod
    def _hmac_ok(cls, v: str) -> str:
        try:
            raw = base64.b64decode(v, validate=True)
        except Exception as exc:
            raise ValueError("SAVE_HMAC_KEY must be base64") from exc
        if len(raw) < 16:
            raise ValueError("SAVE_HMAC_KEY must decode to at least 16 bytes")
        return v

    @field_validator("server_config_url", "launcher_key", "update_public_key", "content_dir", mode="before")
    @classmethod
    def _blank_none(cls, v):
        return None if isinstance(v, str) and not v.strip() else v

    @property
    def hmac_key_bytes(self) -> bytes:
        return base64.b64decode(self.save_hmac_key)


def load_settings(**over) -> LauncherSettings:
    if "_env_file" not in over:
        candidates = [
            Path.cwd() / ".env",
            Path(sys.executable).parent / ".env",
            Path(getattr(sys, "_MEIPASS", "")) / ".env" if hasattr(sys, "_MEIPASS") else None,
            Path(__file__).resolve().parents[1] / ".env",
        ]
        for candidate in candidates:
            if candidate and candidate.is_file():
                over["_env_file"] = str(candidate)
                break

    # If default_server_url not overridden and server.json is found, prefer server.json's serverURL
    if "default_server_url" not in over:
        server_candidates = [
            Path.cwd() / "server.json",
            Path(sys.executable).parent / "server.json",
            Path(getattr(sys, "_MEIPASS", "")) / "server.json" if hasattr(sys, "_MEIPASS") else None,
            Path(__file__).resolve().parents[1] / "server.json",
        ]
        for s_candidate in server_candidates:
            if s_candidate and s_candidate.is_file():
                try:
                    import json

                    data = json.loads(s_candidate.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and data.get("serverURL"):
                        over["default_server_url"] = str(data["serverURL"]).rstrip("/")
                        break
                except Exception:
                    pass

    try:
        return LauncherSettings(**over)  # type: ignore[call-arg]
    except Exception as exc:
        print(f"Launcher configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
