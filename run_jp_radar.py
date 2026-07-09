from __future__ import annotations

import subprocess
import sys


def main() -> None:
    cmd = [sys.executable, "-m", "streamlit", "run", "jp_radar/dashboard.py"]
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
