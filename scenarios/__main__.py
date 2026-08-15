"""
scenarios CLI.

    python3 -m scenarios --list
    python3 -m scenarios run simple_motor_starter
    python3 -m scenarios run simple_motor_starter --out /tmp/out.qet
"""
from __future__ import annotations

import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from scenarios import simple_motor_starter, motor_starter_with_breaker  # noqa: E402

REGISTRY = {
    "simple_motor_starter": simple_motor_starter.run,
    "motor_starter_with_breaker": motor_starter_with_breaker.run,
}


def main() -> int:
    ap = argparse.ArgumentParser(prog="scenarios")
    ap.add_argument("--list", action="store_true", help="list available scenarios")
    sub = ap.add_subparsers(dest="cmd")

    run_p = sub.add_parser("run", help="run a named scenario")
    run_p.add_argument("name", choices=sorted(REGISTRY))
    run_p.add_argument("--out", default=None, help="where to save the resulting project")

    args = ap.parse_args()

    if args.list or args.cmd is None:
        print("Available scenarios:")
        for name in sorted(REGISTRY):
            fn = REGISTRY[name]
            doc = (fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else ""
            print(f"  {name:<28} {doc}")
        return 0

    if args.cmd == "run":
        fn = REGISTRY[args.name]
        result = fn(out_path=args.out)
        print(f"\n{'PASS' if result.passed else 'FAIL'}: {result.name}")
        print(f"  {result.detail}")
        if result.counts:
            print(f"  counts: {result.counts}")
        return 0 if result.passed else 1

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
