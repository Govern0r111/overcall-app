from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

PRICING_DIR = Path(__file__).resolve().parents[1] / "overcall" / "pricing" / "files"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Warn when active provider pricing has not been reviewed recently."
    )
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--max-age-days", type=int, default=90)
    args = parser.parse_args()
    if args.max_age_days < 1:
        parser.error("--max-age-days must be greater than zero")

    has_stale = False
    for path in sorted(PRICING_DIR.glob("*/*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            retrieved_at = date.fromisoformat(data["retrieved_at"])
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            print(f"ERROR: invalid pricing metadata in {path}: {exc}", file=sys.stderr)
            return 1
        age = (args.as_of - retrieved_at).days
        if age < 0:
            print(f"ERROR: {path} has a future retrieved_at date.", file=sys.stderr)
            return 1
        if age > args.max_age_days:
            has_stale = True
            print(
                f"WARNING: {path.relative_to(PRICING_DIR)} is {age} days old "
                f"(maximum {args.max_age_days})."
            )
        else:
            print(f"OK: {path.relative_to(PRICING_DIR)} reviewed {age} days ago.")
    return 0 if not has_stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
