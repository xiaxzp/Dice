from __future__ import annotations

import argparse
import json
import sys

from .roller import DiceRoller


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Platform-independent TRPG dice roller")
    parser.add_argument("expression", nargs="?", default="d100")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    result = DiceRoller().roll(args.expression)
    if args.as_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(result.render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
