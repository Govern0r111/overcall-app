from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from .models import PricingFile, Provider

API_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_SCHEMA = API_ROOT.parents[1] / "contract" / "pricing.schema.json"
PRICING_FILES = Path(__file__).parent / "files"
PROVIDERS: tuple[Provider, ...] = ("openai", "stripe", "aws")


def _schema_validator(schema_path: Path) -> Draft202012Validator:
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not load pricing schema: {schema_path}") from exc
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def _validate_file(path: Path, provider: Provider, validator: Draft202012Validator) -> PricingFile:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not load pricing file: {path}") from exc

    errors = sorted(validator.iter_errors(raw), key=lambda error: list(error.absolute_path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "<root>"
        raise RuntimeError(f"Invalid pricing file {path} at {location}: {first.message}")
    try:
        entry = PricingFile.model_validate(raw)
    except ValidationError as exc:
        raise RuntimeError(f"Invalid pricing file {path}: {exc}") from exc
    if entry.provider != provider:
        raise RuntimeError(
            f"Pricing file {path} declares provider {entry.provider!r}, expected {provider!r}"
        )
    if entry.effective_from.date().isoformat() != entry.version:
        raise RuntimeError(f"Pricing file {path} version must match its effective_from date")
    return entry


@dataclass(frozen=True)
class PricingBook:
    versions: dict[Provider, tuple[PricingFile, ...]]

    @classmethod
    def from_directory(
        cls,
        pricing_dir: Path,
        schema_path: Path = CONTRACT_SCHEMA,
        providers: Iterable[Provider] = PROVIDERS,
    ) -> PricingBook:
        validator = _schema_validator(schema_path)
        version_map: dict[Provider, tuple[PricingFile, ...]] = {}
        for provider in providers:
            provider_dir = pricing_dir / provider
            if not provider_dir.is_dir():
                raise RuntimeError(
                    f"Missing pricing directory for provider {provider}: {provider_dir}"
                )
            paths = sorted(provider_dir.glob("*.json"))
            if not paths:
                raise RuntimeError(
                    f"No pricing versions found for provider {provider}: {provider_dir}"
                )
            entries = tuple(_validate_file(path, provider, validator) for path in paths)
            ordered = tuple(sorted(entries, key=lambda item: item.effective_from))
            timestamps = [entry.effective_from for entry in ordered]
            if len(timestamps) != len(set(timestamps)):
                raise RuntimeError(
                    f"Duplicate pricing effective_from timestamp for provider {provider}"
                )
            version_map[provider] = ordered
        return cls(version_map)

    def for_time(self, provider: str, at: datetime) -> PricingFile:
        if provider not in self.versions:
            raise ValueError(f"Unknown provider: {provider}")
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("Pricing lookup time must be timezone-aware")
        candidates = [
            version
            for version in self.versions[provider]
            if version.effective_from <= at.astimezone(UTC)
        ]
        if not candidates:
            raise ValueError(f"No {provider} pricing version was effective at {at.isoformat()}")
        return candidates[-1]


def load_default_pricing_book() -> PricingBook:
    return PricingBook.from_directory(PRICING_FILES)


DEFAULT_PRICING_BOOK = load_default_pricing_book()
