from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overcall.main import create_app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the FastAPI OpenAPI document.")
    parser.add_argument("--output", type=Path, help="Optional file to write instead of stdout.")
    parser.add_argument("--format", choices=("json", "yaml"), default="yaml")
    args = parser.parse_args()

    document = create_app().openapi()
    rendered = (
        json.dumps(document, indent=2)
        if args.format == "json"
        else yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
    )
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)


if __name__ == "__main__":
    main()
