"""Virtual operator: a slow, barely perceptible camera drift cut out of the source frame instead of a fixed crop.

The crop breathes between ZOOM_LO and ZOOM_HI (push-in, pull-out) and wanders a few pixels off centre, all on waypoints joined by
cosine easing, so position and speed are continuous and the velocity is zero at every turn. Nothing reacts to the picture: reacting to
motion made the first version twitch. Each frame is resized once to the largest scale the path needs and then warped to the
output in one Lanczos affine step at sub-pixel precision, so there is no rounding jitter, unlike `zoompan` or an integer crop.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

from . import ffio, meta, plan as planmod

ZOOM_LO = 1.05
ZOOM_HI = 1.11
SHIFT_PX = 10.0
ZOOM_SEGMENT = (5.0, 9.0)
SHIFT_SEGMENT = (6.0, 10.0)


def _waypoints(rng: np.random.Generator, duration: float, segment: tuple[float, float], lo: float, hi: float, dims: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Times and values of the turning points, from before the start to after the end."""
    times = [-rng.uniform(0, segment[0])]
    while times[-1] < duration + segment[1]:
        times.append(times[-1] + rng.uniform(*segment))
    return np.asarray(times), rng.uniform(lo, hi, (len(times), dims))


def _eased(t: np.ndarray, times: np.ndarray, vals: np.ndarray) -> np.ndarray:
    """Cosine interpolation through the waypoints: C1 everywhere, zero velocity at each one."""
    i = np.clip(np.searchsorted(times, t, side="right") - 1, 0, len(times) - 2)
    u = (t - times[i]) / (times[i + 1] - times[i])
    e = 0.5 - 0.5 * np.cos(np.pi * np.clip(u, 0, 1))
    return vals[i] + (vals[i + 1] - vals[i]) * e[:, None]


def camera_path(duration: float, fps: float, rng: np.random.Generator):
    """(zoom, dx, dy, waypoints) per output frame; dx/dy are the shift of the crop centre in output pixels."""
    n = max(1, int(round(duration * fps)))
    t = np.arange(n) / fps
    zt, zv = _waypoints(rng, duration, ZOOM_SEGMENT, np.log(ZOOM_LO), np.log(ZOOM_HI))
    zoom = np.exp(_eased(t, zt, zv)[:, 0])
    st, sv = _waypoints(rng, duration, SHIFT_SEGMENT, -SHIFT_PX, SHIFT_PX, dims=2)
    d = _eased(t, st, sv)
    moves = [{"t": round(float(a), 1), "zoom": round(float(np.exp(b[0])), 3)} for a, b in zip(zt, zv) if 0 <= a <= duration]
    return zoom, d[:, 0], d[:, 1], moves


