from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from datahub.bootstrap import ensure_market_databases


DATABASES = (
    Path("datahub/market.db"),
    Path("datahub/us_market.db"),
)

_ARCHIVE_URL_ENV = "DB_ARCHIVE_URL"
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
        raise RuntimeError(
            f"Incomplete download: expected {expected_bytes:,} bytes, received {downloaded_bytes:,} bytes"
        )

    if downloaded_bytes == 0:
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


def _safe_extract_archive(archive_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        destination_root = destination.resolve()
        for member in archive.infolist():
            member_path = (destination / member.filename).resolve()
            if member_path != destination_root and destination_root not in member_path.parents:
                raise RuntimeError(f"Unsafe ZIP member path: {member.filename}")
        archive.extractall(destination)


def _find_database(extracted_root: Path, filename: str) -> Path:
    matches = [path for path in extracted_root.rglob(filename) if path.is_file()]
    if not matches:
        raise RuntimeError(f"Archive does not contain required database: {filename}")
    if len(matches) > 1:
        raise RuntimeError(f"Archive contains multiple copies of required database: {filename}")
    return matches[0]


def sync_database_archive() -> None:
    archive_url = os.getenv(_ARCHIVE_URL_ENV, "").strip()
    if not archive_url:
        missing = [str(path) for path in DATABASES if not _existing_database_is_valid(path)]
        if missing:
            raise RuntimeError(
                f"{_ARCHIVE_URL_ENV} is not set and valid local databases are missing: " + ", ".join(missing)
            )
        _log(f"{_ARCHIVE_URL_ENV} is not set; using existing valid databases")
        return

    with tempfile.TemporaryDirectory(prefix="ade-db-sync-") as temp_dir:
        temp_root = Path(temp_dir)
        archive_path = temp_root / "databases.zip"
        extracted_root = temp_root / "extracted"
        extracted_root.mkdir(parents=True, exist_ok=True)

        _log(f"Downloading database archive from {_ARCHIVE_URL_ENV}")
        _download(archive_url, archive_path)
        if not zipfile.is_zipfile(archive_path):
            raise RuntimeError("Downloaded file is not a valid ZIP archive")

        _log("Extracting database archive")
        _safe_extract_archive(archive_path, extracted_root)

        candidates: dict[Path, Path] = {}
        for destination in DATABASES:
            source = _find_database(extracted_root, destination.name)
            _log(f"Validating {destination.name}")
            _validate_sqlite(source)
            candidates[destination] = source

        for destination, source in candidates.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            candidate = destination.with_name(destination.name + ".candidate")
            candidate.unlink(missing_ok=True)
            try:
                shutil.copyfile(source, candidate)
                _validate_sqlite(candidate)
                size_mb = candidate.stat().st_size / (1024 * 1024)
                os.replace(candidate, destination)
                _log(f"Installed {destination} ({size_mb:,.1f} MiB, validation=ok)")
            finally:
                candidate.unlink(missing_ok=True)


def sync_market_databases() -> None:
    try:
        sync_database_archive()
    except Exception as exc:
        _log(f"ERROR database archive synchronization failed: {exc}")
        invalid = [str(path) for path in DATABASES if not _existing_database_is_valid(path)]
        if invalid:
            raise RuntimeError(
                "Database synchronization failed and no valid fallback exists: " + ", ".join(invalid)
            ) from exc
        _log("Using existing valid databases after archive synchronization failure")

    ensure_market_databases()


if __name__ == "__main__":
    sync_market_databases()
