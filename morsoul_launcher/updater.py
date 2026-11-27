"""Download and apply signed update manifests."""

from __future__ import annotations

import hashlib
import logging
import shutil
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from morsoul_core.manifest import verify_manifest

log = logging.getLogger("morsoul.launcher.updater")

ProgressCB = Callable[[str, int, int], None]  # path, downloaded, total
StatusCB = Callable[[str], None]


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
        if rel.lower().endswith(".zip"):
            marker = install_dir / f".{rel}.sha256"
            if marker.is_file():
                try:
                    return marker.read_text(encoding="utf-8").strip() == sha256
                except Exception:
                    pass
        return False
    if path.stat().st_size != size:
        return False
    return _sha256_file(path) == sha256


def _extract_zip_safely(
    zip_path: Path,
    dest_dir: Path,
    cancelled: Callable[[], bool] | None = None,
    progress: ProgressCB | None = None,
) -> list[Path]:
    """Extract a zip archive safely into dest_dir, preventing Zip Slip.
    If all files are enclosed in a single top-level folder, unwrap it.
    Returns list of extracted relative file paths.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    resolved_dest = dest_dir.resolve()
    extracted_rel_paths: list[Path] = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        infolist = zf.infolist()
        # Zip Slip check
        for info in infolist:
            target = (dest_dir / info.filename).resolve()
            if not str(target).startswith(str(resolved_dest)):
                raise UpdateError(f"Unsafe path in zip archive: {info.filename}")

        # Check for single root wrapper folder (e.g. Morsoul/Morsoul.exe)
        top_elements = {info.filename.split("/")[0] for info in infolist if info.filename.strip("/")}
        strip_prefix = ""
        if len(top_elements) == 1:
            candidate = list(top_elements)[0]
            if any(info.filename.startswith(candidate + "/") for info in infolist):
                strip_prefix = candidate + "/"

        total_members = len([m for m in infolist if not m.is_dir()])
        done_members = 0

        for info in infolist:
            if cancelled and cancelled():
                raise UpdateCancelled("cancelled")
            if info.is_dir():
                continue

            rel_name = info.filename
            if strip_prefix and rel_name.startswith(strip_prefix):
                rel_name = rel_name[len(strip_prefix):]
            if not rel_name:
                continue

            out_file = dest_dir / rel_name
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, out_file.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted_rel_paths.append(Path(rel_name))
            done_members += 1
            if progress and (done_members % 10 == 0 or done_members == total_members):
                progress(f"Extracting {rel_name}", done_members, total_members)

    return extracted_rel_paths


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
    status_cb: StatusCB | None = None,
) -> None:
    """Download changed files, verify all, then replace. Roll back on any failure."""
    if not info.available:
        return
    install_dir.mkdir(parents=True, exist_ok=True)

    # Opportunistic cleanup of leftover .old files from previous runs
    for old_file in install_dir.glob("*.old*"):
        try:
            old_file.unlink()
        except OSError:
            pass

    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    owns = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(None, connect=20.0, read=60.0), follow_redirects=True)
    replaced: list[tuple[Path, Path]] = []  # (final, .old)
    created_markers: list[Path] = []
    try:
        changed = [f for f in info.files if f.changed]
        for f in changed:
            if cancelled and cancelled():
                raise UpdateCancelled("cancelled")
            dest = staging_dir / f.path
            dest.parent.mkdir(parents=True, exist_ok=True)
            downloaded = 0
            chunk_accum = 0
            async with client.stream("GET", f.url) as resp:
                resp.raise_for_status()
                with dest.open("wb") as out:
                    async for chunk in resp.aiter_bytes():
                        if cancelled and cancelled():
                            raise UpdateCancelled("cancelled")
                        out.write(chunk)
                        downloaded += len(chunk)
                        chunk_accum += len(chunk)
                        # Throttle progress updates to every 512KB to avoid flooding Qt event loop
                        if progress and (chunk_accum >= 512 * 1024 or downloaded == f.size):
                            chunk_accum = 0
                            progress(f.path, downloaded, f.size)
            if dest.stat().st_size != f.size or _sha256_file(dest) != f.sha256:
                raise UpdateError("The update could not be verified. Your game was not changed")

        # all verified — unpack any archives and replace
        if status_cb:
            status_cb("applying")

        unpacked_files: dict[str, tuple[Path, list[Path]]] = {}
        for f in changed:
            if f.path.lower().endswith(".zip"):
                staged_zip = staging_dir / f.path
                unpacked_dir = staging_dir / f"_unpacked_{Path(f.path).stem}"
                extracted = _extract_zip_safely(staged_zip, unpacked_dir, cancelled=cancelled, progress=progress)
                unpacked_files[f.path] = (unpacked_dir, extracted)

        for f in changed:
            if f.path in unpacked_files:
                unpacked_dir, extracted_rel_paths = unpacked_files[f.path]
                for rel in extracted_rel_paths:
                    final = install_dir / rel
                    staged = unpacked_dir / rel
                    final.parent.mkdir(parents=True, exist_ok=True)
                    old = Path(str(final) + ".old")
                    if final.exists():
                        if old.exists():
                            try:
                                old.unlink()
                            except OSError:
                                old = final.with_name(f"{final.name}.old.{int(time.time())}")
                        final.replace(old)
                        replaced.append((final, old))
                    staged.replace(final)
                # Write marker so future checks know this zip was unpacked and verified
                marker = install_dir / f".{f.path}.sha256"
                marker.write_text(f.sha256, encoding="utf-8")
                created_markers.append(marker)
            else:
                final = install_dir / f.path
                staged = staging_dir / f.path
                final.parent.mkdir(parents=True, exist_ok=True)
                old = Path(str(final) + ".old")
                if final.exists():
                    if old.exists():
                        try:
                            old.unlink()
                        except OSError:
                            old = final.with_name(f"{final.name}.old.{int(time.time())}")
                    final.replace(old)
                    replaced.append((final, old))
                staged.replace(final)

        # success: remove .old and staging (ignore locked .old files like running launcher)
        for _, old in replaced:
            try:
                if old.exists():
                    old.unlink()
            except OSError:
                log.info("Could not remove %s immediately (file locked by active process); deferred", old)
        shutil.rmtree(staging_dir, ignore_errors=True)
    except Exception:
        # roll back every .old and remove created markers
        for marker in created_markers:
            try:
                if marker.exists():
                    marker.unlink()
            except OSError:
                pass
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
