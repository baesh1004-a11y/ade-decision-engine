from __future__ import annotations

import subprocess
import sys


def main() -> None:
    scheduler_cmd = [sys.executable, "run_daily_scheduler.py"]
    app_cmd = [sys.executable, "-m", "streamlit", "run", "ade_home.py", "--server.address", "0.0.0.0"]

    scheduler = subprocess.Popen(scheduler_cmd)
    try:
        exit_code = subprocess.call(app_cmd)
    finally:
        scheduler.terminate()
        try:
            scheduler.wait(timeout=10)
        except subprocess.TimeoutExpired:
            scheduler.kill()
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
