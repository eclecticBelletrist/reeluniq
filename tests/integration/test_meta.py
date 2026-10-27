import subprocess

import pytest

from reeluniq import ffio

pytestmark = pytest.mark.integration


def _h264_clip(tmp_path, audio=True):
    p = tmp_path / "m.mp4"
    cmd = [ffio.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=2"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-metadata", "title=secret", str(p)]
    subprocess.run(cmd, check=True)
    return p

def test_meta_changes_bytes_not_picture(tmp_path):
    import hashlib
    from reeluniq import meta

    src = _h264_clip(tmp_path)
    done = meta.make_variants(src, tmp_path / "out", 3, seed=5, log=lambda *_: None)
    files = [tmp_path / "out" / d["file"] for d in done]
    assert all(d["picture_and_sound_unchanged"] for d in done)
    digests = {hashlib.sha256(f.read_bytes()).hexdigest() for f in files} | {hashlib.sha256(src.read_bytes()).hexdigest()}
    assert len(digests) == 4
    for f in files:
        data = f.read_bytes()
        assert b"secret" not in data and b"x264 - core" not in data
        assert meta.top_level(f)[0][0] == b"ftyp"
        assert ffio.probe(f).duration == pytest.approx(2.0, abs=0.1)
    assert len({d["plan"]["timescale"] for d in done} | {d["plan"]["brand"] for d in done}) > 1

def test_meta_keeps_ai_label_and_c2pa(tmp_path):
    from reeluniq import meta

    src = tmp_path / "ai.mp4"
    subprocess.run([ffio.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+use_metadata_tags", "-metadata", 'AIGC={"Label":"1"}',
                    str(src)], check=True)
    c2pa = meta.box(b"uuid", meta.C2PA_UUID + b'{"digitalSourceType":".../trainedAlgorithmicMedia"}')
    meta.insert_boxes(src, [], [c2pa])
    assert meta.c2pa_ai_box(src) is not None
    done = meta.make_variants(src, tmp_path / "out", 1, seed=2, log=lambda *_: None)
    out = tmp_path / "out" / done[0]["file"]
    assert "aigc" in {k.lower() for k in ffio.probe(out).format_tags}
    assert meta.c2pa_ai_box(out) is not None and done[0]["picture_and_sound_unchanged"]

def test_meta_insert_boxes_keeps_playback(tmp_path):
    from reeluniq import meta

    src = _h264_clip(tmp_path, audio=False)
    before = meta.stream_md5(src, "v")
    meta.insert_boxes(src, [meta.box(b"free", b"x" * 100), meta.box(b"uuid", b"u" * 40)], [meta.box(b"free", b"y" * 50)])
    assert meta.stream_md5(src, "v") == before
