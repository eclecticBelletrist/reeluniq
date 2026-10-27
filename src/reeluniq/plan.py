"""Variant plans: draw random parameters per preset and turn them into an ffmpeg command.

Presets: `light` (small crop, speed, fps and pitch nudges), `dust` (light plus a few invisible pixel-level touches) and `soft`
(a slightly deeper crop; the operator mode draws its tone, speed and encode settings from it).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from . import ffio
from .ffio import HDR_TONEMAP, MediaInfo


@dataclass
class Plan:
    preset: str
    seed: int
    out_w: int
    out_h: int
    fps: float
    zoom: float = 1.0          # >1 crops in (punch-in)
    pan_x: float = 0.5         # 0..1 position of the crop window
    pan_y: float = 0.5
    rotate_deg: float = 0.0
    speed: float = 1.0         # >1 faster
    pitch: float = 1.0         # audio pitch factor with duration preserved; 1.0 = off
    brightness: float = 0.0
    contrast: float = 1.0
    gamma: float = 1.0
    crf: int = 18
    dust: float = 0.0          # 1.0 = the "1 %" stack: noise, sub-pixel jitter, tiny rotation, chroma shift, light sharpening

    def describe(self) -> dict:
        d = asdict(self)
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}


def _even(x: float) -> int:
    return max(2, int(x) // 2 * 2)


def min_zoom_for_rotation(width: int, height: int, deg: float) -> float:
    """Smallest zoom that hides the black corners after rotating by `deg` (same-size canvas)."""
    t = math.radians(abs(deg))
    ar = max(width / height, height / width)
    return math.cos(t) + ar * math.sin(t)


def output_size(info: MediaInfo, max_short: int = 1080) -> tuple[int, int]:
    w, h = info.display_size
    s = min(1.0, max_short / min(w, h))
    return _even(w * s), _even(h * s)


def draw(info: MediaInfo, preset: str, seed: int, has_audio_signal: bool, index: int = 0) -> Plan:
    rng = np.random.default_rng(seed)
    out_w, out_h = output_size(info)
    fps = info.fps if info.fps > 0 else 30.0
    plan = Plan(preset=preset, seed=seed, out_w=out_w, out_h=out_h, fps=fps)
    plan.pan_x, plan.pan_y = (float(v) for v in rng.uniform(0.1, 0.9, 2))
    plan.brightness = float(np.clip(rng.normal(0, 0.006), -0.012, 0.012))
    plan.contrast = float(1 + np.clip(rng.normal(0, 0.008), -0.016, 0.016))
    plan.gamma = float(1 + np.clip(rng.normal(0, 0.01), -0.02, 0.02))
    pitch_range = (0.01, 0.02)
    if preset in ("light", "dust"):
        # a small crop is enough to move a frame hash
        plan.zoom = float(rng.uniform(1.04, 1.06))
        plan.speed = float(rng.uniform(1.005, 1.015))
        plan.fps = float(max(15, round(fps) + int(rng.choice([-1, 1]))))
        pitch_range = (0.008, 0.012)
    elif preset == "soft":
        plan.zoom = float(rng.uniform(1.07, 1.12))
    else:
        raise ValueError(f"unknown preset {preset!r}")
    if has_audio_signal:
        plan.pitch = float((1 if index % 2 == 0 else -1) * rng.uniform(*pitch_range) + 1)
    if preset == "dust":
        plan.dust = 1.0
        plan.rotate_deg = float(rng.choice([-1, 1]) * rng.uniform(0.1, 0.3))
        plan.zoom = max(plan.zoom, min_zoom_for_rotation(out_w, out_h, plan.rotate_deg) + 0.01)   # the crop hides the rotated corners
    return plan


def video_filter(info: MediaInfo, plan: Plan) -> str:
    """The ffmpeg -vf chain for one plan."""
    w, h = info.display_size
    chain: list[str] = []
    if info.is_hdr:
        chain.append(HDR_TONEMAP)
    if abs(plan.rotate_deg) > 1e-6:
        chain.append(f"rotate={math.radians(plan.rotate_deg):.6f}:ow=iw:oh=ih:c=black")
    cw, ch = _even(w / plan.zoom), _even(h / plan.zoom)
    x, y = int((w - cw) * plan.pan_x) // 2 * 2, int((h - ch) * plan.pan_y) // 2 * 2
    if plan.dust:
        # +-1 source pixel of jitter per frame, kept inside the frame; the sequence depends on the plan's seed
        a, b = plan.seed % 1009 + 0.37, plan.seed % 997 + 0.71
        jx = f"floor(mod(abs(sin(n*12.9898+{a:.2f}))*43758.5453,1)*3)-1"
        jy = f"floor(mod(abs(sin(n*78.233+{b:.2f}))*43758.5453,1)*3)-1"
        chain.append(f"crop={cw}:{ch}:'min({w - cw},max(0,{x}+{jx}))':'min({h - ch},max(0,{y}+{jy}))'")
    else:
        chain.append(f"crop={cw}:{ch}:{x}:{y}")
    chain.append(f"scale={plan.out_w}:{plan.out_h}:flags=lanczos")
    if plan.speed != 1.0:
        chain.append(f"setpts=PTS/{plan.speed:.5f}")
    chain.append(f"fps={plan.fps:g}")
    chain.append(f"eq=brightness={plan.brightness:.4f}:contrast={plan.contrast:.4f}:gamma={plan.gamma:.4f}")
    if plan.dust:
        chain += ["noise=alls=3:allf=t+u", "chromashift=crh=1:cbh=-1", "unsharp=3:3:0.3:3:3:0"]
    chain.append("format=yuv420p")
    return ",".join(chain)


def audio_filter(plan: Plan, sample_rate: int = 48000) -> str | None:
    parts = []
    if abs(plan.pitch - 1.0) > 1e-6:
        # resample to the nominal rate FIRST: asetrate reinterprets samples at the given rate, so a 32 kHz
        # source would otherwise be shifted by 48/32 instead of by `pitch`
        parts.append(
            f"aresample={sample_rate},asetrate={sample_rate * plan.pitch:.1f},aresample={sample_rate},atempo={1 / plan.pitch:.6f}"
        )
    if plan.speed != 1.0:
        parts.append(f"atempo={plan.speed:.5f}")
    return ",".join(parts) or None


def codec_options(plan: Plan, keep_tags: dict[str, str] | None = None) -> list[str]:
    """Everything after the video filter that every re-encoding mode shares: x264, AAC, container flags.

    `keep_tags` are metadata entries deliberately carried over (the AI-origin labels).
    """
    opts = [
        "-c:v", "libx264", "-preset", "medium", "-crf", str(plan.crf), "-profile:v", "high",
        "-g", str(max(12, round(plan.fps * 2))), "-bf", "3", "-pix_fmt", "yuv420p",
        # -color_trc/-color_primaries are ignored by libx264 in current ffmpeg; the VUI must be set via x264 params
        "-x264-params", "colorprim=bt709:transfer=bt709:colormatrix=bt709:range=tv:info=0",
    ]
    af = audio_filter(plan)
    if af:
        opts += ["-af", af]
    opts += ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]
    movflags = "+faststart"
    if keep_tags:
        movflags += "+use_metadata_tags"
        for k, v in keep_tags.items():
            opts += ["-metadata", f"{k}={v}"]
    return opts + ["-movflags", movflags]


def ffmpeg_command(info: MediaInfo, plan: Plan, src: str, dst: str, keep_tags: dict[str, str] | None = None) -> list[str]:
    return [
        ffio.FFMPEG, "-v", "error", "-y", "-threads", "2", "-i", src,
        "-map", "0:v:0", "-map", "0:a:0?", "-map_metadata", "-1", "-map_chapters", "-1",
        "-vf", video_filter(info, plan), *codec_options(plan, keep_tags), dst,
    ]
