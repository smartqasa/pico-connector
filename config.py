from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .const import PROFILE_FIVE_BUTTON, PROFILE_PADDLE


@dataclass
class PicoConfig:
    """Runtime config for a single Pico controller."""

    pico_device_id: str
    entities: List[str]
    profile: str  # "paddle" or "five_button"
    hold_time_ms: int
    step_pct: int
    step_time_ms: int
    brightness_on_pct: int


def parse_pico_config(raw: Dict[str, Any]) -> PicoConfig:
    """Validate and normalize a single YAML config entry."""
    try:
        pico_device_id = raw["pico_device_id"]
    except KeyError as err:
        raise ValueError("missing required key 'pico_device_id'") from err

    entities = raw.get("entities") or raw.get("entity_id") or []
    if not isinstance(entities, list) or not entities:
        raise ValueError("entities must be a non-empty list of light entity_ids")

    profile = str(raw.get("profile", PROFILE_PADDLE)).lower()
    if profile not in (PROFILE_PADDLE, PROFILE_FIVE_BUTTON):
        raise ValueError("profile must be 'paddle' or 'five_button'")

    hold_time_ms = int(raw.get("hold_time_ms", 250))
    step_pct = int(raw.get("step_pct", 5))              # default 5%
    step_time_ms = int(raw.get("step_time_ms", 200))    # default 200 ms
    brightness_on_pct = int(raw.get("brightness_on_pct", 100))

    if hold_time_ms < 50:
        raise ValueError("hold_time_ms must be >= 50 ms")
    if not (1 <= step_pct <= 100):
        raise ValueError("step_pct must be between 1 and 100")
    if step_time_ms < 50:
        raise ValueError("step_time_ms must be >= 50 ms")
    if not (1 <= brightness_on_pct <= 100):
        raise ValueError("brightness_on_pct must be between 1 and 100")

    return PicoConfig(
        pico_device_id=pico_device_id,
        entities=entities,
        profile=profile,
        hold_time_ms=hold_time_ms,
        step_pct=step_pct,
        step_time_ms=step_time_ms,
        brightness_on_pct=brightness_on_pct,
    )
