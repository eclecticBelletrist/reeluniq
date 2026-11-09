"""Command line: `reeluniq make VIDEO`, `reeluniq watch FOLDER`, `reeluniq app`."""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

from . import ffio, settings
from .i18n import resolve, t
from .make import MODES, make_variants


def cmd_make(args: argparse.Namespace) -> int:
    src = Path(args.source)
    out = Path(args.out) if args.out else (Path(args.cfg.out) if args.cfg.out else src.parent) / f"{src.stem}_variants"
    seed = secrets.randbelow(2**31) if args.seed is None else args.seed
    print(f"{src.name} -> {out}  (mode={args.mode}, n={args.count}, seed={seed})", flush=True)
    try:
        done = make_variants(src, out, args.count, args.mode, seed=seed)
    except KeyboardInterrupt:
        print(t(args.lang, "stopped"))
        return 130
    print(t(args.lang, "done", n=len(done), report=out / "report.json"))
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    from .watch import watch

    try:
        out = args.out or args.cfg.out
        watch(Path(args.folder), args.count, args.mode, once=args.once, out=Path(out) if out else None, lang=args.lang)
    except KeyboardInterrupt:
        print(t(args.lang, "stopped"))
    return 0


def cmd_app(args: argparse.Namespace) -> int:
    from .serve import serve

    return serve(args.host, args.port, args.pin, args.count, args.mode,
                 open_browser=args.cfg.browser and not args.no_browser, lang=args.lang, page_lang=args.cfg.lang)


def build_parser(cfg: settings.Settings, lang: str) -> argparse.ArgumentParser:
    """The defaults come from the settings, so a flag overrides them and nothing else needs to look at them."""
    def positive(text: str) -> int:
        n = int(text)
        if n < 1:
            raise argparse.ArgumentTypeError(t(lang, "positive"))
        return n

    def non_negative(text: str) -> int:
        n = int(text)
        if n < 0:
            raise argparse.ArgumentTypeError(t(lang, "non_negative"))
        return n

    modes = "\n".join(f"  {k:9s}{t(lang, 'mode_' + k)}" for k in MODES)
    ap = argparse.ArgumentParser(prog="reeluniq", description=t(lang, "description") + "\n\n" + modes,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.set_defaults(cfg=cfg, lang=lang)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("-m", "--mode", choices=MODES, default=cfg.mode)
        sp.add_argument("-n", "--count", type=positive, default=cfg.count)

    m = sub.add_parser("make", help=t(lang, "cmd_make"))
    m.add_argument("source")
    common(m)
    m.add_argument("--seed", type=non_negative, help=t(lang, "help_seed"))
    m.add_argument("--out", help=t(lang, "help_out_make"))
    m.set_defaults(fn=cmd_make)
    w = sub.add_parser("watch", help=t(lang, "cmd_watch"))
    w.add_argument("folder")
    common(w)
    w.add_argument("--once", action="store_true", help=t(lang, "help_once"))
    w.add_argument("--out", help=t(lang, "help_out_watch"))
    w.set_defaults(fn=cmd_watch)
    a = sub.add_parser("app", help=t(lang, "cmd_app"))
    a.add_argument("--host", default=cfg.host, help=t(lang, "help_host"))
    a.add_argument("--port", type=int, default=cfg.port)
    a.add_argument("--pin", default=cfg.pin, help=t(lang, "help_pin"))
    common(a)
    a.add_argument("--no-browser", action="store_true", help=t(lang, "help_no_browser"))
    a.set_defaults(fn=cmd_app)
    return ap


def main(argv: list[str] | None = None) -> int:
    try:
        cfg = settings.load()
    except settings.SettingsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    lang = resolve(cfg.lang)
    args = build_parser(cfg, lang).parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    try:
        return args.fn(args)
    except (OSError, ffio.FFmpegError) as e:
        print(t(lang, "error", msg=e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
