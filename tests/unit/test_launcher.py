import importlib.util
import socket
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _launcher():
    spec = importlib.util.spec_from_file_location("launcher", Path(__file__).parents[2] / "packaging" / "launcher.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_listening_port_counts_as_busy_and_a_free_one_does_not():
    launcher = _launcher()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        port = s.getsockname()[1]
        assert launcher._port_busy(port)
    assert not launcher._port_busy(port)


@pytest.mark.parametrize("lang, expected, absent", [("ru", "Не закрывайте", "Keep this window"), ("en", "Keep this window", "Не закрывайте")])
def test_banner_follows_the_language_setting(lang, expected, absent):
    from reeluniq.settings import Settings

    text = _launcher().banner(Settings(lang=lang, port=9001))
    assert expected in text and absent not in text and "9001" in text
