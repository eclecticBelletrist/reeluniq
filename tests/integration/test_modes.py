import subprocess

import pytest

from reeluniq import ffio

pytestmark = pytest.mark.integration

MODES = ("light", "dust", "operator", "meta")
C2PA_JSON = b'{"digitalSourceType":".../trainedAlgorithmicMedia"}'


def _ai_clip(tmp_path, tag=True, c2pa=False):
    from reeluniq import meta

    src = tmp_path / "ai.mp4"
    cmd = [ffio.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=1",
           "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if tag:
        cmd += ["-movflags", "+use_metadata_tags", "-metadata", 'AIGC={"Label":"1"}']
    subprocess.run(cmd + [str(src)], check=True)
    if c2pa:
        meta.insert_boxes(src, [], [meta.box(b"uuid", meta.C2PA_UUID + C2PA_JSON)])
    return src


def _first_pixel(path):
    """First pixel of the first frame as RGB, decoding the picture as BT.709 limited range."""
    out = subprocess.run([ffio.FFMPEG, "-v", "error", "-i", str(path), "-vf", "scale=in_color_matrix=bt709:in_range=tv,format=rgb24",
                          "-frames:v", "1", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return tuple(out[:3])


def test_every_mode_makes_playable_variants(clip, tmp_path):
    from reeluniq import make

    for mode in make.MODES:
        out = tmp_path / mode
        done = make.make_variants(clip, out, 2, mode, log=lambda *_: None)
        assert len(done) == 2
        for d in done:
            info = ffio.probe(out / d["file"])
            assert info.codec == "h264" and info.duration > 1.5


@pytest.mark.parametrize("mode", MODES)
def test_every_mode_keeps_the_aigc_tag_and_the_c2pa_box(tmp_path, mode):
    from reeluniq import make, meta

    src = _ai_clip(tmp_path, tag=True, c2pa=True)
    lines = []
    done = make.make_variants(src, tmp_path / mode, 1, mode, log=lines.append)
    out = tmp_path / mode / done[0]["file"]
    assert "aigc" in {k.lower() for k in ffio.probe(out).format_tags}
    assert meta.c2pa_ai_box(out) is not None
    assert any("AI-origin label" in line and "C2PA" in line for line in lines)


@pytest.mark.parametrize("mode", MODES)
def test_a_c2pa_only_source_is_reported_and_kept(tmp_path, mode):
    from reeluniq import make, meta

    src = _ai_clip(tmp_path, tag=False, c2pa=True)
    lines = []
    done = make.make_variants(src, tmp_path / mode, 1, mode, log=lines.append)
    assert meta.c2pa_ai_box(tmp_path / mode / done[0]["file"]) is not None
    assert any("AI-origin label (C2PA)" in line for line in lines)


@pytest.mark.parametrize("mode", ("light", "dust", "operator"))
def test_a_source_that_is_not_an_mp4_still_works(tmp_path, mode):
    from reeluniq import make

    src = tmp_path / "t.mkv"
    subprocess.run([ffio.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    assert make.make_variants(src, tmp_path / mode, 1, mode, log=lambda *_: None)


def test_meta_mode_refuses_what_it_cannot_rewrite(tmp_path):
    from reeluniq import make

    src = tmp_path / "t.mkv"
    subprocess.run([ffio.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    with pytest.raises(ffio.FFmpegError, match="MP4 or MOV"):
        make.make_variants(src, tmp_path / "out", 1, "meta", log=lambda *_: None)


@pytest.mark.parametrize("mode", ("light", "operator"))
def test_colour_survives_the_re_encode(tmp_path, mode):
    from reeluniq import make

    src = tmp_path / "flat.mp4"
    subprocess.run([ffio.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0xC83C28:size=320x180:rate=24:duration=2",
                    "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
                    "-color_trc", "bt709", "-c:v", "libx264", str(src)], check=True)
    done = make.make_variants(src, tmp_path / mode, 1, mode, log=lambda *_: None)
    want, got = _first_pixel(src), _first_pixel(tmp_path / mode / done[0]["file"])
    assert all(abs(a - b) <= 4 for a, b in zip(want, got)), (want, got)


def test_operator_gives_up_on_a_broken_file_instead_of_hanging(tmp_path):
    import random
    import threading

    from reeluniq import operator

    src = tmp_path / "long.mp4"
    subprocess.run([ffio.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24:duration=12",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    data = bytearray(src.read_bytes())
    rng = random.Random(7)
    for i in rng.sample(range(2048, len(data)), len(data) // 12):
        data[i] = rng.randrange(256)
    src.write_bytes(data)
    outcome = []

    def run():
        try:
            outcome.append(operator.render(src, tmp_path / "o.mp4", 1))
        except ffio.FFmpegError as e:
            outcome.append(e)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(120)
    assert not worker.is_alive() and outcome
    assert not list(tmp_path.glob("*.part"))


def test_operator_handles_a_one_frame_clip(tmp_path):
    from reeluniq import make

    src = tmp_path / "one.mp4"
    subprocess.run([ffio.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24", "-frames:v", "1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    assert make.make_variants(src, tmp_path / "out", 1, "operator", log=lambda *_: None)


def test_without_a_seed_every_run_differs_and_the_seed_reproduces(clip, tmp_path):
    import hashlib

    from reeluniq import cli

    def run(name, *extra):
        out = tmp_path / name
        assert cli.main(["make", str(clip), "-m", "light", "-n", "1", "--out", str(out), *extra]) == 0
        return hashlib.sha256(next(out.glob("*.mp4")).read_bytes()).hexdigest()

    assert run("a") != run("b")
    assert run("c", "--seed", "3") == run("d", "--seed", "3")
