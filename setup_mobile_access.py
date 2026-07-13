from __future__ import annotations

import argparse
import platform
import subprocess


RULE_NAME = "ADE Dashboard 8501"


def main() -> None:
    parser = argparse.ArgumentParser(description="Allow ADE mobile access through Windows Firewall")
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()

    if platform.system() != "Windows":
        raise SystemExit("This helper currently supports Windows only.")

    delete_cmd = [
        "netsh",
        "advfirewall",
        "firewall",
        "delete",
        "rule",
        f"name={RULE_NAME}",
    ]
    subprocess.run(delete_cmd, capture_output=True, text=True)

    add_cmd = [
        "netsh",
        "advfirewall",
        "firewall",
        "add",
        "rule",
        f"name={RULE_NAME}",
        "dir=in",
        "action=allow",
        "protocol=TCP",
        f"localport={args.port}",
        "profile=private",
    ]
    result = subprocess.run(add_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise SystemExit(
            "Windows Firewall rule creation failed. "
            "Run Command Prompt as Administrator and try again.\n"
            f"Detail: {detail}"
        )

    print(f"Windows Firewall rule created for TCP port {args.port} on Private networks.")
    print("Keep the PC and phone on the same trusted Wi-Fi network.")


if __name__ == "__main__":
    main()
