import pytest

pytestmark = pytest.mark.unit


def test_command_line_rejects_a_zero_count(tmp_path, capsys):
    from reeluniq import cli

    with pytest.raises(SystemExit):
        cli.main(["make", str(tmp_path / "x.mp4"), "-n", "0"])
    assert "must be 1 or more" in capsys.readouterr().err
