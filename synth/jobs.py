"""Single-worker generation queue for the local UI.

Model jobs are deliberately serial. Concurrent Metal generations compete for the same
device and make both jobs slower and less predictable. The queue owns only transient UI
state; completed WAV files and sidecars remain the persistent source of truth.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


class GenerationFailure(RuntimeError):
    """A visible queue failure carrying corrected facts for its summary card."""

    def __init__(self, message: str, *, summary_updates: dict | None = None) -> None:
        super().__init__(message)
        self.summary_updates = dict(summary_updates or {})


@dataclass
class GenerationJob:
    id: str
    payload: dict
    summary: dict
    expected_seconds: float
    status: str = "queued"
    created_at: float = field(default_factory=time.monotonic)
    started_at: float | None = None
    completed_at: float | None = None
    output_path: str | None = None
    error: str | None = None


class GenerationQueue:
    """Run generation jobs one at a time and expose thread-safe UI snapshots."""

    def __init__(
        self,
        run: Callable[[dict], object],
        *,
        clock: Callable[[], float] = time.monotonic,
        completed_hold_seconds: float = 0.75,
    ) -> None:
        self._run = run
        self._clock = clock
        self._completed_hold_seconds = completed_hold_seconds
        self._jobs: list[GenerationJob] = []
        self._condition = threading.Condition()
        self._stopping = False
        self._worker = threading.Thread(
            target=self._work,
            name="music-generation-queue",
            daemon=True,
        )
        self._worker.start()

    def enqueue(self, payload: dict, summary: dict, expected_seconds: float) -> dict:
        job = GenerationJob(
            id=uuid.uuid4().hex,
            payload=dict(payload),
            summary=dict(summary),
            expected_seconds=max(float(expected_seconds), 1.0),
            created_at=self._clock(),
        )
        with self._condition:
            self._jobs.append(job)
            self._condition.notify_all()
        return self._job_snapshot(job, self._clock())

    def snapshot(self) -> list[dict]:
        now = self._clock()
        with self._condition:
            self._jobs = [
                job for job in self._jobs
                if not (
                    job.status == "complete"
                    and job.completed_at is not None
                    and now - job.completed_at >= self._completed_hold_seconds
                )
            ]
            queued_position = 0
            result = []
            for job in self._jobs:
                snapshot = self._job_snapshot(job, now)
                if job.status == "queued":
                    queued_position += 1
                    snapshot["queue_position"] = queued_position
                result.append(snapshot)
            return result

    def move(self, job_id: str, direction: int) -> list[dict]:
        if direction not in (-1, 1):
            raise ValueError("direction must be -1 or 1")
        with self._condition:
            queued_indexes = [
                index for index, job in enumerate(self._jobs)
                if job.status == "queued"
            ]
            current = next(
                (position for position, index in enumerate(queued_indexes)
                 if self._jobs[index].id == job_id),
                None,
            )
            target = None if current is None else current + direction
            if target is not None and 0 <= target < len(queued_indexes):
                first = queued_indexes[current]
                second = queued_indexes[target]
                self._jobs[first], self._jobs[second] = self._jobs[second], self._jobs[first]
        return self.snapshot()

    def remove(self, job_id: str) -> list[dict]:
        with self._condition:
            self._jobs = [
                job for job in self._jobs
                if job.id != job_id or job.status == "running"
            ]
        return self.snapshot()

    def stop(self) -> None:
        """Stop an idle test queue. Active model work is never interrupted here."""
        with self._condition:
            self._stopping = True
            self._condition.notify_all()
        self._worker.join(timeout=1)

    def _job_snapshot(self, job: GenerationJob, now: float) -> dict:
        progress = 0.0
        elapsed = 0.0
        if job.started_at is not None:
            elapsed = max(0.0, now - job.started_at)
        if job.status == "running":
            progress = min(95.0, 90.0 * elapsed / job.expected_seconds)
        elif job.status == "complete":
            progress = 100.0
        return {
            "id": job.id,
            "status": job.status,
            "progress": round(progress, 1),
            "elapsed_seconds": round(elapsed, 1),
            "expected_seconds": round(job.expected_seconds, 1),
            "output_path": job.output_path,
            "error": job.error,
            **job.summary,
        }

    def _work(self) -> None:
        while True:
            with self._condition:
                job = next(
                    (candidate for candidate in self._jobs if candidate.status == "queued"),
                    None,
                )
                while job is None and not self._stopping:
                    self._condition.wait()
                    job = next(
                        (candidate for candidate in self._jobs
                         if candidate.status == "queued"),
                        None,
                    )
                if self._stopping:
                    return
                job.status = "running"
                job.started_at = self._clock()

            try:
                track = self._run(job.payload)
                output_path = Path(getattr(track, "path", ""))
                if not output_path.is_file():
                    raise RuntimeError(
                        f"Generation returned without writing its WAV: {output_path}"
                    )
            except Exception as exc:
                with self._condition:
                    job.status = "failed"
                    job.error = str(exc)
                    if isinstance(exc, GenerationFailure):
                        job.summary.update(exc.summary_updates)
                    job.completed_at = self._clock()
                    self._condition.notify_all()
            else:
                with self._condition:
                    job.status = "complete"
                    job.output_path = str(output_path)
                    if hasattr(track, "seed"):
                        job.summary["seed"] = track.seed
                    if hasattr(track, "duration"):
                        job.summary["delivered_duration"] = track.duration
                    job.completed_at = self._clock()
                    self._condition.notify_all()
