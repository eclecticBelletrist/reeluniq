"""One-at-a-time job queue: encoding saturates the machine, so variants are made strictly one job after another."""

from __future__ import annotations

import queue
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from .make import make_variants


@dataclass
class Job:
    id: str
    source: Path
    out_dir: Path
    count: int
    mode: str
    state: str = "queued"          # queued | running | done | failed
    log: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    error: str | None = None
    created: float = field(default_factory=time.time)

    def public(self) -> dict:
        return {
            "id": self.id, "name": self.source.name, "state": self.state, "count": self.count,
            "mode": self.mode, "files": self.files, "error": self.error, "log": self.log[-12:],
        }


class JobQueue:
    def __init__(self, on_done=None, echo=None):
        """`on_done(job)` runs after every job; `echo(line)` also receives each log line as it is written."""
        self._q: queue.Queue[Job] = queue.Queue()
        self.jobs: dict[str, Job] = {}
        self._on_done = on_done
        self._echo = echo
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def submit(self, job: Job) -> Job:
        self.jobs[job.id] = job
        self._q.put(job)
        return job

    def pending(self) -> int:
        return sum(j.state in ("queued", "running") for j in self.jobs.values())

    def prune(self, max_age: float) -> None:
        """Forget finished jobs older than `max_age` seconds."""
        now = time.time()
        for jid in [i for i, j in self.jobs.items() if j.state in ("done", "failed") and now - j.created > max_age]:
            del self.jobs[jid]

    def _log(self, job: Job, line: str) -> None:
        job.log.append(line)
        if self._echo:
            self._echo(line)

    def _loop(self) -> None:
        while True:
            job = self._q.get()
            job.state = "running"
            try:
                done = make_variants(job.source, job.out_dir, job.count, job.mode, log=lambda line: self._log(job, line))
                job.files = [d["file"] for d in done]
                job.state = "done" if job.files else "failed"
                if not job.files:
                    job.error = "no variant was produced"
            except Exception as e:  # keep the worker alive whatever one file does
                job.state, job.error = "failed", f"{type(e).__name__}: {e}"
                job.log.append(traceback.format_exc(limit=3))
            if self._on_done:
                try:
                    self._on_done(job)
                except Exception:   # a failing callback must not take the worker down with it
                    self._log(job, traceback.format_exc(limit=3))
