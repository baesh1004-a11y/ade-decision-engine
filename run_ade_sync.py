from __future__ import annotations

import argparse
import json

from maintenance.sync import ADESyncManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize ADE data through a shared folder")
    sub = parser.add_subparsers(dest="command", required=True)

    configure = sub.add_parser("configure", help="Configure a shared sync folder")
    configure.add_argument("--folder", required=True)
    configure.add_argument("--machine-name")
    configure.add_argument("--include-env", action="store_true")

    sub.add_parser("status", help="Show local and remote sync status")

    push = sub.add_parser("push", help="Upload this PC's ADE state to the shared folder")
    push.add_argument("--force", action="store_true")

    pull = sub.add_parser("pull", help="Restore the latest ADE state from the shared folder")
    pull.add_argument("--force", action="store_true")

    args = parser.parse_args()
    manager = ADESyncManager(".")

    if args.command == "configure":
        result = manager.configure(
            folder=args.folder,
            machine_name=args.machine_name,
            include_env=args.include_env,
        ).to_dict()
    elif args.command == "status":
        result = manager.status()
    elif args.command == "push":
        result = manager.push(force=args.force)
    elif args.command == "pull":
        result = manager.pull(force=args.force)
    else:
        raise SystemExit(2)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
