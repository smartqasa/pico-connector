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

    domain: str = "light"

    hold_time_ms: int = 250
    step_time_ms: int = 50
    step_pct: int = 10
    low_pct: int = 1
    on_pct: int = 100

    fan_speeds: int = 6

    middle_button: List[Dict[str, Any]] = field(default_factory=list)
    buttons: Dict[str, List[Dict]] = field(default_factory=dict)

    # ------------------------------------------------------------
    # VALIDATION — Ensures a proper Pico configuration
    # ------------------------------------------------------------
    def validate(self) -> None:

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

        # FOUR-BUTTON special case
        if self.profile == PROFILE_FOUR_BUTTON:
            if not isinstance(self.buttons, dict):
                raise ValueError("'buttons' must be a dict for four_button profile")
            return

        # All other profiles require entities
        if not self.entities:
            raise ValueError(
                "entities must be provided for paddle, five_button, and two_button profiles"
            )

        allowed_domains = {"light", "fan", "cover", "media_player"}
        if self.domain not in allowed_domains:
            raise ValueError(
                f"Invalid domain '{self.domain}'. Must be one of {allowed_domains}"
            )

        # Two-button: no hold/ramp
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

    if "device_id" not in raw:
        raise ValueError("Missing required key 'device_id'")

    device_id = raw["device_id"]
    profile = str(raw.get("profile", PROFILE_PADDLE)).lower()

    # entities or legacy entity_id:
    entities = raw.get("entities") or raw.get("entity_id") or []
    if isinstance(entities, str):
        entities = [entities]

    conf = PicoConfig(
        device_id=device_id,
        profile=profile,
        entities=entities,
        domain=str(raw.get("domain", "light")).lower(),
        hold_time_ms=int(raw.get("hold_time_ms", 250)),
        step_time_ms=int(raw.get("step_time_ms", 50)),
        step_pct=int(raw.get("step_pct", 10)),
        low_pct=int(raw.get("low_pct", 1)),
        on_pct=int(raw.get("on_pct", 100)),
        fan_speeds=int(raw.get("fan_speeds", 6)),
        middle_button=raw.get("middle_button") or [],
        buttons=raw.get("buttons", {}),
    )

    # ============================================================
    # AUTO-INJECT / REPLACE TARGET ENTITY FOR MIDDLE BUTTON
    # ============================================================
    #
    # NEW LOGIC:
    # If an action defines:
    #
    #     target:
    #       entity_id: device_entity
    #
    # Then replace "device_entity" with the actual device's entities.
    #
    # Works for:
    #   - entity_id: "device_entity"
    #   - entity_id: ["device_entity"]
    #   - entity_id: ["device_entity", "other"]
    #
    # ============================================================

    if conf.profile == PROFILE_FIVE_BUTTON and conf.entities:

        fixed_actions = []
        for action in conf.middle_button:

            if not isinstance(action, dict):
                fixed_actions.append(action)
                continue

            new_action = dict(action)

            target = new_action.get("target")
            if isinstance(target, dict):

                eid = target.get("entity_id")

                # Case 1: entity_id == "device_entity"
                if isinstance(eid, str) and eid == "device_entity":
                    new_action["target"] = {"entity_id": conf.entities}

                # Case 2: entity_id is list containing "device_entity"
                elif isinstance(eid, list) and "device_entity" in eid:
                    replaced = []
                    for x in eid:
                        if x == "device_entity":
                            replaced.extend(conf.entities)  # expand inline
                        else:
                            replaced.append(x)
                    new_action["target"] = {"entity_id": replaced}



            fixed_actions.append(new_action)

        conf.middle_button = fixed_actions

    # Final correctness check
    conf.validate()
    return conf

