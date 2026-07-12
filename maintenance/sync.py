from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from maintenance.backup import ADEBackupManager


SYNC_CONFIG_FILE = Path(".ade_sync.json")
SYNC_STATE_FILE = Path(".ade_sync_state.json")
REMOTE_ARCHIVE_NAME = "ADE_Latest.zip"
REMOTE_META_NAME = "ADE_Latest.json"


@dataclass(frozen=True)
class SyncConfig:
    folder: str
    machine_name: str
    include_env: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SyncState:
    remote_sha256: str | None = None
    local_db_sha256: str | None = None
    synced_at: str | None = None
    direction: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ADESyncManager:
    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self.backup = ADEBackupManager(self.project_root)
        self.config_path = self.project_root / SYNC_CONFIG_FILE
        self.state_path = self.project_root / SYNC_STATE_FILE

    def configure(
        self,
        folder: str | Path,
        machine_name: str | None = None,
        include_env: bool = False,
    ) -> SyncConfig:
        sync_folder = Path(folder).expanduser().resolve()
        sync_folder.mkdir(parents=True, exist_ok=True)
        config = SyncConfig(
            folder=str(sync_folder),
            machine_name=machine_name or os.environ.get("COMPUTERNAME") or "ADE-PC",
            include_env=include_env,
        )
        self.config_path.write_text(
            json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return config

    def load_config(self) -> SyncConfig:
        if not self.config_path.exists():
            raise FileNotFoundError(
                "ADE sync is not configured. Run: python run_ade_sync.py configure --folder <shared-folder>"
            )
        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        return SyncConfig(
            folder=str(raw["folder"]),
            machine_name=str(raw.get("machine_name") or "ADE-PC"),
            include_env=bool(raw.get("include_env", False)),
        )

    def status(self) -> dict[str, object]:
        config = self.load_config()
        folder = Path(config.folder)
        archive = folder / REMOTE_ARCHIVE_NAME
        meta = folder / REMOTE_META_NAME
        state = self._load_state()
        return {
            "configured_folder": str(folder),
            "machine_name": config.machine_name,
            "remote_exists": archive.exists(),
            "remote_size": archive.stat().st_size if archive.exists() else 0,
            "remote_updated_at": self._remote_updated_at(meta, archive),
            "remote_sha256": self._sha256(archive) if archive.exists() else None,
            "local_db_sha256": self._local_db_sha256(),
            "last_sync": state.to_dict(),
        }

    def push(self, force: bool = False) -> dict[str, object]:
        config = self.load_config()
        folder = Path(config.folder)
        folder.mkdir(parents=True, exist_ok=True)
        archive = folder / REMOTE_ARCHIVE_NAME
        meta = folder / REMOTE_META_NAME
        state = self._load_state()

        remote_sha = self._sha256(archive) if archive.exists() else None
        local_db_sha = self._local_db_sha256()
        if archive.exists() and not force:
            if state.remote_sha256 and remote_sha != state.remote_sha256:
                raise RuntimeError(
                    "Remote ADE backup changed on another PC. Run pull first, or use --force only if overwrite is intended."
                )

        with tempfile.TemporaryDirectory(prefix="ade_sync_push_") as temp_dir:
            temp_archive = Path(temp_dir) / REMOTE_ARCHIVE_NAME
            manifest = self.backup.create_backup(temp_archive, include_env=config.include_env)
            temp_sha = self._sha256(temp_archive)
            target_temp = folder / f".{REMOTE_ARCHIVE_NAME}.tmp"
            shutil.copy2(temp_archive, target_temp)
            target_temp.replace(archive)

        now = datetime.now().isoformat(timespec="seconds")
        metadata = {
            "updated_at": now,
            "machine_name": config.machine_name,
            "archive": REMOTE_ARCHIVE_NAME,
            "sha256": temp_sha,
            "local_db_sha256": local_db_sha,
            "files": len(manifest.files),
        }
        meta.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        self._save_state(
            SyncState(
                remote_sha256=temp_sha,
                local_db_sha256=local_db_sha,
                synced_at=now,
                direction="push",
            )
        )
        return metadata

    def pull(self, force: bool = False) -> dict[str, object]:
        config = self.load_config()
        folder = Path(config.folder)
        archive = folder / REMOTE_ARCHIVE_NAME
        meta = folder / REMOTE_META_NAME
        if not archive.exists():
            raise FileNotFoundError(f"Remote ADE backup not found: {archive}")

        state = self._load_state()
        remote_sha = self._sha256(archive)
        local_db_sha = self._local_db_sha256()
        if not force and state.local_db_sha256 and local_db_sha:
            if local_db_sha != state.local_db_sha256 and remote_sha != state.remote_sha256:
                raise RuntimeError(
                    "Both this PC and the shared backup changed after the last sync. Resolve manually or use --force."
                )

        manifest = self.backup.restore_backup(archive, overwrite=True)
        now = datetime.now().isoformat(timespec="seconds")
        restored_db_sha = self._local_db_sha256()
        self._save_state(
            SyncState(
                remote_sha256=remote_sha,
                local_db_sha256=restored_db_sha,
                synced_at=now,
                direction="pull",
            )
        )
        metadata = {}
        if meta.exists():
            try:
                metadata = json.loads(meta.read_text(encoding="utf-8"))
            except Exception:
                metadata = {}
        metadata.update(
            {
                "pulled_at": now,
                "remote_sha256": remote_sha,
                "restored_files": len(manifest.files),
            }
        )
        return metadata

    def _load_state(self) -> SyncState:
        if not self.state_path.exists():
            return SyncState()
        raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        return SyncState(
            remote_sha256=raw.get("remote_sha256"),
            local_db_sha256=raw.get("local_db_sha256"),
            synced_at=raw.get("synced_at"),
            direction=raw.get("direction"),
        )

    def _save_state(self, state: SyncState) -> None:
        self.state_path.write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _local_db_sha256(self) -> str | None:
        path = self.project_root / "datahub/market.db"
        return self._sha256(path) if path.exists() else None

    @staticmethod
    def _remote_updated_at(meta: Path, archive: Path) -> str | None:
        if meta.exists():
            try:
                return str(json.loads(meta.read_text(encoding="utf-8")).get("updated_at"))
            except Exception:
                pass
        if archive.exists():
            return datetime.fromtimestamp(archive.stat().st_mtime).isoformat(timespec="seconds")
        return None

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
