"""Command line: `reeluniq make VIDEO`, `reeluniq watch FOLDER`, `reeluniq app`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ffio
from .make import MODES, make_variants

MODE_HELP = {
    "light": "small crop, speed, frame-rate and pitch nudges",
    "dust": "light plus invisible pixel-level touches",
    "operator": "slow, smooth virtual camera drift (zoom 5-11 %, a few pixels of pan)",
    "meta": "new metadata and container structure only; picture and sound are copied as they are",
}


def positive(text: str) -> int:
    n = int(text)
    if n < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return n


def cmd_make(args: argparse.Namespace) -> int:
    src = Path(args.source)
    out = Path(args.out) if args.out else src.parent / f"{src.stem}_variants"
    print(f"{src.name} -> {out}  (mode={args.mode}, n={args.count}, seed={args.seed})", flush=True)
    done = make_variants(src, out, args.count, args.mode, seed=args.seed)
    print(f"done: {len(done)} file(s); report: {out / 'report.json'}")
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    from .watch import watch

    try:
        watch(Path(args.folder), args.count, args.mode, once=args.once)
    except KeyboardInterrupt:
        print("stopped")
    return 0


def cmd_app(args: argparse.Namespace) -> int:
    from .serve import serve

    return serve(args.host, args.port, args.pin, args.count, args.mode, open_browser=not args.no_browser)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="reeluniq", description="Distinct variants of your own videos.\n\n" + "\n".join(f"  {k:9s}{v}" for k, v in MODE_HELP.items()),
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make", help="make N variants of one video")
    m.add_argument("source")
    m.add_argument("-m", "--mode", choices=MODES, default="light")
    m.add_argument("-n", "--count", type=positive, default=3)
    m.add_argument("--seed", type=int, default=1)
    m.add_argument("--out", help="output folder (default: next to the source)")
    m.set_defaults(fn=cmd_make)
    w = sub.add_parser("watch", help="hot folder: drop a video in, variants appear in FOLDER/variants/<file name>/")
    w.add_argument("folder")
    w.add_argument("-m", "--mode", choices=MODES, default="light")
    w.add_argument("-n", "--count", type=positive, default=3)
    w.add_argument("--once", action="store_true", help="process the files already there and exit")
    w.set_defaults(fn=cmd_watch)
    a = sub.add_parser("app", help="local web page: drop a video, download the variants")
    a.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to reach it from a phone on the same network (a PIN is then required)")
    a.add_argument("--port", type=int, default=8765)
    a.add_argument("--pin", help="PIN for access from other machines (default: random, printed at start); unused on localhost")
    a.add_argument("-m", "--mode", choices=MODES, default="light")
    a.add_argument("-n", "--count", type=positive, default=3)
    a.add_argument("--no-browser", action="store_true")
    a.set_defaults(fn=cmd_app)
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):      # a Windows console in a legacy code page must not die on a file name
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    try:
        return args.fn(args)
    except (OSError, ffio.FFmpegError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
