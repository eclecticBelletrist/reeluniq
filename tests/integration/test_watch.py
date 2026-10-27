import pytest

pytestmark = pytest.mark.integration


def test_watch_once_handles_empty_folder_and_same_stem(clip, tmp_path):
    import shutil
    from reeluniq import watch

    watch.watch(tmp_path, 1, "meta", poll=0.1, once=True, log=lambda *_: None)        # nothing to do: returns at once
    shutil.copy(clip, tmp_path / "a.mp4")
    shutil.copy(clip, tmp_path / "a.mov")
    watch.STABLE_SECONDS, old = 0.2, watch.STABLE_SECONDS
    try:
        watch.watch(tmp_path, 1, "meta", poll=0.1, once=True, log=lambda *_: None)
    finally:
        watch.STABLE_SECONDS = old
    assert sorted(d.name for d in (tmp_path / "variants").iterdir()) == ["a.mov", "a.mp4"]
    assert all(any(d.glob("*.mp4")) for d in (tmp_path / "variants").iterdir())
