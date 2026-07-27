from __future__ import annotations

import html
import http.cookiejar
import os
import re
import shutil
import sqlite3
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from datahub.bootstrap import ensure_market_databases


DATABASES = (
    ("MARKET_DB_URL", Path("datahub/market.db")),
    ("US_MARKET_DB_URL", Path("datahub/us_market.db")),
)


_GOOGLE_DRIVE_HOSTS = {"drive.google.com", "docs.google.com"}
_GOOGLE_DRIVE_FORM_ACTION_RE = re.compile(
    r'<form[^>]+action="([^"]*drive\.usercontent\.google\.com/download[^"]*)"',
    re.IGNORECASE,
)
_GOOGLE_DRIVE_INPUT_RE = re.compile(
    r'<input[^>]+name="([^"]+)"[^>]+value="([^"]*)"',
    re.IGNORECASE,
)


def _log(message: str) -> None:
    print(f"[db-sync] {message}", flush=True)


def _is_google_drive_url(url: str) -> bool:
    return urllib.parse.urlparse(url).hostname in _GOOGLE_DRIVE_HOSTS


def _looks_like_html(path: Path) -> bool:
    with path.open("rb") as handle:
        prefix = handle.read(512).lstrip().lower()
    return prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html")


def _extract_google_drive_confirmation_url(page: bytes, base_url: str) -> str | None:
    text = page.decode("utf-8", errors="replace")
    action_match = _GOOGLE_DRIVE_FORM_ACTION_RE.search(text)
    if not action_match:
        return None

    action = html.unescape(action_match.group(1))
    params = {
        html.unescape(name): html.unescape(value)
        for name, value in _GOOGLE_DRIVE_INPUT_RE.findall(text)
    }
    if not params:
        return urllib.parse.urljoin(base_url, action)

    separator = "&" if "?" in action else "?"
    return urllib.parse.urljoin(base_url, action) + separator + urllib.parse.urlencode(params)


def _download(url: str, destination: Path) -> None:
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    headers = {"User-Agent": "Mozilla/5.0 ADE-Decision-Engine/1.0"}

    def fetch(target_url: str) -> tuple[str, str]:
        request = urllib.request.Request(target_url, headers=headers)
        with opener.open(request, timeout=600) as response, destination.open("wb") as output:
            content_type = response.headers.get_content_type()
            final_url = response.geturl()
            shutil.copyfileobj(response, output, length=1024 * 1024)
        return content_type, final_url

    content_type, final_url = fetch(url)
    if not _is_google_drive_url(url):
        return

    if content_type != "text/html" and not _looks_like_html(destination):
        return

    confirmation_url = _extract_google_drive_confirmation_url(destination.read_bytes(), final_url)
    if not confirmation_url:
        raise RuntimeError(
            "Google Drive returned an HTML page instead of the file. "
            "Verify that link sharing is set to anyone with the link."
        )

    _log("Google Drive confirmation page detected; continuing download")
    destination.unlink(missing_ok=True)
    content_type, _ = fetch(confirmation_url)
    if content_type == "text/html" or _looks_like_html(destination):
        raise RuntimeError(
            "Google Drive confirmation download still returned HTML. "
            "Verify public sharing or use another direct-download host."
        )


def _extract_database(downloaded: Path, expected_name: str, destination: Path) -> None:
    if zipfile.is_zipfile(downloaded):
        with zipfile.ZipFile(downloaded) as archive:
            candidates = [
                name
                for name in archive.namelist()
                if not name.endswith("/") and Path(name).name.lower() == expected_name.lower()
            ]
            if not candidates:
                db_files = [
                    name
                    for name in archive.namelist()
                    if not name.endswith("/") and Path(name).suffix.lower() in {".db", ".sqlite", ".sqlite3"}
                ]
                if len(db_files) == 1:
                    candidates = db_files
            if len(candidates) != 1:
                raise RuntimeError(
                    f"ZIP must contain exactly one usable database for {expected_name}; "
                    f"found {len(candidates)}"
                )
            with archive.open(candidates[0]) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
    else:
        shutil.copyfile(downloaded, destination)


def _validate_sqlite(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"Downloaded database is empty: {path}")

    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        result = connection.execute("PRAGMA quick_check").fetchone()
        if not result or str(result[0]).lower() != "ok":
            raise RuntimeError(f"SQLite quick_check failed: {result}")
    finally:
        connection.close()


def sync_database(url_env: str, destination: Path) -> bool:
    url = os.getenv(url_env, "").strip()
    if not url:
        _log(f"{url_env} is not set; keeping existing {destination}")
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ade-db-sync-") as temp_dir:
        temp_root = Path(temp_dir)
        downloaded = temp_root / "download"
        candidate = temp_root / destination.name

        _log(f"Downloading {destination.name} from {url_env}")
        _download(url, downloaded)
        _extract_database(downloaded, destination.name, candidate)
        _validate_sqlite(candidate)

        size_mb = candidate.stat().st_size / (1024 * 1024)
        os.replace(candidate, destination)
        _log(f"Installed {destination} ({size_mb:,.1f} MiB, quick_check=ok)")
        return True


def sync_market_databases() -> None:
    failures: list[str] = []
    for url_env, destination in DATABASES:
        try:
            sync_database(url_env, destination)
        except Exception as exc:  # startup log must identify the failed database
            failures.append(f"{destination}: {exc}")
            _log(f"ERROR {destination}: {exc}")

    # URL이 없는 DB는 기존 파일을 유지하고, 파일도 없으면 최소 스키마를 생성한다.
    ensure_market_databases()

    if failures:
        raise RuntimeError("Database synchronization failed: " + " | ".join(failures))


if __name__ == "__main__":
    sync_market_databases()
