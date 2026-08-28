from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "executive-os.toml"


@dataclass(frozen=True)
class TriageConfig:
    timezone: str
    p0_window_minutes: int
    p1_window_hours: int
    significant_amount_mad: float
    large_amount_mad: float


@dataclass(frozen=True)
class AppConfig:
    raw: dict[str, Any]
    triage: TriageConfig


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path or os.environ.get("EXECUTIVE_OS_CONFIG", DEFAULT_CONFIG_PATH))
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)

    triage = raw.get("triage", {})
    required = {
        "timezone",
        "p0_window_minutes",
        "p1_window_hours",
        "significant_amount_mad",
        "large_amount_mad",
    }
    missing = sorted(required - triage.keys())
    if missing:
        raise ValueError(f"Missing triage config keys: {', '.join(missing)}")

    return AppConfig(
        raw=raw,
        triage=TriageConfig(
            timezone=str(triage["timezone"]),
            p0_window_minutes=int(triage["p0_window_minutes"]),
            p1_window_hours=int(triage["p1_window_hours"]),
            significant_amount_mad=float(triage["significant_amount_mad"]),
            large_amount_mad=float(triage["large_amount_mad"]),
        ),
    )
