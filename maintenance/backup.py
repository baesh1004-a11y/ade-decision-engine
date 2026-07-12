from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


BACKUP_FORMAT_VERSION = 1
DEFAULT_ITEMS = (
    Path("datahub/market.db"),
    Path("config"),
    Path("models"),
    Path("cache/jp_radar"),
    Path("output"),
)


@dataclass(frozen=True)
class BackupFile:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class BackupManifest:
    format_version: int
    created_at: str
    files: list[BackupFile]
    includes_env: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": self.format_version,
            "created_at": self.created_at,
            "files": [asdict(item) for item in self.files],
            "includes_env": self.includes_env,
        }


class ADEBackupManager:
    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root).resolve()

    def create_backup(
        self,
        destination: str | Path,
        include_env: bool = False,
    ) -> BackupManifest:
        destination_path = Path(destination).resolve()
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="ade_backup_") as temp_dir:
            stage_root = Path(temp_dir)
            files: list[BackupFile] = []

            for item in DEFAULT_ITEMS:
                source = self.project_root / item
                if not source.exists():
                    continue
                if source.is_dir():
                    for child in source.rglob("*"):
                        if child.is_file():
                            files.append(self._stage_file(child, stage_root))
                else:
                    staged_source = source
                    if item.as_posix() == "datahub/market.db":
                        staged_source = self._snapshot_sqlite(source, stage_root / "_sqlite_snapshot.db")
                    files.append(self._stage_file(staged_source, stage_root, archive_path=item))

            if include_env:
                env_file = self.project_root / ".env"
                if env_file.exists():
                    files.append(self._stage_file(env_file, stage_root, archive_path=Path(".env")))

            manifest = BackupManifest(
                format_version=BACKUP_FORMAT_VERSION,
                created_at=datetime.now().isoformat(timespec="seconds"),
                files=sorted(files, key=lambda item: item.path),
                includes_env=include_env and (self.project_root / ".env").exists(),
            )
            (stage_root / "manifest.json").write_text(
                json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with zipfile.ZipFile(destination_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for child in stage_root.rglob("*"):
                    if child.is_file() and child.name != "_sqlite_snapshot.db":
                        archive.write(child, child.relative_to(stage_root).as_posix())

        return manifest

    def restore_backup(
        self,
        source: str | Path,
        overwrite: bool = False,
    ) -> BackupManifest:
        source_path = Path(source).resolve()
        if not source_path.exists():
            raise FileNotFoundError(source_path)

        with tempfile.TemporaryDirectory(prefix="ade_restore_") as temp_dir:
            stage_root = Path(temp_dir)
            with zipfile.ZipFile(source_path, "r") as archive:
                self._safe_extract(archive, stage_root)

            manifest_path = stage_root / "manifest.json"
            if not manifest_path.exists():
                raise ValueError("Invalid ADE backup: manifest.json is missing")
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = BackupManifest(
                format_version=int(raw["format_version"]),
                created_at=str(raw["created_at"]),
                files=[BackupFile(**item) for item in raw.get("files", [])],
                includes_env=bool(raw.get("includes_env", False)),
            )
            if manifest.format_version != BACKUP_FORMAT_VERSION:
                raise ValueError(f"Unsupported backup format: {manifest.format_version}")

            self._verify(stage_root, manifest)
            for item in manifest.files:
                staged = stage_root / item.path
                target = self.project_root / item.path
                if target.exists() and not overwrite:
                    raise FileExistsError(f"Restore target already exists: {target}")
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and target.is_dir():
                    shutil.rmtree(target)
                shutil.copy2(staged, target)

        return manifest

    def inspect_backup(self, source: str | Path) -> BackupManifest:
        source_path = Path(source).resolve()
        with zipfile.ZipFile(source_path, "r") as archive:
            raw = json.loads(archive.read("manifest.json").decode("utf-8"))
        return BackupManifest(
            format_version=int(raw["format_version"]),
            created_at=str(raw["created_at"]),
            files=[BackupFile(**item) for item in raw.get("files", [])],
            includes_env=bool(raw.get("includes_env", False)),
        )

    def _snapshot_sqlite(self, source: Path, destination: Path) -> Path:
        source_conn = sqlite3.connect(str(source))
        destination_conn = sqlite3.connect(str(destination))
        try:
            source_conn.backup(destination_conn)
        finally:
            destination_conn.close()
            source_conn.close()
        return destination

    def _stage_file(
        self,
        source: Path,
        stage_root: Path,
        archive_path: Path | None = None,
    ) -> BackupFile:
        relative = archive_path or source.relative_to(self.project_root)
        target = stage_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return BackupFile(
            path=relative.as_posix(),
            size=target.stat().st_size,
            sha256=self._sha256(target),
        )

    @staticmethod
    def _verify(stage_root: Path, manifest: BackupManifest) -> None:
        for item in manifest.files:
            path = stage_root / item.path
            if not path.exists():
                raise ValueError(f"Backup file is missing: {item.path}")
            if path.stat().st_size != item.size:
                raise ValueError(f"Backup size mismatch: {item.path}")
            if ADEBackupManager._sha256(path) != item.sha256:
                raise ValueError(f"Backup checksum mismatch: {item.path}")

    @staticmethod
    def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
        destination_resolved = destination.resolve()
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if destination_resolved not in target.parents and target != destination_resolved:
                raise ValueError(f"Unsafe archive path: {member.filename}")
        archive.extractall(destination)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
