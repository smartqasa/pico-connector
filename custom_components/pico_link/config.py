# ================================================================
# CONFIG MODULE — Handles PicoLink configuration and validation
# ================================================================
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from homeassistant.helpers import device_registry as dr
import logging

_LOGGER = logging.getLogger(__name__)


# ================================================================
# DEVICE CONFIGURATION MODEL (DATACLASS)
# ================================================================
@dataclass
class PicoConfig:
    """
    A normalized configuration object for a single Pico device.

    IMPORTANT:
    Device behavior is auto-detected dynamically from the Lutron
    event payload ("type": "Pico3ButtonRaiseLower", etc.).
    YAML no longer controls "profile" or type.
    """

    # Resolved device_id (UUID from HA device registry)
    device_id: str

    # Auto-detected at runtime by controller (optional)
    behavior: str | None = None

    # Entities controlled by this Pico
    entities: List[str] = field(default_factory=list)

    # Domain (light, fan, cover, media_player)
    domain: str = "light"

    # Timing / ramp parameters
    hold_time_ms: int = 250
    step_time_ms: int = 500
    step_pct: int = 10
    low_pct: int = 1
    on_pct: int = 100

    # Fan
    fan_speeds: int = 6

    # STOP button custom action
    middle_button: List[Dict[str, Any]] = field(default_factory=list)

    # Four-button scene actions (if applicable)
    buttons: Dict[str, List[Dict]] = field(default_factory=dict)

    # ------------------------------------------------------------
    # VALIDATION — Very minimal now that profiles are removed
    # ------------------------------------------------------------
    def validate(self) -> None:

        # Must have either entities or buttons
        if not self.entities and not self.buttons:
            raise ValueError(
                f"Device {self.device_id} has no 'entities' OR 'buttons'. "
                "At least one must be provided."
            )

        allowed_domains = {"light", "fan", "cover", "media_player"}
        if self.domain not in allowed_domains:
            raise ValueError(
                f"Invalid domain '{self.domain}' for device {self.device_id}. "
                f"Must be one of: {allowed_domains}"
            )


# ================================================================
# DEVICE LOOKUP — name_by_user FIRST, then name
# ================================================================
def lookup_device_id(hass, name: str) -> str | None:
    """Return device_id matching name_by_user first, then name."""
    dev_reg = dr.async_get(hass)

    # Priority 1: user-assigned name
    for device in dev_reg.devices.values():
        if device.name_by_user == name:
            return device.id

    # Priority 2: integration-provided name
    for device in dev_reg.devices.values():
        if device.name == name:
            return device.id

    return None


# ================================================================
# CONFIG PARSER — MERGES DEFAULTS + DEVICE OVERRIDES
# ================================================================
def parse_pico_config(hass, raw: Dict[str, Any]) -> PicoConfig:
    """
    device_id priority:
        1. YAML device_id (explicit)
        2. device lookup from name_by_user / name
    """

    # ------------------------------------------------------------
    # Resolve device_id
    # ------------------------------------------------------------
    device_id = raw.get("device_id")

    if not device_id:
        name = raw.get("name")
        if not name:
            raise ValueError(
                "Each Pico device must define either 'device_id' or 'name'."
            )

        device_id = lookup_device_id(hass, name)
        if not device_id:
            raise ValueError(
                f"No device found with name_by_user or name '{name}'."
            )

        _LOGGER.debug(
            "Resolved Pico '%s' → device_id %s",
            name,
            device_id,
        )

    # ------------------------------------------------------------
    # Entity normalization
    # ------------------------------------------------------------
    entities = raw.get("entities") or raw.get("entity_id") or []
    if isinstance(entities, str):
        entities = [entities]

    # ------------------------------------------------------------
    # Build PicoConfig
    # ------------------------------------------------------------
    conf = PicoConfig(
        device_id=device_id,
        entities=entities,
        domain=str(raw.get("domain", "light")).lower(),
        hold_time_ms=int(raw.get("hold_time_ms", 250)),
        step_time_ms=int(raw.get("step_time_ms", 500)),
        step_pct=int(raw.get("step_pct", 10)),
        low_pct=int(raw.get("low_pct", 1)),
        on_pct=int(raw.get("on_pct", 100)),
        fan_speeds=int(raw.get("fan_speeds", 6)),
        middle_button=raw.get("middle_button") or [],
        buttons=raw.get("buttons", {}),
    )

    # ------------------------------------------------------------
    # DEBUG
    # ------------------------------------------------------------
    _LOGGER.debug(
        "PICO[%s] RAW middle_button BEFORE REWRITE → %s",
        device_id,
        raw.get("middle_button"),
    )

    # ============================================================
    # AUTO-INJECT ENTITY: replace entity_id: device_entity
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

            # Replace a single device_entity
            if isinstance(eid, str) and eid == "device_entity":
                new_action["target"] = {"entity_id": conf.entities}

            # Replace inside a list
            elif isinstance(eid, list) and "device_entity" in eid:
                new_list = []
                for x in eid:
                    if x == "device_entity":
                        new_list.extend(conf.entities)
                    else:
                        new_list.append(x)
                new_action["target"] = {"entity_id": new_list}

        fixed_actions.append(new_action)

    conf.middle_button = fixed_actions

    _LOGGER.debug(
        "PICO[%s] FINAL middle_button AFTER REWRITE → %s",
        device_id,
        conf.middle_button,
    )

    # ------------------------------------------------------------
    # Validate and return
    # ------------------------------------------------------------
    conf.validate()
    return conf
