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
    return name       # not found: the first call fails and the command line reports it


FFMPEG, FFPROBE = _find("ffmpeg"), _find("ffprobe")

# HLG/PQ -> SDR BT.709. `mobius` leaves values below its knee unchanged (SDR content round-trips to within a few
# levels, see tests) and rolls off only real HDR highlights; `hable` darkened the whole picture by about a quarter.
HDR_TONEMAP = (
    "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
    "tonemap=mobius:param=0.7:desat=0,zscale=t=bt709:m=bt709:r=tv"
)


AI_LABEL_KEYS = ("aigc", "c2pa")


class FFmpegError(RuntimeError):
    pass


@dataclass
class MediaInfo:
    path: Path
    width: int
    height: int
    rotation: int
    fps: float
    duration: float
    nb_frames: int | None
    codec: str
    pix_fmt: str
    color_transfer: str | None
    color_space: str | None
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


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise FFmpegError(f"{cmd[0]} failed: {proc.stderr.decode(errors='replace')[-800:]}")
    return proc


def probe(path: str | Path) -> MediaInfo:
    path = Path(path)
    out = _run([FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)])
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
    nb = video.get("nb_frames")
    return MediaInfo(
        path=path,
        width=int(video["width"]),
        height=int(video["height"]),
        rotation=rotation,
        fps=fps,
        duration=duration,
        nb_frames=int(nb) if nb and nb.isdigit() else None,
        codec=video["codec_name"],
        pix_fmt=video.get("pix_fmt", ""),
        color_transfer=video.get("color_transfer"),
        color_space=video.get("color_space"),
        has_audio=audio is not None,
        audio_rate=int(audio["sample_rate"]) if audio else None,
        format_tags=data["format"].get("tags", {}),
    )
