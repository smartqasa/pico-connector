# ================================================================
# CONFIG MODULE — Handles PicoLink configuration and validation
# ================================================================
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

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
    Defaults are applied from THREE layers:
        1. Hardcoded dataclass defaults (lowest priority)
        2. Global defaults block from configuration.yaml
        3. Per-device overrides in configuration.yaml (highest priority)

    IMPORTANT:
    Device "type" / behavior is NO LONGER derived from YAML "profile".
    The controller now auto-detects behavior from Lutron event payload:
        data["type"] → "Pico3ButtonRaiseLower" / "Pico4ButtonScene" / etc.
    """

    device_id: str
    behavior: str | None = None

    # Primary entities controlled by the device
    entities: List[str] = field(default_factory=list)

    # Domain of the controlled entity (light, fan, cover, media_player)
    domain: str = "light"

    # Timing / ramp parameters
    hold_time_ms: int = 250
    step_time_ms: int = 250
    step_pct: int = 10
    low_pct: int = 1
    on_pct: int = 100

    # Fan parameters
    fan_speeds: int = 6

    # Middle button (STOP) formatted action list
    middle_button: List[Dict[str, Any]] = field(default_factory=list)

    # Four-button scene actions (if applicable)
    buttons: Dict[str, List[Dict]] = field(default_factory=dict)

    # ------------------------------------------------------------
    # VALIDATION — MINIMAL NOW THAT PROFILES ARE GONE
    # ------------------------------------------------------------
    def validate(self) -> None:

        # Entities must be present for all devices EXCEPT 4-button:
        if not self.entities and not self.buttons:
            raise ValueError(
                f"Device {self.device_id} has no 'entities' AND no 'buttons'. "
                "At least one must be provided."
            )

        allowed_domains = {"light", "fan", "cover", "media_player"}
        if self.domain not in allowed_domains:
            raise ValueError(
                f"Invalid domain '{self.domain}' for device {self.device_id}. "
                f"Must be one of {allowed_domains}"
            )

        # Nothing else to validate now.


# ================================================================
# CONFIG PARSER — MERGES DEFAULTS + DEVICE OVERRIDES
# ================================================================
def parse_pico_config(raw: Dict[str, Any]) -> PicoConfig:

    if "device_id" not in raw:
        raise ValueError("Missing required key 'device_id'")

    device_id = raw["device_id"]

    # entities or legacy entity_id:
    entities = raw.get("entities") or raw.get("entity_id") or []
    if isinstance(entities, str):
        entities = [entities]

    conf = PicoConfig(
        device_id=device_id,
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

    # -------------------------------------------------------------
    # DEBUG: before rewrite (if any)
    # -------------------------------------------------------------
    _LOGGER.debug(
        "PICO[%s] RAW middle_button BEFORE REWRITE → %s",
        device_id,
        raw.get("middle_button"),
    )

    # ============================================================
    # OPTIONAL TARGET AUTO-INJECTION
    # Only rewrite if user explicitly used 'device_entity'.
    # No more profile gating — controller behavior handles STOP logic.
    # ============================================================

    fixed_actions: List[Dict[str, Any]] = []

    for action in conf.middle_button:

        if not isinstance(action, dict):
            fixed_actions.append(action)
            continue

        new_action = dict(action)

        target = new_action.get("target")
        if isinstance(target, dict):
            eid = target.get("entity_id")

            if isinstance(eid, str) and eid == "device_entity":
                new_action["target"] = {"entity_id": conf.entities}

            elif isinstance(eid, list) and "device_entity" in eid:
                replaced: list[str] = []
                for x in eid:
                    if x == "device_entity":
                        replaced.extend(conf.entities)
                    else:
                        replaced.append(x)
                new_action["target"] = {"entity_id": replaced}

        fixed_actions.append(new_action)

    conf.middle_button = fixed_actions

    # -------------------------------------------------------------
    # DEBUG: after rewrite
    # -------------------------------------------------------------
    _LOGGER.debug(
        "PICO[%s] FINAL middle_button AFTER REWRITE → %s",
        device_id,
        conf.middle_button,
    )

    # Validate and return
    conf.validate()
    return conf
