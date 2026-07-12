from __future__ import annotations

import subprocess
import sys


def main() -> None:
    """Start only the ADE dashboard.

    Automatic recommendation scheduling is handled independently by
    run_ade_core.py, so closing the dashboard does not stop ADE Core.
    """
    app_cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "ade_home.py",
        "--server.address",
        "0.0.0.0",
    ]
    raise SystemExit(subprocess.call(app_cmd))


if __name__ == "__main__":
    main()
