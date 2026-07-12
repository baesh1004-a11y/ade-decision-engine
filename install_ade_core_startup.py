from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path


TASK_NAME = "ADE Core"


def main() -> None:
    if platform.system() != "Windows":
        raise SystemExit("This installer currently supports Windows only.")

    project_root = Path(__file__).resolve().parent
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    python_cmd = pythonw if pythonw.exists() else Path(sys.executable)
    core_script = project_root / "run_ade_core.py"

    task_command = (
        f'cmd /c "cd /d ""{project_root}"" && '
        f'""{python_cmd}"" ""{core_script}"""'
    )

    command = [
        "schtasks",
        "/Create",
        "/TN",
        TASK_NAME,
        "/SC",
        "ONLOGON",
        "/TR",
        task_command,
        "/RL",
        "LIMITED",
        "/F",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise SystemExit(f"Failed to install ADE Core startup task: {detail}")

    subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME], check=False)
    print("ADE Core startup task installed.")
    print("ADE Core will start automatically whenever you sign in to Windows.")
    print("The task has also been started now.")


if __name__ == "__main__":
    main()
