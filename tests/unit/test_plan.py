import pytest

from reeluniq import plan as planmod

pytestmark = pytest.mark.unit


def test_rotation_zoom_covers_corners():
    assert planmod.min_zoom_for_rotation(1920, 1080, 0) == pytest.approx(1.0)
    assert planmod.min_zoom_for_rotation(1920, 1080, 1.0) > 1.03
