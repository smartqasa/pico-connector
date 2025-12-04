from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .const import (
    PROFILE_FIVE_BUTTON,
    PROFILE_PADDLE,
    PROFILE_TWO_BUTTON,
    PROFILE_FOUR_BUTTON,
)

import logging

_LOGGER = logging.getLogger(__name__)


@dataclass
class PicoConfig:
    device_id: str
    profile: str
    entities: List[str]

    # Only applies to paddle, five_button, two_button
    domain: str = "light"

    hold_time_ms: int = 300
    step_time_ms: int = 200
    step_pct: int = 5
    on_pct: int = 100

    # Four-button per-button actions
    buttons: Dict[str, List[Dict]] = field(default_factory=dict)

    def validate(self) -> None:
        """Sanity checks based on profile type."""

        # Allowed profile list
        allowed_profiles = {
            PROFILE_PADDLE,
            PROFILE_FIVE_BUTTON,
            PROFILE_TWO_BUTTON,
            PROFILE_FOUR_BUTTON,
        }

        if self.profile not in allowed_profiles:
            raise ValueError(
                f"Invalid profile '{self.profile}'. Must be one of: {allowed_profiles}"
            )

        # -------------------------------------------------------
        # FOUR BUTTON PROFILE: does not use domain or entities
        # -------------------------------------------------------
        if self.profile == PROFILE_FOUR_BUTTON:
            if not isinstance(self.buttons, dict):
                raise ValueError("'buttons' must be a dict for four_button profile")

            # entities & domain not required for four_button
            return

        # -------------------------------------------------------
        # ALL OTHER PROFILES REQUIRE DOMAIN + ENTITIES
        # -------------------------------------------------------
        if not self.entities:
            raise ValueError("entities must be provided for paddle, five_button, and two_button profiles")

        allowed_domains = {"light", "fan", "cover"}
        if self.domain not in allowed_domains:
            raise ValueError(
                f"Invalid domain '{self.domain}'. Must be one of: {allowed_domains}"
            )

        # -------------------------------------------------------
        # TWO BUTTON PROFILE IGNORES HOLD & RAMP CONFIG
        # -------------------------------------------------------
        if self.profile == PROFILE_TWO_BUTTON:
            if self.hold_time_ms != 0:
                _LOGGER.debug(
                    "Ignoring hold_time_ms for two-button Pico %s; holds not supported",
                    self.device_id,
                )
            if self.step_time_ms != 0 or self.step_pct != 0:
                _LOGGER.debug(
                    "Ignoring ramp settings for two-button Pico %s; ramp not supported",
                    self.device_id,
                )


def parse_pico_config(raw: Dict[str, Any]) -> PicoConfig:
    """Validate and normalize a single YAML config entry."""

    if "device_id" not in raw:
        raise ValueError("missing required key 'device_id'")
    device_id = raw["device_id"]

    profile = str(raw.get("profile", PROFILE_PADDLE)).lower()

    # Entities may not exist for FOUR BUTTON
    entities = raw.get("entities") or raw.get("entity_id") or []

    domain = str(raw.get("domain", "light")).lower()

    hold_time_ms = int(raw.get("hold_time_ms", 300))
    step_time_ms = int(raw.get("step_time_ms", 200))
    step_pct = int(raw.get("step_pct", 5))
    on_pct = int(raw.get("on_pct", 100))

    buttons = raw.get("buttons", {})

    conf = PicoConfig(
        device_id=device_id,
        profile=profile,
        entities=entities,
        domain=domain,
        hold_time_ms=hold_time_ms,
        step_time_ms=step_time_ms,
        step_pct=step_pct,
        on_pct=on_pct,
        buttons=buttons,
    )

    conf.validate()
    return conf
