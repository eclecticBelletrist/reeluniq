import re

import pytest

pytestmark = pytest.mark.unit


def _load(tmp_path, file_text=None, env=None):
    from reeluniq import settings

    path = tmp_path / "reeluniq.env"
    path.write_text(file_text or "", encoding="utf-8")
    return settings.load({"REELUNIQ_CONFIG": str(path), **(env or {})})


def test_defaults_without_a_file(tmp_path):
    from reeluniq.settings import Settings

    assert _load(tmp_path) == Settings()


def test_file_values_comments_quotes_and_bom(tmp_path):
    s = _load(tmp_path, "\ufeff# comment\n\nREELUNIQ_LANG=ru\nreeluniq_mode = dust\nREELUNIQ_OUT=\"C:/Видео/готово\"\nREELUNIQ_BROWSER=no\nREELUNIQ_PORT=9000\n")
    assert (s.lang, s.mode, s.out, s.browser, s.port) == ("ru", "dust", "C:/Видео/готово", False, 9000)


def test_variable_beats_file_and_blank_keeps_default(tmp_path):
    s = _load(tmp_path, "REELUNIQ_MODE=dust\nREELUNIQ_COUNT=5\n", {"REELUNIQ_MODE": "meta", "REELUNIQ_COUNT": ""})
    assert (s.mode, s.count) == ("meta", 5)


@pytest.mark.parametrize("line, key", [
    ("REELUNIQ_LANG=de", "REELUNIQ_LANG"), ("REELUNIQ_MODE=bogus", "REELUNIQ_MODE"), ("REELUNIQ_COUNT=0", "REELUNIQ_COUNT"),
    ("REELUNIQ_PORT=70000", "REELUNIQ_PORT"), ("REELUNIQ_BROWSER=maybe", "REELUNIQ_BROWSER"),
])
def test_a_bad_value_names_the_setting(tmp_path, line, key):
    from reeluniq.settings import SettingsError

    with pytest.raises(SettingsError, match=key):
        _load(tmp_path, line + "\n")


@pytest.mark.parametrize("text", ["REELUNIQ_LANGUAGE=ru\n", "just text\n", "REELUNIQ_FFMPEG=/usr/bin/ffmpeg\n"])
def test_unknown_line_is_refused_with_its_position(tmp_path, text):
    from reeluniq.settings import SettingsError

    with pytest.raises(SettingsError, match=r"reeluniq\.env:1"):
        _load(tmp_path, text)


def test_a_missing_config_file_that_was_asked_for_is_an_error(tmp_path):
    from reeluniq import settings

    with pytest.raises(settings.SettingsError, match="REELUNIQ_CONFIG"):
        settings.load({"REELUNIQ_CONFIG": str(tmp_path / "typo.env")})


def test_config_file_location(tmp_path, monkeypatch):
    from reeluniq import paths, settings

    assert settings.config_file({"REELUNIQ_CONFIG": "x/y.env"}).as_posix() == "x/y.env"
    assert settings.config_file({}) == paths.app_dir() / "reeluniq.env"
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", str(tmp_path / "reeluniq"))
    assert settings.config_file({}) == tmp_path / "reeluniq.env"


def test_auto_language_follows_the_system(monkeypatch):
    from reeluniq import i18n

    assert i18n.resolve("ru") == "ru" and i18n.resolve("en") == "en"
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", "ru_RU.UTF-8")
    assert i18n.resolve("auto") == "ru"
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert i18n.resolve("auto") == "en"


def test_both_languages_have_the_same_messages():
    from reeluniq.i18n import MSG

    assert MSG["en"].keys() == MSG["ru"].keys()
    for key, text in MSG["en"].items():
        assert set(re.findall(r"{(\w+)}", text)) == set(re.findall(r"{(\w+)}", MSG["ru"][key])), key
