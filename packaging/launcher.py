"""Entry point of the packaged program: no arguments (a double click) opens the web page, anything else is the normal command line."""

import socket
import sys
import webbrowser

from reeluniq import settings
from reeluniq.cli import main


def banner(cfg: settings.Settings) -> str:
    ru = f"""  Не закрывайте это окно, пока идёт обработка: оно и есть программа.
  Страница откроется в браузере сама. Если нет, откройте http://127.0.0.1:{cfg.port}
  Чтобы выйти, закройте окно.
"""
    en = f"""  Keep this window open while videos are being made: it is the program.
  The page opens in your browser by itself. If it does not, go to http://127.0.0.1:{cfg.port}
  To quit, close this window.
"""
    return "reeluniq\n" + {"ru": ru, "en": en}.get(cfg.lang, ru + "\n" + en)


def _port_busy(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), 0.5).close()
        return True
    except OSError:
        return False


def _wait_for_enter() -> None:
    try:
        input("Press Enter to close.")
    except EOFError:
        pass


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(main())
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        cfg = settings.load()
        print(banner(cfg), flush=True)
        if _port_busy(cfg.port):
            webbrowser.open(f"http://127.0.0.1:{cfg.port}")
            print(f"\nПорт {cfg.port} занят, возможно программа уже запущена; открываю страницу.")
            print(f"Port {cfg.port} is in use, reeluniq may already be running; opening the page.")
            _wait_for_enter()
            sys.exit(1)
        code = main(["app"])
        if code:
            _wait_for_enter()
        sys.exit(code)
    except Exception as e:
        print(f"\nreeluniq could not start: {e}")
        _wait_for_enter()
        sys.exit(1)
