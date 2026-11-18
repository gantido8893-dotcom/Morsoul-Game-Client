"""Download and apply signed update manifests."""

from __future__ import annotations

import hashlib
import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from morsoul_core.manifest import verify_manifest

log = logging.getLogger("morsoul.launcher.updater")

ProgressCB = Callable[[str, int, int], None]  # path, downloaded, total


@dataclass
class UpdateFileInfo:
    path: str
    sha256: str
    size: int
    url: str
    changed: bool = True


@dataclass
class UpdateInfo:
    app_version: str
    content_version: int
    files: list[UpdateFileInfo] = field(default_factory=list)
    total_download_bytes: int = 0

    @property
    def available(self) -> bool:
        return any(f.changed for f in self.files)


class UpdateError(Exception):
    pass


class UpdateCancelled(UpdateError):
    pass


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def local_file_matches(install_dir: Path, rel: str, sha256: str, size: int) -> bool:
    path = install_dir / rel
    if not path.is_file():
        return False
    if path.stat().st_size != size:
        return False
    return _sha256_file(path) == sha256


async def check_updates(
    *,
    manifest: dict,
    signature: str,
    public_key_b64: str,
    install_dir: Path,
) -> UpdateInfo:
    if not verify_manifest(manifest, signature, public_key_b64):
        raise UpdateError("The update could not be verified. Your game was not changed")
    files: list[UpdateFileInfo] = []
    total = 0
    for f in manifest.get("files") or []:
        rel = f["path"]
        sha = f["sha256"]
        size = int(f["size"])
        url = f["url"]
        changed = not local_file_matches(install_dir, rel, sha, size)
        info = UpdateFileInfo(path=rel, sha256=sha, size=size, url=url, changed=changed)
        files.append(info)
        if changed:
            total += size
    return UpdateInfo(
        app_version=str(manifest.get("appVersion", "")),
        content_version=int(manifest.get("contentVersion", 0)),
        files=files,
        total_download_bytes=total,
    )


async def apply_update(
    info: UpdateInfo,
    *,
    install_dir: Path,
    staging_dir: Path,
    client: httpx.AsyncClient | None = None,
    progress: ProgressCB | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> None:
    """Download changed files, verify all, then replace. Roll back on any failure."""
    if not info.available:
        return
    install_dir.mkdir(parents=True, exist_ok=True)
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    owns = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))
    replaced: list[tuple[Path, Path]] = []  # (final, .old)
    try:
        changed = [f for f in info.files if f.changed]
        for f in changed:
            if cancelled and cancelled():
                raise UpdateCancelled("cancelled")
            dest = staging_dir / f.path
            dest.parent.mkdir(parents=True, exist_ok=True)
            downloaded = 0
            async with client.stream("GET", f.url) as resp:
                resp.raise_for_status()
                with dest.open("wb") as out:
                    async for chunk in resp.aiter_bytes():
                        if cancelled and cancelled():
                            raise UpdateCancelled("cancelled")
                        out.write(chunk)
                        downloaded += len(chunk)
                        if progress:
                            progress(f.path, downloaded, f.size)
            if dest.stat().st_size != f.size or _sha256_file(dest) != f.sha256:
                raise UpdateError("The update could not be verified. Your game was not changed")

        # all verified — replace
        for f in changed:
            final = install_dir / f.path
            staged = staging_dir / f.path
            final.parent.mkdir(parents=True, exist_ok=True)
            old = Path(str(final) + ".old")
            if final.exists():
                if old.exists():
                    old.unlink()
                final.replace(old)
                replaced.append((final, old))
            staged.replace(final)

        # success: remove .old and staging
        for _, old in replaced:
            if old.exists():
                old.unlink()
        shutil.rmtree(staging_dir, ignore_errors=True)
    except Exception:
        # roll back every .old
        for final, old in replaced:
            try:
                if final.exists():
                    final.unlink()
                if old.exists():
                    old.replace(final)
            except OSError:
                log.exception("rollback failed for %s", final)
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    finally:
        if owns:
            await client.aclose()
