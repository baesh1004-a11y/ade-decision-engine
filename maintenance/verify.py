from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path("datahub/market.db")
KEY_TABLES = (
    "price_bars",
    "replay_events",
    "replay_event_flow",
    "replay_event_vectors",
    "pattern_vectors",
    "paper_orders",
    "kis_account_snapshots",
    "kis_position_snapshots",
    "feedback_cases",
    "feedback_daily",
)
REQUIRED_FILES = (
    Path("run_ade.py"),
    Path("run_recommend_v3.py"),
    Path("run_jp_radar_live.py"),
    Path("run_feedback.py"),
    Path("requirements.txt"),
)
PACKAGE_NAMES = (
    "pandas",
    "numpy",
    "pykrx",
    "finance-datareader",
    "ta",
    "fastapi",
    "uvicorn",
    "streamlit",
    "plotly",
    "yfinance",
    "tqdm",
)


@dataclass(frozen=True)
class VerificationItem:
    name: str
    status: str
    value: Any
    detail: str = ""


@dataclass(frozen=True)
class VerificationReport:
    created_at: str
    project_root: str
    machine: str
    python_version: str
    git_commit: str | None
    git_branch: str | None
    git_dirty: bool | None
    db_path: str
    db_exists: bool
    db_size: int
    db_sha256: str | None
    db_integrity: str
    table_counts: dict[str, int | None]
    package_versions: dict[str, str | None]
    required_files: dict[str, bool]
    items: list[VerificationItem]
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "project_root": self.project_root,
            "machine": self.machine,
            "python_version": self.python_version,
            "git_commit": self.git_commit,
            "git_branch": self.git_branch,
            "git_dirty": self.git_dirty,
            "db_path": self.db_path,
            "db_exists": self.db_exists,
            "db_size": self.db_size,
            "db_sha256": self.db_sha256,
            "db_integrity": self.db_integrity,
            "table_counts": self.table_counts,
            "package_versions": self.package_versions,
            "required_files": self.required_files,
            "items": [asdict(item) for item in self.items],
            "fingerprint": self.fingerprint,
        }


