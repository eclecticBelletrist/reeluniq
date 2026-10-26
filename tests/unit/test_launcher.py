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