def warp(mid: np.ndarray, src_size: tuple[int, int], zoom: float, dx: float, dy: float, out_w: int, out_h: int) -> np.ndarray:
    """One output frame from `mid`, the source frame resized once to the largest scale the path needs.

    The window is `zoom` times smaller than the source frame, centred and then shifted by (dx, dy) output pixels; coordinates are
    followed in the pixel-edge convention so that a zoom of 1 reproduces the frame exactly.
    """
    w, h = src_size
    mh, mw = mid.shape[:2]
    sx, sy = mw / w, mh / h
    s = out_w / (w / zoom)
    x0 = w / 2 - (out_w / s) / 2 + dx / s
    y0 = h / 2 - (out_h / s) / 2 + dy / s
    a, b = s / sx, s / sy
    m = np.float32([[a, 0, 0.5 * a - x0 * s - 0.5], [0, b, 0.5 * b - y0 * s - 0.5]])
    return cv2.warpAffine(mid, m, (out_w, out_h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)


def render(src: str | Path, dst: str | Path, seed: int, keep_tags: dict | None = None, index: int = 0) -> dict:
    """Render one operator variant. Tone and pitch are drawn like the `soft` preset. `dst` appears only when the encode succeeded."""
    src, dst = Path(src), Path(dst)
    info = ffio.probe(src)
    if info.duration <= 0:
        raise ffio.FFmpegError(f"{src}: cannot read the duration")
    out_w, out_h = planmod.output_size(info)
    plan = planmod.draw(info, "soft", seed, has_audio_signal=info.has_audio, index=index)
    w, h = info.display_size
    fps = plan.fps
    rng = np.random.default_rng(seed)
    zoom, dx, dy, moves = camera_path(info.duration / plan.speed, fps, rng)
    s_max = out_w / (w / zoom.max())
    mid_w, mid_h = int(np.ceil(w * s_max)) // 2 * 2, int(np.ceil(h * s_max)) // 2 * 2
    part = dst.with_name(dst.name + ".part")
    dec = [ffio.FFMPEG, "-v", "error", "-nostdin", "-threads", "2", "-i", str(src), "-an",
           "-vf", ((planmod.HDR_TONEMAP + ",") if info.is_hdr else "") + f"setpts=PTS/{plan.speed:.5f},fps={fps:g},format=rgb24", "-f", "rawvideo", "-"]
    enc = [ffio.FFMPEG, "-v", "error", "-y", "-threads", "2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{out_w}x{out_h}", "-r", f"{fps:g}", "-i", "-",
           "-i", str(src), "-map", "0:v:0", "-map", "1:a:0?", "-map_metadata", "-1", "-map_chapters", "-1",
           "-vf", f"eq=brightness={plan.brightness:.4f}:contrast={plan.contrast:.4f}:gamma={plan.gamma:.4f},scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
           "-shortest", *planmod.codec_options(plan, keep_tags), "-f", "mp4", str(part)]
    fb = w * h * 3
    n = 0
    eof = False
    try:
        with tempfile.TemporaryFile() as dec_log, tempfile.TemporaryFile() as enc_log:
            pd = subprocess.Popen(dec, stdout=subprocess.PIPE, stderr=dec_log)
            pe = subprocess.Popen(enc, stdin=subprocess.PIPE, stderr=enc_log)
            finished = False
            try:
                while n < len(zoom):
                    raw = pd.stdout.read(fb)
                    if len(raw) < fb:
                        eof = True
                        break
                    frame = np.frombuffer(raw, np.uint8).reshape(h, w, 3)
                    mid = cv2.resize(frame, (mid_w, mid_h), interpolation=cv2.INTER_AREA if s_max < 1 else cv2.INTER_CUBIC)
                    pe.stdin.write(warp(mid, (w, h), float(zoom[n]), float(dx[n]), float(dy[n]), out_w, out_h).tobytes())
                    n += 1
                finished = True
            except BrokenPipeError:
                finished = True
            finally:
                if not finished:
                    pd.kill()
                    pe.kill()
                try:
                    pe.stdin.close()
                except BrokenPipeError:
                    pass
                pd.stdout.close()
                dec_rc, enc_rc = pd.wait(), pe.wait()
                dec_log.seek(0)
                enc_log.seek(0)
                dec_err, enc_err = dec_log.read(), enc_log.read()
        if eof and dec_rc != 0:
            raise ffio.FFmpegError(f"decode failed: {dec_err.decode(errors='replace')[-600:]}")
        if enc_rc != 0:
            raise ffio.FFmpegError(f"encode failed: {enc_err.decode(errors='replace')[-600:]}")
        if n == 0:
            raise ffio.FFmpegError(f"{src}: no frames were decoded")
        os.replace(part, dst)
    finally:
        part.unlink(missing_ok=True)
    return {"file": dst.name, "frames": n, "zoom": [round(float(zoom.min()), 3), round(float(zoom.max()), 3)],
            "shift_px": [round(float(np.abs(dx).max()), 1), round(float(np.abs(dy).max()), 1)],
            "max_zoom_rate": round(float(np.abs(np.diff(np.log(zoom))).max(initial=0.0) * fps), 4),
            "upscale_at_zmax": round(max(out_w / (w / zoom.max()), out_h / (h / zoom.max())), 3), "moves": moves, "plan": plan.describe()}


def make_variants(src: Path, out_dir: Path, count: int, seed: int = 1, log=print) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    labels = ffio.ai_labels(ffio.probe(src))
    ai_box = meta.c2pa_ai_box(src)
    ffio.log_ai_labels([*labels, *(["C2PA"] if ai_box else [])], log)
    done = []
    for i in range(count):
        dst = out_dir / f"{src.stem}_operator_{i + 1:02d}.mp4"
        r = render(src, dst, seed * 1000 + i, keep_tags=labels or None, index=i)
        if ai_box:
            meta.insert_boxes(dst, [], [ai_box])
        r["kept_labels"] = sorted(labels) + (["c2pa"] if ai_box else [])
        done.append(r)
        log(f"  [{i + 1}/{count}] {dst.name}  zoom {r['zoom'][0]}-{r['zoom'][1]}, pan up to {max(r['shift_px'])} px, zoom rate up to {r['max_zoom_rate']}/s")
    return done
