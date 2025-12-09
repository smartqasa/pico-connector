# ================================================================
# CONFIG MODULE — Handles PicoLink configuration and validation
# ================================================================
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from homeassistant.helpers import device_registry as dr
import logging

from .const import VALID_PICO_TYPES  # valid: 3BRL, 4B, P2B, 2B

_LOGGER = logging.getLogger(__name__)


# ================================================================
# DEVICE CONFIGURATION MODEL (DATACLASS)
# ================================================================
@dataclass
class PicoConfig:
    device_id: str
    type: str
    behavior: str | None = None

    # Entities by domain
    covers: List[str] = field(default_factory=list)
    fans: List[str] = field(default_factory=list)
    lights: List[str] = field(default_factory=list)
    media_players: List[str] = field(default_factory=list)
    switches: List[str] = field(default_factory=list)

    # Default action parameters
    hold_time_ms: int = 0
    step_time_ms: int = 0
    step_pct: int = 0
    low_pct: int = 0
    on_pct: int = 0
    fan_speeds: int = 0

    # 3BRL only — middle button actions
    middle_button: List[Dict[str, Any]] = field(default_factory=list)

    # 4B only — scene buttons
    buttons: Dict[str, List[Dict]] = field(default_factory=dict)

    # ------------------------------------------------------------
    def validate(self) -> None:
        if self.type not in VALID_PICO_TYPES:
            raise ValueError(
                f"Invalid type '{self.type}' for device {self.device_id}. "
                f"Must be one of: {VALID_PICO_TYPES}"
            )


# ================================================================
# LOOK UP device_id FROM name_by_user FIRST, THEN name
# ================================================================
def lookup_device_id(hass, name: str) -> str | None:
    dev_reg = dr.async_get(hass)

    for dev in dev_reg.devices.values():
        if dev.name_by_user == name:
            return dev.id

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

    # ------------------------------------------------------------
    # Ensure Pico type exists
    # ------------------------------------------------------------
    device_type = device_raw.get("type")
    if not device_type:
        raise ValueError("Device must define a 'type'.")
    device_type = str(device_type)

    # ------------------------------------------------------------
    # Merge defaults → raw (except middle_button)
    # ------------------------------------------------------------
    raw: Dict[str, Any] = {}
    for key, value in defaults.items():
        if key == "middle_button":
            continue
        raw[key] = value

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
    # Safe normalization helper
    # ------------------------------------------------------------
    def normalize(v):
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return [v]
        return []

    # ------------------------------------------------------------
    # Per-domain entity lists
    # ------------------------------------------------------------
    covers = normalize(raw.get("covers"))
    fans = normalize(raw.get("fans"))
    lights = normalize(raw.get("lights"))
    media_players = normalize(raw.get("media_players"))
    switches = normalize(raw.get("switches"))

    # ------------------------------------------------------------
    # Middle button (3BRL only)
    # ------------------------------------------------------------
    raw_mb = device_raw.get("middle_button")

    if device_type == "3BRL":
        if raw_mb == "default":
            middle_button = defaults.get("middle_button", [])
        elif isinstance(raw_mb, list):
            middle_button = raw_mb
        else:
            middle_button = []
    else:
        middle_button = []

    # ------------------------------------------------------------
    # Build PicoConfig
    # ------------------------------------------------------------
    conf = PicoConfig(
        device_id=device_id,
        type=device_type,
        behavior=None,

        covers=covers,
        fans=fans,
        lights=lights,
        media_players=media_players,
        switches=switches,

        hold_time_ms=int(raw.get("hold_time_ms", 250)),
        step_time_ms=int(raw.get("step_time_ms", 750)),
        step_pct=int(raw.get("step_pct", 10)),
        low_pct=int(raw.get("low_pct", 1)),
        on_pct=int(raw.get("on_pct", 100)),
        fan_speeds=int(raw.get("fan_speeds", 6)),

        middle_button=middle_button,
        buttons=raw.get("buttons", {}),
    )

    # ------------------------------------------------------------
    # Expand placeholders in middle_button
    # ------------------------------------------------------------
    PLACEHOLDERS = {
        "covers": conf.covers,
        "fans": conf.fans,
        "lights": conf.lights,
        "media_players": conf.media_players,
        "switches": conf.switches,
    }

    rewritten = []

    for action in conf.middle_button:
        if not isinstance(action, dict):
            rewritten.append(action)
            continue

        new_action = dict(action)
        target = new_action.get("target")

        if isinstance(target, dict):
            eid = target.get("entity_id")

            # Single placeholder
            if isinstance(eid, str) and eid in PLACEHOLDERS:
                new_action["target"] = {
                    "entity_id": PLACEHOLDERS[eid]
                }

            # Mixed list of placeholders + literals
            elif isinstance(eid, list):
                expanded: List[str] = []
                for x in eid:
                    if x in PLACEHOLDERS:
                        expanded.extend(PLACEHOLDERS[x])
                    else:
                        expanded.append(x)

                new_action["target"] = {"entity_id": expanded}

        rewritten.append(new_action)

    conf.middle_button = rewritten

    # ------------------------------------------------------------
    # Validate and return
    # ------------------------------------------------------------
    conf.validate()
    return conf
