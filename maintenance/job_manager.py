from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator


LOCK_PATH = Path("output/ade_job.lock")
STATUS_PATH = Path("output/ade_job_status.json")


class JobBusyError(RuntimeError):
    pass


class ADEJobManager:
    def __init__(self, lock_path: str | Path = LOCK_PATH, status_path: str | Path = STATUS_PATH) -> None:
        self.lock_path = Path(lock_path)
        self.status_path = Path(status_path)
        self._handle = None

    @contextmanager
    def acquire(
        self,
        job_name: str,
        *,
        wait: bool = True,
        timeout_seconds: int = 3600,
        poll_seconds: float = 2.0,
    ) -> Iterator[None]:
        started = time.monotonic()
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a+", encoding="utf-8")
        self._handle = handle

        while True:
            if self._try_lock(handle):
                break
            if not wait:
                handle.close()
                self._handle = None
                raise JobBusyError(self._busy_message(job_name))
            if time.monotonic() - started >= timeout_seconds:
                handle.close()
                self._handle = None
                raise JobBusyError(self._busy_message(job_name, timed_out=True))
            time.sleep(max(0.2, poll_seconds))

        self._write_status(
            state="RUNNING",
            job_name=job_name,
            message="Job started",
        )
        try:
            yield
        except Exception as exc:
            self._write_status(
                state="FAILED",
                job_name=job_name,
                message=str(exc),
            )
            raise
        else:
            self._write_status(
                state="COMPLETED",
                job_name=job_name,
                message="Job completed",
            )
        finally:
            self._unlock(handle)
            handle.close()
            self._handle = None

    def current_status(self) -> dict[str, object] | None:
        if not self.status_path.exists():
            return None
        try:
            return json.loads(self.status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _busy_message(self, requested_job: str, timed_out: bool = False) -> str:
        status = self.current_status() or {}
        running_job = status.get("job_name") or "another ADE job"
        prefix = "Timed out waiting for" if timed_out else "ADE is busy with"
        return f"{prefix} '{running_job}'. Requested job: '{requested_job}'."

    def _write_status(self, *, state: str, job_name: str, message: str) -> None:
        payload = {
            "state": state,
            "job_name": job_name,
            "pid": os.getpid(),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "message": message,
        }
        self.status_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _try_lock(handle) -> bool:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (OSError, BlockingIOError):
            return False

    @staticmethod
    def _unlock(handle) -> None:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
