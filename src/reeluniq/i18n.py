"""Console and --help texts in Russian and English. The web page carries its own copy of its texts (see serve.py)."""

from __future__ import annotations

import locale
import os

MSG = {
    "en": {
        "description": "Distinct variants of your own videos.",
        "mode_light": "small crop, speed, frame-rate and pitch nudges",
        "mode_dust": "light plus invisible pixel-level touches",
        "mode_operator": "slow, smooth virtual camera drift (zoom 5-11 %, a few pixels of pan)",
        "mode_meta": "new metadata and container structure only; picture and sound are copied as they are",
        "cmd_make": "make N variants of one video",
        "cmd_watch": "hot folder: drop a video in, variants appear in FOLDER/variants/<file name>/",
        "cmd_app": "local web page: drop a video, download the variants",
        "help_out_make": "folder for the variants (default: <source name>_variants next to the source, or inside REELUNIQ_OUT)",
        "help_out_watch": "folder for the results (default: FOLDER/variants, or REELUNIQ_OUT)",
        "help_once": "process the files already there and exit",
        "help_host": "use 0.0.0.0 to reach it from a phone on the same network (a PIN is then required)",
        "help_pin": "PIN for access from other machines (default: random, printed at start); unused on localhost",
        "help_no_browser": "do not open the page in the browser",
        "positive": "must be 1 or more",
        "non_negative": "must be 0 or more",
        "help_seed": "number that fixes the random draw (default: a new one each run, printed and kept in report.json)",
        "done": "done: {n} file(s); report: {report}",
        "stopped": "stopped",
        "error": "error: {msg}",
        "watching": "watching {root}  (results: {out}, mode={mode}, n={count}); Ctrl+C to stop",
        "queued": "queued: {name}",
        "job": "{name}: {state} ({n} file(s))",
        "state_done": "done",
        "state_failed": "failed",
        "open": "open {url}",
        "pin": "PIN: {pin}",
        "stop": "Ctrl+C to stop",
    },
    "ru": {
        "description": "Разные варианты ваших видео.",
        "mode_light": "небольшая обрезка, чуть другие скорость, частота кадров и высота звука",
        "mode_dust": "лёгкий плюс незаметные правки на уровне пикселей",
        "mode_operator": "медленное плавное движение виртуальной камеры (зум 5-11 %, несколько пикселей сдвига)",
        "mode_meta": "только новые метаданные и структура контейнера; картинка и звук копируются как есть",
        "cmd_make": "сделать N вариантов одного видео",
        "cmd_watch": "папка-приёмник: положите видео, варианты появятся в ПАПКА/variants/<имя файла>/",
        "cmd_app": "локальная страница: загрузите видео, скачайте варианты",
        "help_out_make": "папка для вариантов (по умолчанию <имя источника>_variants рядом с источником или внутри REELUNIQ_OUT)",
        "help_out_watch": "папка для результатов (по умолчанию ПАПКА/variants или REELUNIQ_OUT)",
        "help_once": "обработать файлы, которые уже лежат в папке, и выйти",
        "help_host": "0.0.0.0, чтобы открыть страницу с телефона в той же сети (тогда нужен PIN)",
        "help_pin": "PIN для доступа с других устройств (по умолчанию случайный, печатается при запуске); на localhost не нужен",
        "help_no_browser": "не открывать страницу в браузере",
        "positive": "должно быть 1 или больше",
        "non_negative": "должно быть 0 или больше",
        "help_seed": "число, фиксирующее случайный выбор (по умолчанию каждый раз новое, печатается и сохраняется в report.json)",
        "done": "готово: файлов {n}; отчёт: {report}",
        "stopped": "остановлено",
        "error": "ошибка: {msg}",
        "watching": "слежу за {root}  (результаты: {out}, режим={mode}, версий={count}); остановить: Ctrl+C",
        "queued": "в очереди: {name}",
        "job": "{name}: {state} (файлов: {n})",
        "state_done": "готово",
        "state_failed": "ошибка",
        "open": "откройте {url}",
        "pin": "PIN: {pin}",
        "stop": "остановить: Ctrl+C",
    },
}


def resolve(lang: str) -> str:
    """'ru' or 'en'; 'auto' follows the system language."""
    if lang in MSG:
        return lang
    code = next((os.environ[v] for v in ("LC_ALL", "LC_MESSAGES", "LANG") if os.environ.get(v)), None) or locale.getlocale()[0] or ""
    return "ru" if code.lower().startswith(("ru", "russian")) else "en"


def t(lang: str, key: str, **values) -> str:
    return MSG[lang][key].format(**values)
