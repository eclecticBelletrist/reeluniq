"""Hot folder: drop a video into DIR, variants appear in DIR/variants/<file name>/."""

from __future__ import annotations

import time
from pathlib import Path

from .jobs import Job, JobQueue

VIDEO_EXT = {".mp4", ".mov", ".m4v"}
OUT_NAME = "variants"
STABLE_SECONDS = 3.0   # a file still being copied/AirDropped keeps changing its size


def _candidates(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXT and not p.name.startswith("."))


def watch(root: Path, count: int, mode: str, poll: float = 2.0, once: bool = False, log=print) -> None:
    root = root.resolve()
    out_root = root / OUT_NAME
    out_root.mkdir(exist_ok=True)
    queue = JobQueue(on_done=lambda j: log(f"{j.source.name}: {j.state} ({len(j.files)} file(s))" + (f", {j.error}" if j.error else "")), echo=log)
    seen: dict[Path, tuple[int, float]] = {}   # path -> (size, time the size last changed)
    submitted: set[Path] = set()
    log(f"watching {root}  (results: {out_root}, mode={mode}, n={count}); Ctrl+C to stop")
    while True:
        now = time.time()
        waiting = 0
        for p in _candidates(root):
            if p in submitted or (out_root / p.name).exists():
                continue
            waiting += 1
            size = p.stat().st_size
            prev = seen.get(p)
            if prev is None or prev[0] != size:
                seen[p] = (size, now)
            elif now - prev[1] >= STABLE_SECONDS and size > 0:
                submitted.add(p)
                waiting -= 1
                log(f"queued: {p.name}")
                queue.submit(Job(id=p.name, source=p, out_dir=out_root / p.name, count=count, mode=mode))
        if once and not waiting and queue.pending() == 0:
            return
        time.sleep(poll)
