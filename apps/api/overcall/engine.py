import asyncio
from datetime import datetime, timezone
from typing import List

from .db import issues_col, logs_col, runs_col
from .models import Issue, RequestLog
from .rules import RULES
from .rules.base import RuleContext
from .settings_store import AppSettings, Windows, get_settings
from .synthetic.truth import GroundTruth

SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}
MAX_LOGS = 200_000
_state = {"version": 1, "clean_version": 0}
_lock = asyncio.Lock()
data_lock = asyncio.Lock()


def mark_dirty():
    _state["version"] += 1


def window_days(logs: List[RequestLog]) -> float:
    return max(1.0, (logs[-1].timestamp - logs[0].timestamp).total_seconds() / 86400) if logs else 1.0


def rule_active(rule, s: AppSettings) -> bool:
    return s.rules.get(rule.id, True) and (rule.tier < 3 or s.experimental_enabled)


def sample(l: RequestLog) -> dict:
    return l.model_dump(include={
        "id", "timestamp", "method", "endpoint", "status", "latency_ms", "req_size", "resp_size",
        "req_hash", "cost_usd", "model", "caller", "prompt_tokens", "completion_tokens",
    })


def to_issue(rule, f, ctx: RuleContext, now) -> Issue:
    return Issue(
        rule_id=rule.id, rule_name=rule.name, issue_type=f.issue_type, tier=rule.tier, experimental=rule.tier == 3,
        provider=f.provider, endpoint=f.endpoint, severity=f.severity, title=f.title, summary=f.summary,
        explanation=f.explanation, suggested_fix=f.suggested_fix,
        affected_requests=[l.id for l in f.affected[:200]], affected_count=len(f.affected),
        estimated_savings_usd=round(f.estimated_savings, 6),
        projected_monthly_usd=round(ctx.monthly(f.estimated_savings), 4),
        confidence=f.confidence, sample_requests=[sample(l) for l in f.affected[:5]], detected_at=now,
    )


async def load_logs(query=None) -> List[RequestLog]:
    docs = await logs_col.find(query or {}).sort("timestamp", 1).to_list(MAX_LOGS)
    return [RequestLog.from_record(d) for d in docs]


def build_summary(logs, issues, trusted, experimental, days, now) -> dict:
    trend = {}
    for l in logs:
        d = trend.setdefault(l.timestamp.date().isoformat(), {"date": l.timestamp.date().isoformat(), "cost_usd": 0.0, "waste_usd": 0.0})
        d["cost_usd"] += l.cost_usd
        d["waste_usd"] += trusted.get(l.id, 0.0)
    total = sum(l.cost_usd for l in logs)
    saved = sum(trusted.values())
    extra = sum(v for k, v in experimental.items() if k not in trusted)
    counts = {s: sum(1 for i in issues if i.severity == s) for s in SEVERITY_RANK}
    sources = {}
    for l in logs:
        sources[l.source] = sources.get(l.source, 0) + 1
    return {
        "_id": "latest", "ran_at": now, "has_data": bool(logs), "request_count": len(logs),
        "flagged_request_count": len(trusted), "window_days": round(days, 3),
        "total_cost_usd": round(total, 6), "projected_monthly_cost_usd": round(total * 30 / days, 4),
        "window_savings_usd": round(saved, 6), "projected_monthly_usd": round(saved * 30 / days, 4),
        "waste_pct": round(100 * saved / total, 2) if total else 0.0,
        "experimental_projected_monthly_usd": round(extra * 30 / days, 4),
        "issue_counts": counts, "sources": sources,
        "trend": [{**v, "cost_usd": round(v["cost_usd"], 6), "waste_usd": round(v["waste_usd"], 6)} for v in sorted(trend.values(), key=lambda x: x["date"])],
    }


async def run_detection() -> dict:
    version = _state["version"]
    s = await get_settings()
    logs = await load_logs()
    days = window_days(logs)
    ctx = RuleContext(w=s.windows, window_days=days)
    now = datetime.now(timezone.utc)
    issues, trusted, experimental = [], {}, {}
    for rule in RULES:
        if not logs or not rule_active(rule, s):
            continue
        for f in rule.detect(logs, ctx):
            issues.append(to_issue(rule, f, ctx, now))
            target = experimental if rule.tier == 3 else trusted
            for rid, w in f.waste_by_request.items():
                target[rid] = max(target.get(rid, 0.0), w)
    issues.sort(key=lambda i: (SEVERITY_RANK[i.severity], -i.projected_monthly_usd))
    await issues_col.delete_many({})
    if issues:
        await issues_col.insert_many([i.to_record() for i in issues])
    summary = build_summary(logs, issues, trusted, experimental, days, now)
    await runs_col.replace_one({"_id": "latest"}, summary, upsert=True)
    _state["clean_version"] = max(_state["clean_version"], version)
    return summary


async def ensure_fresh():
    async with _lock:
        if _state["clean_version"] < _state["version"]:
            await run_detection()


def evaluate(logs: list[RequestLog], windows: Windows, ground_truth: GroundTruth) -> list:
    ctx = RuleContext(w=windows, window_days=window_days(logs))
    out = []
    for rule in RULES:
        flagged = set()
        for f in rule.detect(logs, ctx):
            flagged |= set(f.waste_by_request)
        truth = ground_truth.request_ids(rule.id)
        hard_negatives = ground_truth.request_ids(rule.id, "hard_negative")
        tp = len(flagged & truth)
        false_positive_hard_negatives = len(flagged & hard_negatives)
        out.append({
            "rule_id": rule.id, "rule_name": rule.name, "tier": rule.tier,
            "ground_truth": len(truth), "flagged": len(flagged), "true_positives": tp,
            "hard_negatives": len(hard_negatives),
            "false_positives_on_hard_negatives": false_positive_hard_negatives,
            "precision": round(tp / len(flagged), 4) if flagged else (1.0 if not truth else 0.0),
            "recall": round(tp / len(truth), 4) if truth else 1.0,
        })
    return out
