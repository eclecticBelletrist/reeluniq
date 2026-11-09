import pytest

pytestmark = pytest.mark.unit


def test_command_line_rejects_a_zero_count(tmp_path, capsys):
    from reeluniq import cli

    with pytest.raises(SystemExit):
        cli.main(["make", str(tmp_path / "x.mp4"), "-n", "0"])
    assert "must be 1 or more" in capsys.readouterr().err


def test_settings_become_the_defaults_and_a_flag_overrides_them():
    from reeluniq.cli import build_parser
    from reeluniq.settings import Settings

    ap = build_parser(Settings(mode="dust", count=5, port=9000, pin="1234"), "en")
    a = ap.parse_args(["app"])
    assert (a.mode, a.count, a.port, a.pin) == ("dust", 5, 9000, "1234")
    b = ap.parse_args(["app", "-m", "meta", "-n", "2", "--port", "1"])
    assert (b.mode, b.count, b.port) == ("meta", 2, 1)


def test_help_and_errors_follow_the_language(capsys):
    from reeluniq.cli import build_parser
    from reeluniq.settings import Settings

    ru = build_parser(Settings(), "ru")
    with pytest.raises(SystemExit):
        ru.parse_args(["make", "x.mp4", "-n", "0"])
    assert "должно быть 1 или больше" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        ru.parse_args(["--help"])
    assert "метаданные" in capsys.readouterr().out


def test_a_bad_settings_file_is_reported_not_raised(tmp_path, monkeypatch, capsys):
    from reeluniq import cli

    bad = tmp_path / "bad.env"
    bad.write_text("REELUNIQ_MODE=bogus\n")
    monkeypatch.setenv("REELUNIQ_CONFIG", str(bad))
    assert cli.main(["app"]) == 1
    assert "REELUNIQ_MODE" in capsys.readouterr().err


def test_seed_is_optional_and_never_negative(capsys):
    from reeluniq.cli import build_parser
    from reeluniq.settings import Settings

    ap = build_parser(Settings(), "en")
    assert ap.parse_args(["make", "x.mp4"]).seed is None
    assert ap.parse_args(["make", "x.mp4", "--seed", "0"]).seed == 0
    with pytest.raises(SystemExit):
        ap.parse_args(["make", "x.mp4", "--seed", "-1"])
    assert "must be 0 or more" in capsys.readouterr().err
