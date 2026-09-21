from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="av2-converter",
        description="Convert video to AV2 and audio to xHE-AAC.",
    )
    parser.add_argument(
        "--convert",
        metavar="FILE",
        help="Convert FILE without opening the GUI",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Output path for --convert",
    )
    args, rest = parser.parse_known_args(argv)

    if args.convert:
        from av2converter.convert import convert_file

        convert_file(
            args.convert,
            output=args.output,
            log=lambda line: print(line, flush=True),
        )
        return 0

    from av2converter.app import run_gui

    return run_gui(rest)


if __name__ == "__main__":
    raise SystemExit(main())
