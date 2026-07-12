from __future__ import annotations

import argparse
from pathlib import Path

from maintenance.backup import ADEBackupManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore ADE data from a portable backup archive")
    parser.add_argument("backup", help="Path to ADE_Backup_*.zip")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing ADE data files after checksum verification.",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Show backup contents without restoring.",
    )
    args = parser.parse_args()

    manager = ADEBackupManager(".")
    if args.inspect:
        manifest = manager.inspect_backup(args.backup)
        print("\n========================================")
        print(" ADE BACKUP INSPECTION")
        print("========================================")
        print(f"Archive       : {Path(args.backup).resolve()}")
        print(f"Created       : {manifest.created_at}")
        print(f"Files         : {len(manifest.files)}")
        print(f"Includes .env : {'YES' if manifest.includes_env else 'NO'}")
        for item in manifest.files:
            print(f"- {item.path} ({item.size:,} bytes)")
        return

    manifest = manager.restore_backup(args.backup, overwrite=args.overwrite)
    print("\n========================================")
    print(" ADE RESTORE COMPLETE")
    print("========================================")
    print(f"Archive       : {Path(args.backup).resolve()}")
    print(f"Backup date   : {manifest.created_at}")
    print(f"Restored files: {len(manifest.files)}")
    print("Verification  : SHA-256 passed")


if __name__ == "__main__":
    main()
