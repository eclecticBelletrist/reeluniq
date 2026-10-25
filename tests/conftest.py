import subprocess
from pathlib import Path

import pytest

from reeluniq import ffio


@pytest.fixture(scope="session")
def clip(tmp_path_factory) -> Path:
    """2 s synthetic 32 kHz-audio clip, the sample-rate case that once broke the pitch filter."""
    p = tmp_path_factory.mktemp("clip") / "t.mp4"
    subprocess.run(
        [ffio.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24:duration=2",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=32000:duration=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(p)],
        check=True,
    )
    return p
