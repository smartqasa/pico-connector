# ================================================================
# CONFIG MODULE — Handles PicoLink configuration and validation
# ================================================================
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .const import (
    PROFILE_FIVE_BUTTON,
    PROFILE_FOUR_BUTTON,
    PROFILE_PADDLE,
    PROFILE_TWO_BUTTON,
)

import logging
_LOGGER = logging.getLogger(__name__)


# ================================================================
# DEVICE CONFIGURATION MODEL (DATACLASS)
# ================================================================
@dataclass
class PicoConfig:
    """
    A normalized configuration object for a single Pico device.

    NOTE:
    - Defaults are applied from THREE layers:
        1. Hardcoded dataclass defaults (lowest priority)
        2. Global defaults block from configuration.yaml
        3. Per-device overrides in configuration.yaml (highest priority)
    """

    device_id: str
    profile: str
    entities: List[str]

    # Behavior domain: determines ON/OFF actions, ramping, etc.
    domain: str = "light"

    # Hold/tap timing
    hold_time_ms: int = 250
    step_time_ms: int = 250
    step_pct: int = 10
    low_pct: int = 1        # minimum % permitted when dimming
    on_pct: int = 100       # "turn on" default brightness %

    # Optional fan behavior
    fan_speeds: int = 6     # valid: 4 or 6

    # Five-button middle-button action list
    middle_button: List[Dict[str, Any]] = field(default_factory=list)

    # Four-button "buttons:" action maps
    buttons: Dict[str, List[Dict]] = field(default_factory=dict)

    # ------------------------------------------------------------
    # VALIDATION — Ensures a proper Pico configuration
    # ------------------------------------------------------------
    def validate(self) -> None:
        """Validate the config according to Pico profile rules."""

        allowed_profiles = {
            PROFILE_PADDLE,
            PROFILE_FIVE_BUTTON,
            PROFILE_TWO_BUTTON,
            PROFILE_FOUR_BUTTON,
        }

        if self.profile not in allowed_profiles:
            raise ValueError(
                f"Invalid profile '{self.profile}'. Must be one of {allowed_profiles}"
            )

        # --------------------------------------------------------
        # FOUR-BUTTON PROFILE — special case
        # --------------------------------------------------------
        if self.profile == PROFILE_FOUR_BUTTON:
            # Four-button mode does NOT require domain or entities
            if not isinstance(self.buttons, dict):
                raise ValueError("'buttons' must be a dict for four_button profile")
            return

        # --------------------------------------------------------
        # ALL OTHER PROFILES REQUIRE ENTITIES
        # --------------------------------------------------------
        if not self.entities:
            raise ValueError(
                "entities must be provided for paddle, five_button, and two_button profiles"
            )

        allowed_domains = {"light", "fan", "cover", "media_player"}
        if self.domain not in allowed_domains:
            raise ValueError(
                f"Invalid domain '{self.domain}'. Must be one of {allowed_domains}"
            )

        # --------------------------------------------------------
        # TWO-BUTTON PROFILE — no ramping, no hold
        # --------------------------------------------------------
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


# ================================================================
# CONFIG PARSER — MERGES DEFAULTS + DEVICE OVERRIDES
# ================================================================
def parse_pico_config(raw: Dict[str, Any]) -> PicoConfig:
    """
    Convert a merged config dictionary into a PicoConfig object.

    IMPORTANT:
    - raw must ALREADY be merged: {**defaults, **device_override}
    - This function performs:
        → normalization
        → type conversion
        → validation (via PicoConfig.validate)
    """

    if "device_id" not in raw:
        raise ValueError("Missing required key 'device_id'")

    device_id = raw["device_id"]
    profile = str(raw.get("profile", PROFILE_PADDLE)).lower()

    # Accept "entities:" or legacy "entity_id:"
    entities = raw.get("entities") or raw.get("entity_id") or []
    if isinstance(entities, str):
        entities = [entities]

    conf = PicoConfig(
        device_id=device_id,
        profile=profile,
        entities=entities,
        domain=str(raw.get("domain", "light")).lower(),
        hold_time_ms=int(raw.get("hold_time_ms", 250)),
        step_time_ms=int(raw.get("step_time_ms", 250)),
        step_pct=int(raw.get("step_pct", 10)),
        low_pct=int(raw.get("low_pct", 1)),
        on_pct=int(raw.get("on_pct", 100)),
        fan_speeds=int(raw.get("fan_speeds", 6)),
        middle_button=raw.get("middle_button") or [],
        buttons=raw.get("buttons", {}),
    )

    # ------------------------------------------------------------
    # AUTO-INJECT TARGET INTO MIDDLE BUTTON ACTIONS (if missing)
    # ------------------------------------------------------------
    #
    # Only applies to profiles that use middle_button (five_button)
    # AND only if user did not manually supply "target".

    if conf.profile == PROFILE_FIVE_BUTTON and conf.entities:
        fixed_actions = []
        for action in conf.middle_button:
            if not isinstance(action, dict):
                continue  # ignore malformed items

            # If action already specifies target → leave it alone
            if "target" not in action:
                action = dict(action)  # shallow copy
                action["target"] = {"entity_id": conf.entities}

            fixed_actions.append(action)

        conf.middle_button = fixed_actions

    # Final correctness check
    conf.validate()
    return conf


