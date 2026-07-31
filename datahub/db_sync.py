from __future__ import annotations

import os
import shutil
import sqlite3
import urllib.request
import zipfile
from pathlib import Path

from datahub.bootstrap import ensure_market_databases


DATABASE_ARCHIVES = (
    ("MARKET_DB_ARCHIVE_URL", Path("datahub/market.db"), Path("datahub/.market-db-archive.zip")),
    ("US_MARKET_DB_ARCHIVE_URL", Path("datahub/us_market.db"), Path("datahub/.us-market-db-archive.zip")),
)

_DOWNLOAD_CHUNK_SIZE = 1024 * 1024
_PROGRESS_STEP_BYTES = 25 * 1024 * 1024
_FULL_CHECK_ENV = "DB_SYNC_FULL_CHECK"
_SQLITE_HEADER = b"SQLite format 3\x00"


def _log(message: str) -> None:
    print(f"[db-sync] {message}", flush=True)


def _read_prefix(path: Path, size: int = 512) -> bytes:
    if not path.exists() or path.stat().st_size == 0:
        return b""
    with path.open("rb") as handle:
        return handle.read(size)


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ADE-Decision-Engine/1.0",
            "Accept": "application/zip,application/octet-stream,*/*",
        },
    )

    with urllib.request.urlopen(request, timeout=1800) as response:
        content_length = response.headers.get("Content-Length")
        expected_bytes = int(content_length) if content_length and content_length.isdigit() else None
        downloaded_bytes = 0
        next_progress = _PROGRESS_STEP_BYTES

        with destination.open("wb") as output:
            while True:
                chunk = response.read(_DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                output.write(chunk)
                downloaded_bytes += len(chunk)
                if downloaded_bytes >= next_progress:
                    if expected_bytes:
                        percent = downloaded_bytes * 100 / expected_bytes
                        _log(f"Downloaded {downloaded_bytes / (1024 * 1024):,.1f} MiB ({percent:.1f}%)")
                    else:
                        _log(f"Downloaded {downloaded_bytes / (1024 * 1024):,.1f} MiB")
                    next_progress += _PROGRESS_STEP_BYTES

    if expected_bytes is not None and downloaded_bytes != expected_bytes:
        destination.unlink(missing_ok=True)
        raise RuntimeError(
            f"Incomplete download: expected {expected_bytes:,} bytes, received {downloaded_bytes:,} bytes"
        )

    if downloaded_bytes == 0:
        destination.unlink(missing_ok=True)
        raise RuntimeError("Downloaded archive is empty")

    _log(f"Archive download complete ({downloaded_bytes / (1024 * 1024):,.1f} MiB)")


def _validate_sqlite(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"Database is empty: {path}")

    header = _read_prefix(path, len(_SQLITE_HEADER))
    if header != _SQLITE_HEADER:
        raise RuntimeError(
            "File is not a valid SQLite database: "
            f"{path}; actual header hex={header.hex()}"
        )

    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        if os.getenv(_FULL_CHECK_ENV, "").strip().lower() in {"1", "true", "yes", "on"}:
            _log(f"Running SQLite quick_check for {path.name}")
            result = connection.execute("PRAGMA quick_check").fetchone()
            if not result or str(result[0]).lower() != "ok":
                raise RuntimeError(f"SQLite quick_check failed: {result}")
            _log(f"SQLite quick_check passed for {path.name}")
    finally:
        connection.close()


def _existing_database_is_valid(path: Path) -> bool:
    try:
        _validate_sqlite(path)
    except Exception as exc:
        _log(f"Existing database is unavailable or invalid: {path}: {exc}")
        return False
    return True


def _find_archive_member(archive: zipfile.ZipFile, filename: str) -> zipfile.ZipInfo:
    matches = [
        member
        for member in archive.infolist()
        if not member.is_dir() and Path(member.filename).name == filename
    ]
    if not matches:
        raise RuntimeError(f"Archive does not contain required database: {filename}")
    if len(matches) > 1:
        raise RuntimeError(f"Archive contains multiple copies of required database: {filename}")
    return matches[0]


def _extract_database_member(
    archive: zipfile.ZipFile,
    member: zipfile.ZipInfo,
    destination: Path,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    candidate = destination.with_name(destination.name + ".candidate")
    candidate.unlink(missing_ok=True)

    try:
        _log(f"Extracting {destination.name}")
        with archive.open(member, "r") as source, candidate.open("wb") as output:
            shutil.copyfileobj(source, output, length=_DOWNLOAD_CHUNK_SIZE)

        _log(f"Validating {destination.name}")
        _validate_sqlite(candidate)
        size_mb = candidate.stat().st_size / (1024 * 1024)
        os.replace(candidate, destination)
        _log(f"Installed {destination} ({size_mb:,.1f} MiB, validation=ok)")
    finally:
        candidate.unlink(missing_ok=True)


def sync_database_archive(url_env: str, destination: Path, archive_path: Path) -> None:
    archive_url = os.getenv(url_env, "").strip()
    if not archive_url:
        if _existing_database_is_valid(destination):
            _log(f"{url_env} is not set; using existing valid {destination}")
            return
        raise RuntimeError(f"{url_env} is not set and valid local database is missing: {destination}")

    _log(f"Downloading {destination.name} archive from {url_env}")
    _download(archive_url, archive_path)

    try:
        if not zipfile.is_zipfile(archive_path):
            raise RuntimeError(f"Downloaded file for {destination.name} is not a valid ZIP archive")

        with zipfile.ZipFile(archive_path) as archive:
            member = _find_archive_member(archive, destination.name)
            _extract_database_member(archive, member, destination)
    finally:
        archive_path.unlink(missing_ok=True)


def sync_market_databases() -> None:
    fatal_failures: list[str] = []

    for url_env, destination, archive_path in DATABASE_ARCHIVES:
        try:
            sync_database_archive(url_env, destination, archive_path)
        except Exception as exc:
            _log(f"ERROR {destination.name} synchronization failed: {exc}")
            if _existing_database_is_valid(destination):
                _log(f"Using existing valid database after sync failure: {destination}")
                continue
            fatal_failures.append(f"{destination}: {exc}")

    ensure_market_databases()

    if fatal_failures:
        raise RuntimeError(
            "Database synchronization failed and no valid fallback exists: " + " | ".join(fatal_failures)
        )


if __name__ == "__main__":
    sync_market_databases()
