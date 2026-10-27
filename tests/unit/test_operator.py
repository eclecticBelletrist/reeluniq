import numpy as np
import pytest

pytestmark = pytest.mark.unit


def test_operator_path_is_smooth_and_stays_inside_the_frame():
    from reeluniq import operator as op

    zoom, dx, dy, _ = op.camera_path(30.0, 24.0, np.random.default_rng(4))
    assert op.ZOOM_LO - 1e-9 <= zoom.min() and zoom.max() <= op.ZOOM_HI + 1e-9
    assert np.abs(dx).max() <= op.SHIFT_PX and np.abs(dy).max() <= op.SHIFT_PX
    assert np.abs(np.diff(np.log(zoom))).max() * 24 < 0.03           # never faster than a slow push
    for x in (np.log(zoom), dx, dy):                                 # no kinks: the step itself changes by very little
        assert np.abs(np.diff(x, 2)).max() < 0.02 * max(np.ptp(x), 1e-6) + 1e-3
    # the window (half the frame over the zoom, plus the shift seen in source pixels) must stay inside a 1080p frame
    assert (1920 / (2 * zoom) + np.abs(dx) / zoom <= 1920 / 2).all() and (1080 / (2 * zoom) + np.abs(dy) / zoom <= 1080 / 2).all()

def test_operator_warp_is_exact_at_unit_zoom_and_matches_a_crop():
    from reeluniq import operator as op
    import cv2

    rng = np.random.default_rng(1)
    frame = cv2.GaussianBlur((rng.random((360, 640, 3)) * 255).astype(np.uint8), (0, 0), 3)
    same = op.warp(frame, (640, 360), 1.0, 0.0, 0.0, 640, 360)
    assert np.abs(same.astype(int) - frame.astype(int)).max() <= 1
    mid = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_CUBIC)       # a mid image larger than the source, as for zoom > 1
    out = op.warp(mid, (640, 360), 2.0, 0.0, 0.0, 320, 180)
    ref = cv2.resize(frame[90:270, 160:480], (320, 180), interpolation=cv2.INTER_AREA)
    assert out.shape == ref.shape and np.abs(out.astype(int) - ref.astype(int)).mean() < 2.0

def test_operator_shift_moves_the_window_by_whole_output_pixels():
    from reeluniq import operator as op

    frame = np.zeros((90, 160, 3), np.uint8)
    frame[:, 80:] = 255
    a = op.warp(frame, (160, 90), 1.0, 0.0, 0.0, 160, 90)
    b = op.warp(frame, (160, 90), 1.0, 3.0, 0.0, 160, 90)           # window moves right: the edge moves left by 3 px
    assert abs(int((a[0, :, 0] > 127).argmax()) - int((b[0, :, 0] > 127).argmax()) - 3) <= 1
