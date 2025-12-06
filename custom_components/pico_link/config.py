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

    Behavior (paddle, 5-button, 4-button, etc.) is auto-detected
    dynamically from the Lutron event payload type.

    YAML no longer controls behavior via "profile".
    """

    # Always a device registry ID
    device_id: str

    # Auto-detected at runtime by the controller
    behavior: str | None = None

    # Entities controlled by this Pico
    entities: List[str] = field(default_factory=list)

    # Domain of the primary controlled device
    # (must match one of the allowed domain groups)
    domain: str = "light"

    # Timing / ramp defaults (overridden by defaults: and device YAML)
    hold_time_ms: int = 250
    step_time_ms: int = 500
    step_pct: int = 10
    low_pct: int = 1
    on_pct: int = 100

    # Fan parameters
    fan_speeds: int = 6

    # STOP / middle button action list
    middle_button: List[Dict[str, Any]] = field(default_factory=list)

    # For 4-button scene remotes
    buttons: Dict[str, List[Dict]] = field(default_factory=dict)

    # ------------------------------------------------------------
    def validate(self) -> None:
        """Basic correctness checks."""

        # Must have something to control
        if not self.entities and not self.buttons:
            raise ValueError(
                f"Device {self.device_id} has no 'entities' OR 'buttons'. "
                "At least one must be provided."
            )

        # Alphabetized domain list
        allowed_domains = {"cover", "fan", "light", "media_player", "switch"}
        if self.domain not in allowed_domains:
            raise ValueError(
                f"Invalid domain '{self.domain}' for device {self.device_id}. "
                f"Must be one of: {allowed_domains}"
            )


# ================================================================
# LOOK UP device_id FROM name_by_user FIRST, THEN name
# ================================================================
def lookup_device_id(hass, name: str) -> str | None:
    dev_reg = dr.async_get(hass)

    # Highest priority → user-assigned name
    for dev in dev_reg.devices.values():
        if dev.name_by_user == name:
            return dev.id

    # Second priority → device registry name
    for dev in dev_reg.devices.values():
        if dev.name == name:
            return dev.id

    return None


# ================================================================
# CONFIG PARSER — MERGES DEFAULTS + DEVICE OVERRIDES
# ================================================================
def parse_pico_config(
    hass,
    defaults: Dict[str, Any],
    device_raw: Dict[str, Any],
) -> PicoConfig:
    """
    Build a fully merged and validated PicoConfig.
    - defaults: global defaults from YAML
    - device_raw: per-device configuration block
    """

    # ------------------------------------------------------------
    # Determine domain BEFORE merging defaults
    # ------------------------------------------------------------
    raw_domain = device_raw.get("domain")
    domain = str(raw_domain).lower() if raw_domain else None

    if domain is None:
        raise ValueError("Device must define 'domain'.")

    # ------------------------------------------------------------
    # Domain-aware merge: defaults → device_raw
    # ------------------------------------------------------------
    raw: Dict[str, Any] = {}

    for key, value in defaults.items():
        # Only LIGHT devices inherit default middle_button
        if key == "middle_button" and domain != "light":
            continue
        raw[key] = value

    # Overlay device configuration
    raw.update(device_raw)

    # ------------------------------------------------------------
    # Resolve device_id
    # ------------------------------------------------------------
    device_id = raw.get("device_id")

    if not device_id:
        name = raw.get("name")
        if not name:
            raise ValueError("Device must define 'device_id' or 'name'.")

        device_id = lookup_device_id(hass, name)
        if not device_id:
            raise ValueError(
                f"No device found in device registry with name '{name}'."
            )

        _LOGGER.debug("Resolved '%s' → device_id %s", name, device_id)

    # ------------------------------------------------------------
    # Normalize entities
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
        domain=domain,

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
    # DEVICE_ENTITY rewrite
    # ------------------------------------------------------------
    rewritten: List[Dict[str, Any]] = []

    for action in conf.middle_button:
        if not isinstance(action, dict):
            rewritten.append(action)
            continue

        new_action = dict(action)
        target = new_action.get("target")

        if isinstance(target, dict):
            eid = target.get("entity_id")

            # Case 1: entity_id: "device_entity"
            if eid == "device_entity":
                new_action["target"] = {"entity_id": conf.entities}

            # Case 2: entity_id: ["foo", "device_entity", ...]
            elif isinstance(eid, list) and "device_entity" in eid:
                expanded = []
                for x in eid:
                    if x == "device_entity":
                        expanded.extend(conf.entities)
                    else:
                        expanded.append(x)
                new_action["target"] = {"entity_id": expanded}

        rewritten.append(new_action)

    conf.middle_button = rewritten

    # ------------------------------------------------------------
    # VALIDATE & RETURN
    # ------------------------------------------------------------
    conf.validate()
    return conf


