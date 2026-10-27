"""One entry point for every mode: `make_variants(src, out_dir, count, mode)`."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import ffio, meta, operator, plan as planmod

MODES = ("light", "dust", "operator", "meta")


def _encode_variants(src: Path, out_dir: Path, count: int, preset: str, seed: int, log) -> list[dict]:
    """`light` and `dust`: one re-encode per variant with drawn crop, speed, fps, pitch and tone."""
    info = ffio.probe(src)
    labels = ffio.ai_labels(info)
    if labels:
        log(f"! source carries an AI-origin label ({', '.join(labels)}): it stays in every result")
    done = []
    for i in range(count):
        plan = planmod.draw(info, preset, seed * 1000 + i, has_audio_signal=info.has_audio, index=i)
        dst = out_dir / f"{src.stem}_{preset}_{i + 1:02d}.mp4"
        proc = subprocess.run(planmod.ffmpeg_command(info, plan, str(src), str(dst), labels or None), capture_output=True)
        if proc.returncode != 0:
            raise ffio.FFmpegError(proc.stderr.decode(errors="replace")[-600:])
        done.append({"file": dst.name, "plan": plan.describe()})
        log(f"  [{i + 1}/{count}] {dst.name}  zoom {plan.zoom:.3f}  speed x{plan.speed:.3f}  fps {plan.fps:g}")
    return done


def make_variants(src: Path, out_dir: Path, count: int, mode: str, seed: int = 1, log=print) -> list[dict]:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; choose from {', '.join(MODES)}")
    out_dir.mkdir(parents=True, exist_ok=True)
    if mode == "meta":
        done = meta.make_variants(src, out_dir, count, seed, log=log)
    elif mode == "operator":
        done = operator.make_variants(src, out_dir, count, seed, log=log)
    else:
        done = _encode_variants(src, out_dir, count, mode, seed, log)
    (out_dir / "report.json").write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    return done
