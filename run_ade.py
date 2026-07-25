from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from maintenance.network import dashboard_urls


ROOT_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT_DIR / "runtime"
UPDATE_FLAG = RUNTIME_DIR / "update.flag"
REQUIREMENTS_FILE = ROOT_DIR / "requirements.txt"
REQUIREMENTS_STAMP = RUNTIME_DIR / "requirements.sha256"
UPDATE_LOG = ROOT_DIR / "logs" / "auto_update_ade.log"


def _log(message: str) -> None:
    UPDATE_LOG.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with UPDATE_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")
    print(message, flush=True)


def _requirements_hash() -> str:
    if not REQUIREMENTS_FILE.exists():
        return ""
    return hashlib.sha256(REQUIREMENTS_FILE.read_bytes()).hexdigest()


def _install_requirements_if_needed() -> None:
    if not REQUIREMENTS_FILE.exists():
        return

    current_hash = _requirements_hash()
    saved_hash = REQUIREMENTS_STAMP.read_text(encoding="utf-8").strip() if REQUIREMENTS_STAMP.exists() else ""

    core_imports_ok = subprocess.run(
        [sys.executable, "-c", "import streamlit, plotly, pandas, numpy"],
        cwd=ROOT_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0

    if current_hash == saved_hash and core_imports_ok:
        _log("Python dependencies are already current.")
        return

    _log("Installing changed or missing Python dependencies...")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-r",
            str(REQUIREMENTS_FILE),
        ],
        cwd=ROOT_DIR,
        check=True,
    )
    REQUIREMENTS_STAMP.write_text(current_hash, encoding="utf-8")


def _update_repository() -> None:
    subprocess.run(["git", "fetch", "origin", "main"], cwd=ROOT_DIR, check=True)

    local_changes = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if local_changes:
        raise RuntimeError("Local changes exist; automatic update was skipped to prevent data loss.")

    local_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT_DIR, check=True, capture_output=True, text=True
    ).stdout.strip()
    remote_sha = subprocess.run(
        ["git", "rev-parse", "origin/main"], cwd=ROOT_DIR, check=True, capture_output=True, text=True
    ).stdout.strip()

    if local_sha == remote_sha:
        _log("Repository is already current.")
        return

    subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=ROOT_DIR, check=True)
    _log(f"Repository updated: {local_sha[:8]} -> {remote_sha[:8]}")


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _watch_for_update(process: subprocess.Popen[bytes], interval_seconds: float = 3.0) -> None:
    """Receive an Actions signal, update once, then restart ADE from the user session."""
    while process.poll() is None:
        if UPDATE_FLAG.exists():
            signal = UPDATE_FLAG.read_text(encoding="utf-8", errors="ignore").strip()
            UPDATE_FLAG.unlink(missing_ok=True)
            try:
                _log(f"GitHub update signal detected: {signal or 'manual'}")
                _update_repository()
                _install_requirements_if_needed()
                _stop_process(process)
                _log("ADE update completed. Restarting ADE...")
                os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])
            except Exception as exc:
                _log(f"ADE automatic update failed: {exc}")
        time.sleep(interval_seconds)


def main() -> None:
    """Start the ADE dashboard for desktop and same-Wi-Fi mobile access."""
    parser = argparse.ArgumentParser(description="Start ADE Dashboard")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Bind only to this PC instead of the local network.",
    )
    args = parser.parse_args()

    address = "127.0.0.1" if args.local_only else "0.0.0.0"
    urls = dashboard_urls(args.port)

    print("========================================")
    print(" ADE PROFESSIONAL TERMINAL")
    print("========================================")
    print(f"Desktop : {urls['desktop']}")
    if args.local_only:
        print("Mobile  : disabled (--local-only)")
    else:
        print(f"Mobile  : {urls['mobile']}")
        print("Condition: PC and phone must use the same Wi-Fi/LAN.")
    print("========================================")

    app_cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "dashboard_app.py",
        "--server.address",
        address,
        "--server.port",
        str(args.port),
        "--server.headless",
        "true",
    ]

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(app_cmd, cwd=ROOT_DIR)
    watcher = threading.Thread(target=_watch_for_update, args=(process,), daemon=True)
    watcher.start()
    raise SystemExit(process.wait())


if __name__ == "__main__":
    main()
