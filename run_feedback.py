from __future__ import annotations

import subprocess
import sys


def main() -> None:
    cmd = [sys.executable, "-m", "streamlit", "run", "feedback/dashboard.py", "--server.address", "0.0.0.0"]
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
