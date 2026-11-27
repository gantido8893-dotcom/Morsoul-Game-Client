"""Updater, stats and game launch tests (milestone M4)."""

from __future__ import annotations

import base64
from pathlib import Path

import httpx
import pytest

from morsoul_core.manifest import generate_keypair, sign_manifest
from morsoul_launcher import stats as stats_mod
from morsoul_launcher.api import ApiClient
from morsoul_launcher.game import launch_game
from morsoul_launcher.updater import UpdateCancelled, UpdateError, apply_update, check_updates


def _file_sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_sha_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


@pytest.mark.asyncio
async def test_check_bad_signature(tmp_path: Path) -> None:
    pem, pub = generate_keypair()
    manifest = {
        "appVersion": "1.0.0",
        "contentVersion": 1,
        "publishedAt": 1,
        "files": [{"path": "a.bin", "sha256": "0" * 64, "size": 1, "url": "http://x/a"}],
    }
    with pytest.raises(UpdateError):
        await check_updates(
            manifest=manifest,
            signature=base64.b64encode(b"bad").decode(),
            public_key_b64=pub,
            install_dir=tmp_path,
        )


@pytest.mark.asyncio
async def test_apply_hash_mismatch_rollback(tmp_path: Path) -> None:
    pem, pub = generate_keypair()
    install = tmp_path / "install"
    staging = tmp_path / "staging"
    install.mkdir()
    original = install / "game.exe"
    original.write_bytes(b"ORIGINAL")
    # serve a file with wrong content vs declared hash
    bad_bytes = b"TAMPERED"
    good_hash = "a" * 64

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=bad_bytes)

    manifest = {
        "appVersion": "1.1.0",
        "contentVersion": 1,
        "publishedAt": 1,
        "files": [
            {
                "path": "game.exe",
                "sha256": good_hash,
                "size": len(bad_bytes),
                "url": "http://cdn/game.exe",
            }
        ],
    }
    sig = sign_manifest(manifest, pem)
    info = await check_updates(manifest=manifest, signature=sig, public_key_b64=pub, install_dir=install)
    assert info.available
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(UpdateError):
            await apply_update(info, install_dir=install, staging_dir=staging, client=client)
    assert original.read_bytes() == b"ORIGINAL"


@pytest.mark.asyncio
async def test_apply_success_and_cancel(tmp_path: Path) -> None:
    pem, pub = generate_keypair()
    install = tmp_path / "install"
    staging = tmp_path / "staging"
    install.mkdir()
    payload = b"NEWVERSIONDATA"
    sha = __import__("hashlib").sha256(payload).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    manifest = {
        "appVersion": "2.0.0",
        "contentVersion": 2,
        "publishedAt": 2,
        "files": [{"path": "game.exe", "sha256": sha, "size": len(payload), "url": "http://cdn/game.exe"}],
    }
    sig = sign_manifest(manifest, pem)
    info = await check_updates(manifest=manifest, signature=sig, public_key_b64=pub, install_dir=install)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await apply_update(info, install_dir=install, staging_dir=staging, client=client)
    assert (install / "game.exe").read_bytes() == payload
    assert not list(install.glob("*.old"))

    # cancel mid-download
    cancelled = {"n": 0}

    def handler2(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    info2 = await check_updates(
        manifest={
            **manifest,
            "appVersion": "2.0.1",
            "files": [
                {"path": "game.exe", "sha256": "b" * 64, "size": len(payload), "url": "http://cdn/game.exe"}
            ],
        },
        signature=sign_manifest(
            {
                **manifest,
                "appVersion": "2.0.1",
                "files": [
                    {
                        "path": "game.exe",
                        "sha256": "b" * 64,
                        "size": len(payload),
                        "url": "http://cdn/game.exe",
                    }
                ],
            },
            pem,
        ),
        public_key_b64=pub,
        install_dir=install,
    )

    def cancel() -> bool:
        cancelled["n"] += 1
        return True

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler2)) as client:
        with pytest.raises(UpdateCancelled):
            await apply_update(
                info2, install_dir=install, staging_dir=tmp_path / "staging2", client=client, cancelled=cancel
            )
    assert (install / "game.exe").read_bytes() == payload


@pytest.mark.asyncio
async def test_stats_silent_failure(tmp_path: Path) -> None:
    path = tmp_path / "stats-cache.json"
    path.write_text('{"cases":[],"updatedAt":1}', encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"code": "INTERNAL", "message": "x"}})

    async with ApiClient(
        base_url="http://t", token=lambda: "t", transport=httpx.MockTransport(handler)
    ) as api:
        ok = await stats_mod.refresh_stats_cache(api, path=path)
    assert ok is False
    assert path.read_text(encoding="utf-8").startswith('{"cases"')


def test_launch_missing_exe(tmp_path: Path) -> None:
    r = launch_game(tmp_path / "missing.exe", lock_path=tmp_path / "game.lock")
    assert r.ok is False


@pytest.mark.asyncio
async def test_apply_zip_extraction_and_marker(tmp_path: Path) -> None:
    import io
    import zipfile

    pem, pub = generate_keypair()
    install = tmp_path / "install"
    staging = tmp_path / "staging"
    install.mkdir()

    # Create in-memory zip with wrapper directory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Morsoul/Morsoul.exe", b"EXEDATA")
        zf.writestr("Morsoul/sub/asset.dat", b"ASSETDATA")
    zip_bytes = buf.getvalue()
    zip_sha = _file_sha_bytes(zip_bytes)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=zip_bytes)

    manifest = {
        "appVersion": "1.1.3",
        "contentVersion": 1,
        "publishedAt": 100,
        "files": [{"path": "Morsoul.zip", "sha256": zip_sha, "size": len(zip_bytes), "url": "http://cdn/Morsoul.zip"}],
    }
    sig = sign_manifest(manifest, pem)

    # 1. First check: update should be available
    info = await check_updates(manifest=manifest, signature=sig, public_key_b64=pub, install_dir=install)
    assert info.available is True

    # 2. Apply update: should extract files and write marker
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await apply_update(info, install_dir=install, staging_dir=staging, client=client)

    assert (install / "Morsoul.exe").read_bytes() == b"EXEDATA"
    assert (install / "sub" / "asset.dat").read_bytes() == b"ASSETDATA"
    assert (install / ".Morsoul.zip.sha256").read_text(encoding="utf-8").strip() == zip_sha

    # 3. Subsequent check: should be recognized as up-to-date via marker
    info2 = await check_updates(manifest=manifest, signature=sig, public_key_b64=pub, install_dir=install)
    assert info2.available is False

