"""Fail when the running API drifts from the committed contract/openapi.yaml.

Compares the structural contract (paths, methods, response status codes, schema property
names, types and required lists). Run with --write to regenerate after an intended change.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overcall.main import create_app  # noqa: E402

CONTRACT = ROOT / "contract" / "openapi.yaml"
HTTP_METHODS = {"get", "put", "post", "delete", "patch"}


def _type(prop: dict[str, Any]) -> str:
    if "$ref" in prop:
        return prop["$ref"].rsplit("/", 1)[-1]
    for key in ("anyOf", "oneOf"):
        if key in prop:
            return "|".join(sorted(_type(item) for item in prop[key]))
    if prop.get("type") == "array":
        return f"array<{_type(prop.get('items', {}))}>"
    return str(prop.get("enum") or prop.get("type"))


def summarize(document: dict[str, Any]) -> dict[str, Any]:
    operations = {
        f"{method.upper()} {path}": sorted(operation.get("responses", {}))
        for path, item in document.get("paths", {}).items()
        for method, operation in item.items()
        if method in HTTP_METHODS
    }
    schemas = {
        name: {
            "required": sorted(schema.get("required", [])),
            "properties": {
                key: _type(value) for key, value in sorted(schema.get("properties", {}).items())
            },
        }
        for name, schema in document.get("components", {}).get("schemas", {}).items()
    }
    return {
        "operations": dict(sorted(operations.items())),
        "schemas": dict(sorted(schemas.items())),
    }


def diff(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for section in ("operations", "schemas"):
        for key in sorted(set(expected[section]) | set(actual[section])):
            if key not in actual[section]:
                problems.append(f"{section}: {key} is in the contract but not implemented")
            elif key not in expected[section]:
                problems.append(f"{section}: {key} is implemented but not in the contract")
            elif expected[section][key] != actual[section][key]:
                problems.append(
                    f"{section}: {key} differs\n  contract: {expected[section][key]}\n"
                    f"  actual:   {actual[section][key]}"
                )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Regenerate contract/openapi.yaml")
    args = parser.parse_args()

    actual_document = create_app().openapi()
    if args.write:
        CONTRACT.write_text(
            yaml.safe_dump(actual_document, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        print(f"Wrote {CONTRACT}")
        return 0
    if not CONTRACT.exists():
        print(f"{CONTRACT} is missing. Run with --write.")
        return 1

    expected = summarize(yaml.safe_load(CONTRACT.read_text(encoding="utf-8")))
    problems = diff(expected, summarize(actual_document))
    if problems:
        print("API contract drift detected:")
        print("\n".join(problems))
        return 1
    print(f"API matches the contract ({len(expected['operations'])} operations).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
