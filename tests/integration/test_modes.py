import subprocess

import pytest

from reeluniq import ffio

pytestmark = pytest.mark.integration


def test_every_mode_makes_playable_variants(clip, tmp_path):
    from reeluniq import make

    for mode in make.MODES:
        out = tmp_path / mode
        done = make.make_variants(clip, out, 2, mode, log=lambda *_: None)
        assert len(done) == 2
        for d in done:
            info = ffio.probe(out / d["file"])
            assert info.codec == "h264" and info.duration > 1.5

def test_light_keeps_the_aigc_tag(tmp_path):
    from reeluniq import make

    src = tmp_path / "ai.mp4"
    subprocess.run([ffio.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+use_metadata_tags", "-metadata", 'AIGC={"Label":"1"}',
                    str(src)], check=True)
    for mode in ("light", "operator"):
        done = make.make_variants(src, tmp_path / mode, 1, mode, log=lambda *_: None)
        assert "aigc" in {k.lower() for k in ffio.probe(tmp_path / mode / done[0]["file"]).format_tags}
