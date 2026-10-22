"""Where ffmpeg and ffprobe are, and a thin wrapper around ffprobe."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path


def _find(name: str) -> str:
    """The ffmpeg tool to run: REELUNIQ_<NAME> if set, else next to the program (release bundles only), else PATH."""
    exe = name + (".exe" if os.name == "nt" else "")
    bundled = str(Path(sys.executable).parent / exe) if getattr(sys, "frozen", False) else None
    for cand in (os.environ.get(f"REELUNIQ_{name.upper()}"), bundled, shutil.which(name)):
        if cand and Path(cand).is_file():
            return cand
    return name


FFMPEG, FFPROBE = _find("ffmpeg"), _find("ffprobe")

HDR_TONEMAP = (
    "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
    "tonemap=mobius:param=0.7:desat=0,zscale=t=bt709:m=bt709:r=tv"
)


AI_LABEL_KEYS = ("aigc", "c2pa")


class FFmpegError(RuntimeError):
    pass


@dataclass
class MediaInfo:
    width: int
    height: int
    rotation: int
    fps: float
    duration: float
    codec: str
    pix_fmt: str
    color_transfer: str | None
    has_audio: bool
    audio_rate: int | None
    format_tags: dict = field(default_factory=dict)

    @property
    def display_size(self) -> tuple[int, int]:
        """Size after applying rotation metadata (what a player shows)."""
        if self.rotation in (90, 270):
            return self.height, self.width
        return self.width, self.height

    @property
    def is_hdr(self) -> bool:
        return self.color_transfer in ("smpte2084", "arib-std-b67")


def ai_labels(info: MediaInfo) -> dict[str, str]:
    """Metadata entries that declare AI generation. They are written back into every result."""
    return {k: v for k, v in info.format_tags.items() if any(m in k.lower() for m in AI_LABEL_KEYS)}


def log_ai_labels(names, log) -> None:
    if names:
        log(f"! source carries an AI-origin label ({', '.join(names)}): it stays in every result")


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise FFmpegError(f"{cmd[0]} failed: {proc.stderr.decode(errors='replace')[-800:]}")
    return proc


def probe(path: str | Path) -> MediaInfo:
    path = Path(path)
    out = run([FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)])
    data = json.loads(out.stdout)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if video is None:
        raise FFmpegError(f"{path}: no video stream")
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)

    rotation = 0
    for side in video.get("side_data_list", []):
        if "rotation" in side:
            rotation = int(round(float(side["rotation"]))) % 360
    if "rotate" in video.get("tags", {}):
        rotation = int(video["tags"]["rotate"]) % 360

    fps = 0.0
    for rate in (video.get("avg_frame_rate"), video.get("r_frame_rate")):
        try:
            fps = float(Fraction(rate))
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if fps > 0:
            break
    duration = float(video.get("duration") or data["format"].get("duration") or 0.0)
    return MediaInfo(
        width=int(video["width"]),
        height=int(video["height"]),
        rotation=rotation,
        fps=fps,
        duration=duration,
        codec=video["codec_name"],
        pix_fmt=video.get("pix_fmt", ""),
        color_transfer=video.get("color_transfer"),
        has_audio=audio is not None,
        audio_rate=int(audio["sample_rate"]) if audio else None,
        format_tags=data["format"].get("tags", {}),
    )
