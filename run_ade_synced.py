from __future__ import annotations

import argparse
import subprocess
import sys

from maintenance.sync import ADESyncManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull ADE data, run ADE Home, then push on exit")
    parser.add_argument("--no-pull", action="store_true")
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--force-pull", action="store_true")
    parser.add_argument("--force-push", action="store_true")
    args = parser.parse_args()

    manager = ADESyncManager(".")

    if not args.no_pull:
        print("[SYNC] Pulling latest ADE state...")
        manager.pull(force=args.force_pull)
        print("[SYNC] Pull complete")

    cmd = [sys.executable, "-m", "streamlit", "run", "ade_home.py", "--server.address", "0.0.0.0"]
    exit_code = subprocess.call(cmd)

    if not args.no_push:
        print("[SYNC] Pushing ADE state...")
        manager.push(force=args.force_push)
        print("[SYNC] Push complete")

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
