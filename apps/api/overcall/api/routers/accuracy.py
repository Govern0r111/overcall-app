from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from ..schemas import Accuracy, AccuracyDataset, AccuracyRule

router = APIRouter(tags=["accuracy"])

REPORT_PATH = Path(__file__).resolve().parents[5] / "validation" / "reports" / "synthetic.json"

SYNTHETIC_LABEL = "Synthetic data (circular)"
SYNTHETIC_NOTE = (
    "Generated from the same rules, so high scores are expected and are not evidence "
    "of real accuracy."
)
REAL_LABEL = "Real-traffic fixtures (hand-labelled)"
REAL_NOTE = "Not measured yet. These are added after running real sample apps through the proxy."


def _load_report() -> dict[str, Any] | None:
    try:
        value = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _synthetic_dataset() -> AccuracyDataset:
    report = _load_report()
    if report is None:
        return AccuracyDataset(
            id="synthetic",
            label=SYNTHETIC_LABEL,
            note=SYNTHETIC_NOTE,
            generated_at=None,
            requests=0,
            rules=[],
        )
    generated_at = report.get("generated_at")
    return AccuracyDataset(
        id="synthetic",
        label=SYNTHETIC_LABEL,
        note=SYNTHETIC_NOTE,
        generated_at=datetime.fromisoformat(generated_at) if generated_at else None,
        requests=int(report.get("requests", 0)),
        rules=[
            AccuracyRule(
                rule_id=item["rule_id"],
                tier=item["tier"],
                positives=item["positives"],
                flagged=item["flagged"],
                true_positives=item["true_positives"],
                precision=item.get("precision"),
                recall=item.get("recall"),
                false_positives_on_hard_negatives=item.get("false_positives_on_hard_negatives"),
            )
            for item in report.get("rules", [])
        ],
    )


@router.get("/accuracy", response_model=Accuracy)
async def get_accuracy() -> Accuracy:
    real = AccuracyDataset(
        id="real",
        label=REAL_LABEL,
        note=REAL_NOTE,
        generated_at=None,
        requests=0,
        rules=[],
    )
    return Accuracy(datasets=[_synthetic_dataset(), real])
