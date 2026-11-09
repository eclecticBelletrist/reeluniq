import pytest

pytestmark = pytest.mark.integration


def test_watch_once_handles_empty_folder_and_same_stem(clip, tmp_path, monkeypatch):
    import shutil
    from reeluniq import watch

    watch.watch(tmp_path, 1, "meta", poll=0.1, once=True, log=lambda *_: None)
    shutil.copy(clip, tmp_path / "a.mp4")
    shutil.copy(clip, tmp_path / "a.mov")
    monkeypatch.setattr(watch, "STABLE_SECONDS", 0.2)
    watch.watch(tmp_path, 1, "meta", poll=0.1, once=True, log=lambda *_: None)
    assert sorted(d.name for d in (tmp_path / "variants").iterdir()) == ["a.mov", "a.mp4"]
    assert all(any(d.glob("*.mp4")) for d in (tmp_path / "variants").iterdir())


def test_results_folder_can_be_chosen(tmp_path):
    from reeluniq import watch

    out = tmp_path / "elsewhere" / "results"
    watch.watch(tmp_path, 1, "meta", poll=0.1, once=True, log=lambda *_: None, out=out)
    assert out.is_dir() and not (tmp_path / "variants").exists()


def test_a_missing_folder_is_an_error_not_a_new_folder(tmp_path):
    from reeluniq import watch

    with pytest.raises(FileNotFoundError):
        watch.watch(tmp_path / "typo", 1, "meta", poll=0.1, once=True, log=lambda *_: None)
    assert not (tmp_path / "typo").exists()


def test_once_does_not_wait_for_an_empty_file(tmp_path, monkeypatch):
    from reeluniq import watch

    (tmp_path / "empty.mp4").write_bytes(b"")
    monkeypatch.setattr(watch, "STABLE_SECONDS", 0.2)
    watch.watch(tmp_path, 1, "meta", poll=0.1, once=True, log=lambda *_: None)
