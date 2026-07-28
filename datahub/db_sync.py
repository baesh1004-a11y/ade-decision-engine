from __future__ import annotations

import html
import http.cookiejar
import os
import re
import sqlite3
import urllib.parse
import urllib.request
from pathlib import Path

from datahub.bootstrap import ensure_market_databases


DATABASES = (
    ("MARKET_DB_URL", Path("datahub/market.db")),
    ("US_MARKET_DB_URL", Path("datahub/us_market.db")),
)


_GOOGLE_DRIVE_HOSTS = {"drive.google.com", "docs.google.com", "drive.usercontent.google.com"}
_GOOGLE_DRIVE_FORM_ACTION_RE = re.compile(
    r'<form[^>]+action="([^"]*drive\.usercontent\.google\.com/download[^"]*)"',
    re.IGNORECASE,
)
_GOOGLE_DRIVE_INPUT_RE = re.compile(
    r'<input[^>]+name="([^"]+)"[^>]+value="([^"]*)"',
    re.IGNORECASE,
)
_GOOGLE_DRIVE_CONFIRM_RE = re.compile(r"confirm=([0-9A-Za-z_-]+)")
_DOWNLOAD_CHUNK_SIZE = 1024 * 1024
_PROGRESS_STEP_BYTES = 25 * 1024 * 1024
_FULL_CHECK_ENV = "DB_SYNC_FULL_CHECK"
_DIAGNOSTIC_PREFIX_BYTES = 64


def _log(message: str) -> None:
    print(f"[db-sync] {message}", flush=True)


def _is_google_drive_url(url: str) -> bool:
    return urllib.parse.urlparse(url).hostname in _GOOGLE_DRIVE_HOSTS


def _looks_like_html(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    with path.open("rb") as handle:
        prefix = handle.read(512).lstrip().lower()
    return prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html")


def _extract_google_drive_confirmation_url(page: bytes, base_url: str) -> str | None:
    text = page.decode("utf-8", errors="replace")
    action_match = _GOOGLE_DRIVE_FORM_ACTION_RE.search(text)
    if action_match:
        action = html.unescape(action_match.group(1))
        params = {
            html.unescape(name): html.unescape(value)
            for name, value in _GOOGLE_DRIVE_INPUT_RE.findall(text)
        }
        separator = "&" if "?" in action else "?"
        if params:
            return urllib.parse.urljoin(base_url, action) + separator + urllib.parse.urlencode(params)
        return urllib.parse.urljoin(base_url, action)

    parsed = urllib.parse.urlparse(base_url)
    query = urllib.parse.parse_qs(parsed.query)
    file_id = query.get("id", [None])[0]
    confirm_match = _GOOGLE_DRIVE_CONFIRM_RE.search(text)
    if file_id and confirm_match:
        return "https://drive.usercontent.google.com/download?" + urllib.parse.urlencode(
            {"id": file_id, "export": "download", "confirm": confirm_match.group(1)}
        )
    return None


def _stream_response(response, destination: Path) -> int:
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
    _log(f"Download complete ({downloaded_bytes / (1024 * 1024):,.1f} MiB)")
    return downloaded_bytes


def _log_download_diagnostics(path: Path, content_type: str, final_url: str) -> None:
    if not path.exists():
        _log("Diagnostic: downloaded file is missing")
        return

    with path.open("rb") as handle:
        prefix = handle.read(_DIAGNOSTIC_PREFIX_BYTES)

    printable = prefix.decode("utf-8", errors="replace").replace("\r", "\\r").replace("\n", "\\n")
    _log(f"Diagnostic content-type: {content_type}")
    _log(f"Diagnostic final URL: {final_url}")
    _log(f"Diagnostic first {_DIAGNOSTIC_PREFIX_BYTES} bytes (hex): {prefix.hex()}")
    _log(f"Diagnostic first {_DIAGNOSTIC_PREFIX_BYTES} bytes (text): {printable!r}")


def _download(url: str, destination: Path) -> None:
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ADE-Decision-Engine/1.0",
        "Accept": "*/*",
    }

    def fetch(target_url: str) -> tuple[str, str]:
        request = urllib.request.Request(target_url, headers=headers)
        with opener.open(request, timeout=1800) as response:
            content_type = response.headers.get_content_type()
            final_url = response.geturl()
            _stream_response(response, destination)
        return content_type, final_url

    content_type, final_url = fetch(url)
    if not _is_google_drive_url(url):
        _log_download_diagnostics(destination, content_type, final_url)
        if content_type == "text/html" or _looks_like_html(destination):
            raise RuntimeError("Download returned HTML instead of a SQLite database")
        return

    if content_type != "text/html" and not _looks_like_html(destination):
        _log_download_diagnostics(destination, content_type, final_url)
        return

    confirmation_url = _extract_google_drive_confirmation_url(destination.read_bytes(), final_url)
    if not confirmation_url:
        _log_download_diagnostics(destination, content_type, final_url)
        raise RuntimeError(
            "Google Drive returned an HTML page instead of the file. "
            "Verify that link sharing is set to anyone with the link."
        )

    _log("Google Drive confirmation page detected; continuing download")
    destination.unlink(missing_ok=True)
    content_type, final_url = fetch(confirmation_url)
    _log_download_diagnostics(destination, content_type, final_url)
    if content_type == "text/html" or _looks_like_html(destination):
        preview = destination.read_text("utf-8", errors="replace")[:300].replace("\n", " ")
        raise RuntimeError(
            "Google Drive confirmation download still returned HTML. "
            f"Final URL: {final_url}. Response preview: {preview!r}"
        )


def _validate_sqlite(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"Downloaded database is empty: {path}")

    with path.open("rb") as handle:
        header = handle.read(16)
    if header != b"SQLite format 3\x00":
        raise RuntimeError(
            "Downloaded file does not have a valid SQLite header: "
            f"{path}; actual header hex={header.hex()}"
        )

    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        if os.getenv(_FULL_CHECK_ENV, "").strip().lower() in {"1", "true", "yes", "on"}:
            _log(f"Running full SQLite quick_check for {path.name}")
            result = connection.execute("PRAGMA quick_check").fetchone()
            if not result or str(result[0]).lower() != "ok":
                raise RuntimeError(f"SQLite quick_check failed: {result}")
            _log(f"Full SQLite quick_check passed for {path.name}")
    finally:
        connection.close()


def sync_database(url_env: str, destination: Path) -> bool:
    url = os.getenv(url_env, "").strip()
    if not url:
        _log(f"{url_env} is not set; keeping existing {destination}")
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    candidate = destination.with_name(destination.name + ".candidate")
    candidate.unlink(missing_ok=True)

    try:
        _log(f"Downloading original SQLite file for {destination.name} from {url_env}")
        _download(url, candidate)
        _log(f"Validating SQLite header and schema for {destination.name}")
        _validate_sqlite(candidate)

        size_mb = candidate.stat().st_size / (1024 * 1024)
        os.replace(candidate, destination)
        _log(f"Installed {destination} ({size_mb:,.1f} MiB, validation=ok)")
        return True
    finally:
        candidate.unlink(missing_ok=True)


def sync_market_databases() -> None:
    failures: list[str] = []
    for url_env, destination in DATABASES:
        try:
            sync_database(url_env, destination)
        except Exception as exc:
            failures.append(f"{destination}: {exc}")
            _log(f"ERROR {destination}: {exc}")

    ensure_market_databases()

    if failures:
        raise RuntimeError("Database synchronization failed: " + " | ".join(failures))


if __name__ == "__main__":
    sync_market_databases()
