"""Settings: command-line flag, then REELUNIQ_* environment variable, then the reeluniq.env file, then the default.

The file holds lines of `REELUNIQ_NAME=value` (the same names as the variables), `#` starts a comment. In the release
archives it sits next to the program; from source it is looked for in the per-user folder (see paths.app_dir).
`REELUNIQ_CONFIG` names a different file.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, fields
from pathlib import Path

from . import paths
from .make import MODES

FILE_NAME = "reeluniq.env"
LANGS = ("auto", "ru", "en")


class SettingsError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    lang: str = "auto"
    mode: str = "light"
    count: int = 3
    out: str | None = None
    host: str = "127.0.0.1"
    port: int = 8765
    pin: str | None = None
    browser: bool = True


def _choice(choices):
    def parse(value: str):
        if value.lower() not in choices:
            raise ValueError(f"one of {', '.join(choices)}")
        return value.lower()
    return parse


def _int(low: int, high: int | None = None):
    def parse(value: str):
        try:
            n = int(value)
        except ValueError:
            raise ValueError("a whole number") from None
        if n < low or (high is not None and n > high):
            raise ValueError(f"a whole number from {low}" + (f" to {high}" if high is not None else ""))
        return n
    return parse


def _bool(value: str) -> bool:
    if value.lower() in ("1", "true", "yes", "on"):
        return True
    if value.lower() in ("0", "false", "no", "off"):
        return False
    raise ValueError("yes or no")


PARSERS = {
    "lang": _choice(LANGS), "mode": _choice(MODES), "count": _int(1), "out": str,
    "host": str, "port": _int(0, 65535), "pin": str, "browser": _bool,
}
KEYS = {f"REELUNIQ_{f.name.upper()}": f.name for f in fields(Settings)}


def config_file(env=None) -> Path:
    env = os.environ if env is None else env
    if env.get("REELUNIQ_CONFIG"):
        return Path(env["REELUNIQ_CONFIG"])
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else paths.app_dir()
    return base / FILE_NAME


def read_file(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError) as e:
        raise SettingsError(f"{path}: {e}") from None
    values: dict[str, str] = {}
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key, value = key.strip().upper(), value.strip()
        if not sep or key not in KEYS:
            raise SettingsError(f"{path}:{n}: expected one of {', '.join(KEYS)} as NAME=value, got {line!r}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def load(env=None) -> Settings:
    env = os.environ if env is None else env
    path = config_file(env)
    if env.get("REELUNIQ_CONFIG") and not path.is_file():
        raise SettingsError(f"REELUNIQ_CONFIG: {path} does not exist")
    raw = read_file(path)
    raw.update({k: v for k, v in env.items() if k in KEYS and v != ""})
    found: dict[str, object] = {}
    for key, name in KEYS.items():
        if raw.get(key, "") == "":
            continue
        try:
            found[name] = PARSERS[name](raw[key])
        except ValueError as e:
            raise SettingsError(f"{key}={raw[key]!r}: expected {e}") from None
    return Settings(**found)
