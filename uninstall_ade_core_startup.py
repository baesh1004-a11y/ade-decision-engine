from __future__ import annotations

import platform
import subprocess


TASK_NAME = "ADE Core"


def main() -> None:
    if platform.system() != "Windows":
        raise SystemExit("This uninstaller currently supports Windows only.")

    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise SystemExit(f"Failed to remove ADE Core startup task: {detail}")
    print("ADE Core startup task removed.")


if __name__ == "__main__":
    main()
