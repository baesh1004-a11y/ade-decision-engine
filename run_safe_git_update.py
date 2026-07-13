from __future__ import annotations

import argparse
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "datahub" / "market.db"
BACKUP_ROOT = PROJECT_ROOT / "backups" / "pre_git_update"


def _run(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
        capture_output=capture,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safely update ADE source code while preserving the local market.db"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Run without interactive confirmation.",
    )
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_ROOT / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    db_backup = backup_dir / "market.db"
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, db_backup)
        print(f"DB backup created: {db_backup}")
    else:
        print("No local market.db found; source update will continue.")

    patch_path = backup_dir / "local_code_changes.patch"
    diff = _run("git", "diff", "HEAD", "--binary", capture=True).stdout
    patch_path.write_text(diff, encoding="utf-8")
    if diff.strip():
        print(f"Local code changes saved as patch: {patch_path}")
    else:
        print("No tracked local code changes found.")

    status = _run("git", "status", "--short", capture=True).stdout.strip()
    if status:
        print("\nCurrent local changes:")
        print(status)

    if not args.yes:
        answer = input(
            "\nContinue? Tracked local changes will be reset after being saved as a patch. [y/N]: "
        ).strip().lower()
        if answer not in {"y", "yes"}:
            print("Cancelled. No Git changes were made.")
            return

    _run("git", "restore", "--source=HEAD", "--staged", "--worktree", ".")
    _run("git", "pull", "--ff-only")

    if db_backup.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_backup, DB_PATH)
        print(f"Local DB restored: {DB_PATH}")

    print("\nADE source update completed safely.")
    print("Git now manages source code only; market.db, reports, output, cache and backups stay local.")
    if diff.strip():
        print(f"Review local code patch if needed: {patch_path}")


if __name__ == "__main__":
    main()
