import argparse
import json
from pathlib import Path

from .generator import generate


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate metadata-only synthetic traffic")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--size", choices=("small", "standard"), default="small")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    logs, truth = generate(seed=args.seed, days=args.days, size=args.size)
    args.out.mkdir(parents=True, exist_ok=True)
    logs_payload = [log.model_dump(mode="json") for log in logs]
    (args.out / "logs.json").write_text(
        json.dumps(logs_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.out / "ground_truth.json").write_text(
        json.dumps(truth.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "requests": len(logs),
                "labeled_requests": len({label.request_id for label in truth.labels}),
                "size": args.size,
                "output": str(args.out),
            },
            indent=2,
        )
    )
