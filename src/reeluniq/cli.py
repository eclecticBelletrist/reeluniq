"""Command line: `reeluniq make VIDEO`."""

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
