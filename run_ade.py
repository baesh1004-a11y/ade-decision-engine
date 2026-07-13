from __future__ import annotations

import argparse
import subprocess
import sys

from maintenance.network import dashboard_urls


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
    print(" ADE DASHBOARD")
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
        "ade_home.py",
        "--server.address",
        address,
        "--server.port",
        str(args.port),
        "--server.headless",
        "true",
    ]
    raise SystemExit(subprocess.call(app_cmd))


if __name__ == "__main__":
    main()