class ADEEnvironmentVerifier:
    def __init__(self, project_root: str | Path = ".", db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.project_root = Path(project_root).resolve()
        db = Path(db_path)
        self.db_path = db if db.is_absolute() else self.project_root / db

    def verify(self) -> VerificationReport:
        items: list[VerificationItem] = []

        python_version = platform.python_version()
        python_ok = sys.version_info[:2] == (3, 12)
        items.append(
            VerificationItem(
                "Python 3.12",
                "PASS" if python_ok else "WARN",
                python_version,
                "Python 3.12.x 권장" if not python_ok else "",
            )
        )

        git_commit = self._git("rev-parse", "HEAD")
        git_branch = self._git("rev-parse", "--abbrev-ref", "HEAD")
        git_status = self._git("status", "--porcelain")
        git_dirty = None if git_status is None else bool(git_status.strip())
        items.append(
            VerificationItem(
                "Git commit",
                "PASS" if git_commit else "FAIL",
                git_commit or "not available",
            )
        )
        items.append(
            VerificationItem(
                "Git working tree",
                "PASS" if git_dirty is False else ("WARN" if git_dirty else "FAIL"),
                "clean" if git_dirty is False else ("modified" if git_dirty else "not available"),
            )
        )

        package_versions: dict[str, str | None] = {}
        for package in PACKAGE_NAMES:
            try:
                package_versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                package_versions[package] = None
        missing_packages = [name for name, version in package_versions.items() if version is None]
        items.append(
            VerificationItem(
                "Required packages",
                "PASS" if not missing_packages else "FAIL",
                f"{len(PACKAGE_NAMES) - len(missing_packages)}/{len(PACKAGE_NAMES)} installed",
                ", ".join(missing_packages),
            )
        )

        required_files = {
            path.as_posix(): (self.project_root / path).exists()
            for path in REQUIRED_FILES
        }
        missing_files = [name for name, exists in required_files.items() if not exists]
        items.append(
            VerificationItem(
                "Required files",
                "PASS" if not missing_files else "FAIL",
                f"{len(required_files) - len(missing_files)}/{len(required_files)} found",
                ", ".join(missing_files),
            )
        )

        db_exists = self.db_path.exists()
        db_size = self.db_path.stat().st_size if db_exists else 0
        db_sha256 = self._sha256(self.db_path) if db_exists else None
        db_integrity, table_counts = self._inspect_database()
        items.append(
            VerificationItem(
                "SQLite database",
                "PASS" if db_exists else "FAIL",
                str(self.db_path),
            )
        )
        items.append(
            VerificationItem(
                "SQLite integrity",
                "PASS" if db_integrity == "ok" else "FAIL",
                db_integrity,
            )
        )

        essential_tables = (
            "price_bars",
            "replay_events",
            "replay_event_flow",
            "replay_event_vectors",
        )
        table_ok = all((table_counts.get(name) or 0) > 0 for name in essential_tables)
        items.append(
            VerificationItem(
                "Core Replay data",
                "PASS" if table_ok else "FAIL",
                {name: table_counts.get(name) for name in essential_tables},
            )
        )

        fingerprint_source = {
            "python_major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
            "git_commit": git_commit,
            "db_sha256": db_sha256,
            "table_counts": table_counts,
            "package_versions": package_versions,
            "required_files": required_files,
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_source, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

        return VerificationReport(
            created_at=datetime.now().isoformat(timespec="seconds"),
            project_root=str(self.project_root),
            machine=platform.node(),
            python_version=python_version,
            git_commit=git_commit,
            git_branch=git_branch,
            git_dirty=git_dirty,
            db_path=str(self.db_path),
            db_exists=db_exists,
            db_size=db_size,
            db_sha256=db_sha256,
            db_integrity=db_integrity,
            table_counts=table_counts,
            package_versions=package_versions,
            required_files=required_files,
            items=items,
            fingerprint=fingerprint,
        )

    def compare(self, current: VerificationReport, other_file: str | Path) -> dict[str, Any]:
        other = json.loads(Path(other_file).read_text(encoding="utf-8"))
        checks = {
            "git_commit": current.git_commit == other.get("git_commit"),
            "python_major_minor": self._major_minor(current.python_version)
            == self._major_minor(str(other.get("python_version", ""))),
            "db_sha256": current.db_sha256 == other.get("db_sha256"),
            "table_counts": current.table_counts == other.get("table_counts"),
            "package_versions": current.package_versions == other.get("package_versions"),
            "required_files": current.required_files == other.get("required_files"),
            "fingerprint": current.fingerprint == other.get("fingerprint"),
        }
        return {
            "current_machine": current.machine,
            "other_machine": other.get("machine"),
            "checks": checks,
            "identical": all(checks.values()),
        }

    def save(self, report: VerificationReport, destination: str | Path) -> Path:
        destination_path = Path(destination)
        if not destination_path.is_absolute():
            destination_path = self.project_root / destination_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return destination_path.resolve()

    def _inspect_database(self) -> tuple[str, dict[str, int | None]]:
        counts = {name: None for name in KEY_TABLES}
        if not self.db_path.exists():
            return "missing", counts
        try:
            conn = sqlite3.connect(str(self.db_path))
            try:
                integrity_row = conn.execute("PRAGMA integrity_check").fetchone()
                integrity = str(integrity_row[0]) if integrity_row else "unknown"
                existing = {
                    str(row[0])
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                for table in KEY_TABLES:
                    if table in existing:
                        counts[table] = int(
                            conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                        )
                return integrity, counts
            finally:
                conn.close()
        except sqlite3.Error as exc:
            return f"error: {exc}", counts

    def _git(self, *args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.project_root,
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
            return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _major_minor(version: str) -> str:
        parts = version.split(".")
        return ".".join(parts[:2]) if len(parts) >= 2 else version
