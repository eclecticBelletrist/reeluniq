"""Hot folder: drop a video into DIR, variants appear in DIR/variants/<file name>/."""

from __future__ import annotations

import time
from pathlib import Path

from .i18n import t
from .jobs import Job, JobQueue

VIDEO_EXT = {".mp4", ".mov", ".m4v"}
OUT_NAME = "variants"
STABLE_SECONDS = 3.0


def _candidates(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXT and not p.name.startswith("."))


def watch(root: Path, count: int, mode: str, poll: float = 2.0, once: bool = False, log=print,
          out: Path | None = None, lang: str = "en") -> None:
    """Results go to `out` (default: DIR/variants), one folder per video."""
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"{root}: no such folder")
    out_root = out.resolve() if out else root / OUT_NAME
    out_root.mkdir(parents=True, exist_ok=True)
    queue = JobQueue(on_done=lambda j: log(t(lang, "job", name=j.source.name, state=t(lang, f"state_{j.state}"), n=len(j.files)) + (f", {j.error}" if j.error else "")), echo=log)
    seen: dict[Path, tuple[int, float]] = {}
    submitted: set[Path] = set()
    log(t(lang, "watching", root=root, out=out_root, mode=mode, count=count))
    while True:
        now = time.time()
        waiting = 0
        for p in _candidates(root):
            if p in submitted or (out_root / p.name).exists():
                continue
            waiting += 1
            try:
                size = p.stat().st_size
            except FileNotFoundError:
                waiting -= 1
                continue
            prev = seen.get(p)
            if prev is None or prev[0] != size:
                seen[p] = (size, now)
            elif now - prev[1] >= STABLE_SECONDS:
                waiting -= 1
                if size > 0:
                    submitted.add(p)
                    log(t(lang, "queued", name=p.name))
                    queue.submit(Job(id=p.name, source=p, out_dir=out_root / p.name, count=count, mode=mode))
        if once and not waiting and queue.pending() == 0:
            return
        time.sleep(poll)
