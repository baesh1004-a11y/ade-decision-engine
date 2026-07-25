from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from maintenance.network import dashboard_urls


ROOT_DIR = Path(__file__).resolve().parent
UPDATE_FLAG = ROOT_DIR / "runtime" / "update.flag"


def _watch_for_update(process: subprocess.Popen[bytes], interval_seconds: float = 5.0) -> None:
    """Watch for a GitHub update signal and restart ADE safely from the user session."""
    while process.poll() is None:
        if UPDATE_FLAG.exists():
            try:
                UPDATE_FLAG.unlink(missing_ok=True)
                print("\nGitHub update signal detected. Updating ADE...")

                subprocess.run(
                    ["git", "fetch", "origin", "main"],
                    cwd=ROOT_DIR,
                    check=True,
                )
                subprocess.run(
                    ["git", "reset", "--hard", "origin/main"],
                    cwd=ROOT_DIR,
                    check=True,
                )

                requirements = ROOT_DIR / "requirements.txt"
                if requirements.exists():
                    subprocess.run(
                        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-r", str(requirements)],
                        cwd=ROOT_DIR,
                        check=True,
                    )

                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

                print("ADE update complete. Restarting...")
                os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])
            except Exception as exc:
                print(f"ADE automatic update failed: {exc}", file=sys.stderr)

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

    UPDATE_FLAG.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(app_cmd, cwd=ROOT_DIR)
    watcher = threading.Thread(target=_watch_for_update, args=(process,), daemon=True)
    watcher.start()
    raise SystemExit(process.wait())


if __name__ == "__main__":
    main()
