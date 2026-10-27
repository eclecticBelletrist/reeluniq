"""Meta mode: new bytes around the same picture and sound, no re-encoding.

What changes per file, all of it legal for players and uploaders:
  * every tag, XMP packet (Premiere document ids), timecode track and chapter is dropped;
  * container structure is drawn at random: major brand, track timescale (a multiple of the native one, so timing stays
    exact), moov at the front or the back, bitrate box on or off, handler names, creation time;
  * H.264: the x264 settings SEI is dropped and a user-data SEI with a random uuid and text is inserted
    (HEVC has no such filter in ffmpeg, so HEVC files only get the container changes);
  * a few `free` and `uuid` boxes at the start and the end of the file (a handful of KB at most; whole boxes, never raw bytes);
  * neutral output name and modification time.
Labels that say the content is AI-generated stay: the AIGC tag is written back, and a C2PA manifest that declares synthetic
media is appended unchanged. Nothing here switches that off.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import time
import uuid as uuidlib
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from . import ffio

C2PA_UUID = bytes.fromhex("d8fec3d61b0e483c92975828877ec481")
C2PA_AI_MARKERS = (b"algorithmicmedia", b"compositesynthetic")   # IPTC digitalSourceType values for generated media
CONTAINERS = (b"moov", b"trak", b"mdia", b"minf", b"stbl")
HANDLERS_V = ("VideoHandler", "Video Media Handler", "Video", "ISO Media video")
HANDLERS_A = ("SoundHandler", "Sound Media Handler", "Audio", "ISO Media audio")
BRANDS = ("isom", "mp42", "iso2")
TS_MULTIPLES = (1, 2, 3, 4, 5, 8)
MAX_EXTRA_BYTES = 8192


@dataclass
class MetaPlan:
    seed: int
    brand: str
    timescale: int
    faststart: bool
    btrt: bool
    creation_time: str
    handler_v: str
    handler_a: str
    drop_x264_sei: bool
    sei: str | None                      # "uuid+text" for h264_metadata, None when the codec has no such filter
    front: list[bytes] = field(default_factory=list, repr=False)
    back: list[bytes] = field(default_factory=list, repr=False)
    name: str = ""
    mtime: float = 0.0
    keep_c2pa: bool = False

    def describe(self) -> dict:
        d = asdict(self)
        d.pop("front"), d.pop("back")
        d["front_boxes"] = [b[4:8].decode("latin1") + str(len(b)) for b in self.front]
        d["back_boxes"] = [b[4:8].decode("latin1") + str(len(b)) for b in self.back]
        return d


def box(typ: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), typ) + payload


def top_level(path: Path) -> list[tuple[bytes, int, int]]:
    """[(type, offset, size)] of the top-level boxes."""
    out, n = [], path.stat().st_size
    with open(path, "rb") as f:
        pos = 0
        while pos + 8 <= n:
            f.seek(pos)
            size, typ = struct.unpack(">I4s", f.read(8))
            if size == 1:
                size = struct.unpack(">Q", f.read(8))[0]
            elif size == 0:
                size = n - pos
            if size < 8 or pos + size > n:
                raise ffio.FFmpegError(f"{path}: broken box {typ!r} at {pos}")
            out.append((typ, pos, size))
            pos += size
    return out


def _patch_offsets(moov: bytearray, delta: int) -> None:
    """Add `delta` to every chunk offset (stco/co64) inside a moov box held in memory."""
    def walk(start: int, end: int) -> None:
        pos = start
        while pos + 8 <= end:
            size, typ = struct.unpack_from(">I4s", moov, pos)
            if size < 8:
                return
            body = pos + 8
            if typ in CONTAINERS:
                walk(body, pos + size)
            elif typ in (b"stco", b"co64"):
                count = struct.unpack_from(">I", moov, body + 4)[0]
                width, fmt = (4, ">I") if typ == b"stco" else (8, ">Q")
                for i in range(count):
                    at = body + 8 + i * width
                    struct.pack_into(fmt, moov, at, struct.unpack_from(fmt, moov, at)[0] + delta)
            pos += size

    walk(8, len(moov))


def insert_boxes(path: Path, front: list[bytes], back: list[bytes]) -> None:
    """Put whole boxes right after `ftyp` and at the very end; chunk offsets are shifted to match."""
    if not front and not back:
        return
    boxes = top_level(path)
    if boxes[0][0] != b"ftyp":
        raise ffio.FFmpegError("ftyp is not the first box")
    ftyp_end = boxes[0][1] + boxes[0][2]
    delta = sum(len(b) for b in front)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(path, "rb") as src, open(tmp, "wb") as dst:
            dst.write(src.read(ftyp_end))
            for b in front:
                dst.write(b)
            shutil.copyfileobj(src, dst, 1 << 20)
            for b in back:
                dst.write(b)
        if delta:
            typ, off, size = next(b for b in top_level(tmp) if b[0] == b"moov")
            with open(tmp, "r+b") as f:
                f.seek(off)
                moov = bytearray(f.read(size))
                _patch_offsets(moov, delta)
                f.seek(off)
                f.write(moov)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def c2pa_ai_box(path: Path) -> bytes | None:
    """The C2PA manifest box if it declares AI-generated media, else None (real-footage manifests are stripped like any metadata)."""
    with open(path, "rb") as f:
        for typ, off, size in top_level(path):
            if typ != b"uuid":
                continue
            f.seek(off + 8)
            if f.read(16) != C2PA_UUID:
                continue
            f.seek(off)
            data = f.read(size)
            if any(m in data.lower() for m in C2PA_AI_MARKERS):
                return data
    return None


def _stream(path: Path) -> dict:
    out = ffio._run([ffio.FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,time_base",
                     "-of", "json", str(path)])
    return json.loads(out.stdout)["streams"][0]


def _has_x264_sei(path: Path) -> bool:
    with open(path, "rb") as f:
        return b"x264 - core" in f.read(4 << 20)


def _junk_box(rng, kind: str, lo: int, hi: int) -> bytes:
    body = rng.bytes(int(rng.integers(lo, hi)))
    return box(b"uuid", rng.bytes(16) + body) if kind == "uuid" else box(b"free", body)


def draw(src: Path, seed: int, now: float | None = None) -> tuple[MetaPlan, dict]:
    rng = np.random.default_rng(seed)
    st = _stream(src)
    native = int(st["time_base"].split("/")[1])
    now = time.time() if now is None else now
    created = now - float(rng.uniform(300, 5 * 3600))
    h264 = st["codec_name"] == "h264"
    plan = MetaPlan(
        seed=seed,
        brand=str(rng.choice(BRANDS)),
        timescale=native * int(rng.choice(TS_MULTIPLES)),
        faststart=bool(rng.integers(2)),
        btrt=bool(rng.integers(2)),
        creation_time=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime(created)),
        handler_v=str(rng.choice(HANDLERS_V)),
        handler_a=str(rng.choice(HANDLERS_A)),
        drop_x264_sei=h264 and _has_x264_sei(src),
        sei=f"{uuidlib.UUID(bytes=rng.bytes(16))}+{rng.bytes(int(rng.integers(6, 20))).hex()}" if h264 else None,
        name=f"clip-{rng.bytes(3).hex()}.mp4",
        mtime=created,
    )
    for _ in range(int(rng.integers(1, 3))):
        plan.front.append(_junk_box(rng, "free" if rng.integers(2) else "uuid", 24, 1500))
    for _ in range(int(rng.integers(1, 3))):
        plan.back.append(_junk_box(rng, "free", 16, 1200))
    plan.back.append(_junk_box(rng, "uuid", 32, 600))
    while sum(len(b) for b in plan.front + plan.back) > MAX_EXTRA_BYTES:
        (plan.back if len(plan.back) > 1 else plan.front).pop()
    plan.keep_c2pa = c2pa_ai_box(src) is not None
    return plan, st


def ffmpeg_command(plan: MetaPlan, st: dict, src: Path, dst: Path, keep_tags: dict[str, str]) -> list[str]:
    cmd = [ffio.FFMPEG, "-v", "error", "-y", "-threads", "2", "-i", str(src),
           "-map", "0:v:0", "-map", "0:a:0?", "-map_metadata", "-1", "-map_metadata:s:v:0", "-1", "-map_metadata:s:a:0", "-1",
           "-map_chapters", "-1", "-fflags", "+bitexact", "-c", "copy"]   # bitexact: no Lavf version string; stream metadata: no codec string
    if st["codec_name"] == "h264":
        bsf = []
        if plan.drop_x264_sei:
            bsf.append("filter_units=remove_types=6")
        bsf.append(f"h264_metadata=sei_user_data={plan.sei}")
        cmd += ["-bsf:v", ",".join(bsf)]
    elif st["codec_name"] == "hevc":
        cmd += ["-tag:v", "hvc1"]
    movflags = ("+faststart" if plan.faststart else "") + ("+use_metadata_tags" if keep_tags else "")
    cmd += ["-video_track_timescale", str(plan.timescale), "-brand", plan.brand, "-write_btrt", str(int(plan.btrt)),
            "-write_tmcd", "0", "-metadata", f"creation_time={plan.creation_time}",
            "-metadata:s:v:0", f"handler_name={plan.handler_v}", "-metadata:s:a:0", f"handler_name={plan.handler_a}"]
    for k, v in keep_tags.items():
        cmd += ["-metadata", f"{k}={v}"]
    if movflags:
        cmd += ["-movflags", movflags]
    return cmd + [str(dst)]


def stream_md5(path: Path, kind: str) -> str | None:
    """md5 over decoded frames of the first video or audio stream (`v`/`a`); None when ffmpeg cannot decode it."""
    proc = subprocess.run([ffio.FFMPEG, "-v", "error", "-threads", "2", "-i", str(path), "-map", f"0:{kind}:0", "-f", "framemd5", "-"],
                          capture_output=True)
    if proc.returncode != 0:
        return None
    rows = [ln.split(",")[-1].strip() for ln in proc.stdout.decode().splitlines() if ln and not ln.startswith("#")]
    return hashlib.md5("\n".join(rows).encode()).hexdigest()


def make_variants(src: Path, out_dir: Path, count: int, seed: int = 1, log=print, verify: bool = True) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    info = ffio.probe(src)
    labels = ffio.ai_labels(info)
    ai_box = c2pa_ai_box(src)
    if labels or ai_box:
        log(f"! source carries an AI-origin label ({', '.join(labels) or 'C2PA'}): it stays in every result")
    # a source without audio has nothing to compare there: "" on both sides
    ref = (stream_md5(src, "v"), stream_md5(src, "a") if info.has_audio else "") if verify else None
    done = []
    for i in range(count):
        plan, st = draw(src, seed * 1000 + i)
        dst = out_dir / plan.name
        proc = subprocess.run(ffmpeg_command(plan, st, src, dst, labels), capture_output=True)
        if proc.returncode != 0:
            raise ffio.FFmpegError(proc.stderr.decode(errors="replace")[-600:])
        back = plan.back + ([ai_box] if ai_box else [])
        insert_boxes(dst, plan.front, back)
        os.utime(dst, (plan.mtime, plan.mtime))
        same = None
        if ref:
            got = (stream_md5(dst, "v"), stream_md5(dst, "a") if info.has_audio else "")
            same = None not in got and got == ref
        done.append({"file": dst.name, "plan": plan.describe(), "kept_labels": sorted(labels) + (["c2pa"] if ai_box else []),
                     "picture_and_sound_unchanged": same})
        log(f"  [{i + 1}/{count}] {dst.name}  brand {plan.brand}  ts {plan.timescale}  {'faststart' if plan.faststart else 'moov at the end'}"
            f"{'  +SEI' if plan.sei else ''}  picture and sound unchanged: {'yes' if same else 'NO' if same is False else '-'}")
    return done
