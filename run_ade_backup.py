from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from maintenance.backup import ADEBackupManager


def main() -> None:
    default_name = f"ADE_Backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    parser = argparse.ArgumentParser(description="Create a portable ADE backup archive")
    parser.add_argument("--output", default=str(Path("backups") / default_name))
    parser.add_argument(
        "--include-env",
        action="store_true",
        help="Include .env API credentials in the backup archive.",
    )
    args = parser.parse_args()

    manager = ADEBackupManager(".")
    manifest = manager.create_backup(args.output, include_env=args.include_env)
    total_size = sum(item.size for item in manifest.files)

    print("\n========================================")
    print(" ADE BACKUP COMPLETE")
    print("========================================")
    print(f"Archive       : {Path(args.output).resolve()}")
    print(f"Created       : {manifest.created_at}")
    print(f"Files         : {len(manifest.files)}")
    print(f"Data size     : {total_size / 1024 / 1024:,.1f} MB")
    print(f"Includes .env : {'YES' if manifest.includes_env else 'NO'}")
    print("Verification  : SHA-256 manifest created")


if __name__ == "__main__":
    main()
