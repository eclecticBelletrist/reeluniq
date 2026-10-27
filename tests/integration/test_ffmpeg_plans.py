import subprocess

import numpy as np
import pytest

from reeluniq import ffio, plan as planmod

pytestmark = pytest.mark.integration


def test_probe(clip):
    info = ffio.probe(clip)
    assert info.display_size == (640, 360) and info.has_audio and info.audio_rate == 32000

def test_plan_is_deterministic_and_alternates_pitch(clip):
    info = ffio.probe(clip)
    a = planmod.draw(info, "soft", 7, True, index=0)
    assert a == planmod.draw(info, "soft", 7, True, index=0)
    assert a.pitch > 1 > planmod.draw(info, "soft", 7, True, index=1).pitch
    assert 1.07 <= a.zoom <= 1.12

def test_pitch_filter_resamples_before_asetrate(clip):
    """Regression: asetrate on a 32 kHz source must not shift pitch by 48/32."""
    info = ffio.probe(clip)
    plan = planmod.draw(info, "soft", 3, True, index=0)
    af = planmod.audio_filter(plan)
    assert af.startswith("aresample=48000,asetrate=")
    out = subprocess.run(
        [ffio.FFMPEG, "-v", "error", "-i", str(clip), "-vn", "-af", af, "-f", "f32le", "-ar", "48000", "-ac", "1", "-"],
        capture_output=True, check=True,
    ).stdout
    pcm = np.frombuffer(out, np.float32)
    assert abs(len(pcm) / 48000 - 2.0) < 0.1  # duration preserved
    peak = np.argmax(np.abs(np.fft.rfft(pcm[:48000])))     # one second of audio: one FFT bin is 1 Hz
    assert abs(plan.pitch - 1) > 0.008
    assert abs(peak / 440 - plan.pitch) < 0.004  # shifted by `pitch`, not left alone and not by 48/32

def test_video_filter_shapes(clip):
    info = ffio.probe(clip)
    soft = planmod.draw(info, "soft", 1, False)
    vf = planmod.video_filter(info, soft)
    assert "crop=" in vf and vf.endswith("format=yuv420p")

def test_hdr_tonemap_roundtrip_keeps_brightness(tmp_path):
    """SDR -> HLG -> HDR_TONEMAP must land close to the SDR picture (`hable` made it about 25 % darker)."""
    filters = subprocess.run([ffio.FFMPEG, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    if "zscale" not in filters:
        pytest.skip("this ffmpeg has no zscale filter (HDR sources need it; the release builds include it)")
    src = "testsrc2=size=320x180:rate=5:duration=1"
    hlg = tmp_path / "hlg.mp4"
    sdr = "format=yuv420p,setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv"
    to_hlg = (
        sdr + ",zscale=tin=bt709:t=linear:npl=100,format=gbrpf32le,zscale=p=bt2020,"
        "zscale=t=arib-std-b67:m=bt2020nc:r=tv,format=yuv420p10le"
    )
    subprocess.run(
        [ffio.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", src, "-vf", to_hlg, "-c:v", "libx265", "-preset",
         "ultrafast", "-crf", "12", "-x265-params",
         "colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc:log-level=error", str(hlg)],
        check=True,
    )
    assert ffio.probe(hlg).is_hdr

    def gray(*inp, vf):
        raw = subprocess.run([ffio.FFMPEG, "-v", "error", *inp, "-vf", vf, "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
        return np.frombuffer(raw, np.uint8).astype(float)

    ref = gray("-f", "lavfi", "-i", src, vf=sdr + ",format=gray")
    out = gray("-i", str(hlg), vf=planmod.HDR_TONEMAP + ",format=gray")
    assert ref.shape == out.shape and abs(ref.mean() - out.mean()) < 6

def test_light_and_dust_plans(clip):
    info = ffio.probe(clip)
    light = planmod.draw(info, "light", 3, True)
    assert 1.04 <= light.zoom <= 1.06 and light.dust == 0 and abs(light.pitch - 1) <= 0.0125
    dust = planmod.draw(info, "dust", 3, True)
    assert dust.dust == 1.0 and 0.1 <= abs(dust.rotate_deg) <= 0.3
    w, h = info.display_size
    assert dust.zoom >= planmod.min_zoom_for_rotation(w, h, dust.rotate_deg)
    assert planmod.draw(info, "soft", 3, True).dust == 0
    vf = planmod.video_filter(info, dust)
    assert "noise=" in vf and "chromashift" in vf and "sin(n*" in vf
    assert vf != planmod.video_filter(info, planmod.draw(info, "dust", 4, True))   # the jitter depends on the seed
    out = clip.parent / "dust.mp4"
    subprocess.run(planmod.ffmpeg_command(info, dust, str(clip), str(out)), check=True, capture_output=True)
    assert ffio.probe(out).display_size == planmod.output_size(info)
