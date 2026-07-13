# ADE Two-PC Operating Guide

## Principle

GitHub manages source code only.

Each PC keeps its own local runtime data:

- `datahub/market.db`
- `.env`
- `output/`
- `reports/`
- `cache/`
- `backups/`

Do not use `git push` to move databases or reports between PCs. Use ADE backup and restore instead.

## One-time migration on each existing PC

Run this only after any current recommendation or Replay DB job has finished.

```cmd
python run_safe_git_update.py
```

The script performs these steps:

1. Copies `datahub/market.db` to `backups/pre_git_update/<timestamp>/market.db`.
2. Saves tracked local code changes as `local_code_changes.patch`.
3. Resets tracked local changes.
4. Pulls the latest source with `git pull --ff-only`.
5. Restores the local database.

After completion:

```cmd
git status
```

The database, reports, output, cache, backups and `.env` should no longer appear in Git status.

## Normal code update on both PCs

When no ADE database job is running:

```cmd
git pull --ff-only
```

After the one-time migration, this updates code without touching `market.db`.

## Moving the latest ADE data from PC 1 to PC 2

On PC 1, stop or finish recommendation, Replay DB, Feedback and other database jobs. Then create a backup:

```cmd
python run_ade_backup.py
```

Copy the new ZIP file from `backups/` to PC 2.

On PC 2, stop ADE Core and Dashboard before restoring. Then run:

```cmd
python run_ade_restore.py "<backup zip path>" --overwrite
```

Restart ADE Core or Windows login task after restore.

## Verifying both PCs

On PC 1:

```cmd
python run_verify_environment.py --save output\pc1_environment.json
```

Copy the JSON file to PC 2 and run:

```cmd
python run_verify_environment.py --compare "<pc1_environment.json path>"
```

`git_commit`, `db_sha256` and `table_counts` are the key checks.

## Important operating rule

Only one PC should be treated as the active data-producing PC at a time.

The two local SQLite databases do not automatically synchronize. Running recommendations independently on both PCs creates different local histories. To make both PCs identical again, choose the authoritative PC, create an ADE backup there, and restore that backup on the other PC.
