from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .const import PROFILE_FIVE_BUTTON, PROFILE_PADDLE, PROFILE_TWO_BUTTON

from __init__ import _LOGGER


@dataclass
class PicoConfig:
    device_id: str
    profile: str
    entities: list[str]
    hold_time_ms: int = 300
    step_time_ms: int = 200
    step_pct: int = 5
    on_pct: int = 100

    def validate(self) -> None:
        """Sanity checks based on profile type."""
        if self.profile == PROFILE_TWO_BUTTON:
            # Two-button Picos have no holds and no ramp
            if self.hold_time_ms != 0:
                _LOGGER.debug(
                    "Ignoring hold_time_ms for two-button Pico %s; holds not supported",
                    self.device_id,
                )
            if self.step_time_ms != 0 or self.step_pct != 0:
                _LOGGER.debug(
                    "Ignoring step ramp settings for two-button Pico %s; ramp not supported",
                    self.device_id,
                )


def parse_pico_config(raw: Dict[str, Any]) -> PicoConfig:
    """Validate and normalize a single YAML config entry."""
    try:
        device_id = raw["device_id"]
    except KeyError as err:
        raise ValueError("missing required key 'device_id'") from err

    entities = raw.get("entities") or raw.get("entity_id") or []
    if not isinstance(entities, list) or not entities:
        raise ValueError("entities must be a non-empty list of light entity_ids")

    profile = str(raw.get("profile", PROFILE_PADDLE)).lower()
    if profile not in (PROFILE_PADDLE, PROFILE_FIVE_BUTTON):
        raise ValueError("profile must be 'paddle' or 'five_button'")

    hold_time_ms = int(raw.get("hold_time_ms", 250))            # default 250 ms
    step_pct = int(raw.get("step_pct", 5))                      # default 5%
    step_time_ms = int(raw.get("step_time_ms", 200))            # default 200 ms
    on_pct = int(raw.get("on_pct", 100))  # default 100%

    if hold_time_ms < 50:
        raise ValueError("hold_time_ms must be >= 50 ms")
    if not (1 <= step_pct <= 100):
        raise ValueError("step_pct must be between 1 and 100")
    if step_time_ms < 50:
        raise ValueError("step_time_ms must be >= 50 ms")
    if not (1 <= on_pct <= 100):
        raise ValueError("on_pct must be between 1 and 100")

    return PicoConfig(
        device_id=device_id,
        entities=entities,
        profile=profile,
        hold_time_ms=hold_time_ms,
        step_pct=step_pct,
        step_time_ms=step_time_ms,
        on_pct=on_pct,
    )
