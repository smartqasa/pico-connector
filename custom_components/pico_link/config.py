# ================================================================
# CONFIG MODULE
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

    # Entities by domain — ONE must be assigned
    covers: List[str] = field(default_factory=list)
    fans: List[str] = field(default_factory=list)
    lights: List[str] = field(default_factory=list)
    media_players: List[str] = field(default_factory=list)
    switches: List[str] = field(default_factory=list)

    # Normalized action parameters (ms)
    hold_time_ms: int = 250
    step_time_ms: int = 750

    # Cover configuration
    cover_open_pos: int = 100      # 1–100
    cover_step_pct: int = 10       # 1–25

    # Fan configuration
    fan_on_pct: int = 100          # 1–100
    fan_speeds: int = 6            # ONLY 4 or 6

    # Light configuration
    light_on_pct: int = 100        # 1–100
    light_low_pct: int = 1         # 1–99
    light_step_pct: int = 10       # 1–25

    # Media player config
    media_player_vol_step: int = 10  # 1–20 recommended

    # 3BRL only
    middle_button: List[Dict[str, Any]] = field(default_factory=list)

    # 4B only
    buttons: Dict[str, List[Dict]] = field(default_factory=dict)

    # ------------------------------------------------------------
    def validate(self) -> None:
        # Validate Pico type
        if self.type not in VALID_PICO_TYPES:
            raise ValueError(
                f"Invalid Pico type '{self.type}'. Must be one of: {VALID_PICO_TYPES}"
            )

        # Validate exactly ONE domain
        domains = [
            self.covers,
            self.fans,
            self.lights,
            self.media_players,
            self.switches,
        ]
        active_domains = sum(bool(d) for d in domains)

        if active_domains == 0:
            raise ValueError(
                f"Pico {self.device_id}: No target domain configured. "
                "Must define exactly one of: covers, fans, lights, media_players, switches."
            )

        if active_domains > 1:
            raise ValueError(
                f"Pico {self.device_id}: Multiple domains configured. "
                "Only ONE domain may be assigned to each Pico."
            )

        # Fan validation
        if self.fans:
            if self.fan_speeds not in (4, 6):
                raise ValueError(
                    f"Pico {self.device_id}: fan_speeds must be 4 or 6, got {self.fan_speeds}"
                )

        # 4B validation
        if self.type == "4B":
            if not isinstance(self.buttons, dict):
                raise ValueError(
                    f"Pico {self.device_id} (4B): 'buttons' must be a dict."
                )
            for key, vals in self.buttons.items():
                if not isinstance(vals, list):
                    raise ValueError(
                        f"Pico {self.device_id} (4B): '{key}' must be a list of actions."
                    )


# ================================================================
# DEVICE LOOKUP UTILITY
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
# NORMALIZATION UTILITIES
# ================================================================
def _normalize_int(raw_val, default: int, min_val: int, max_val: int) -> int:
    """Convert to int, clamp into range, treat 0 or invalid as default."""
    try:
        val = int(raw_val)
    except Exception:
        val = default

    if val == 0:
        return default

    return max(min_val, min(max_val, val))


def _normalize_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value]
    return []


# ================================================================
# CONFIG PARSER
# ================================================================
def parse_pico_config(
    hass,
    defaults: Dict[str, Any],
    device_raw: Dict[str, Any],
) -> PicoConfig:

    # ------------------------------------------------------------
    # Ensure device type exists
    # ------------------------------------------------------------
    device_type = device_raw.get("type")
    if not device_type:
        raise ValueError("Device must define a 'type'.")
    device_type = str(device_type)

    # ------------------------------------------------------------
    # Merge defaults → raw (except middle_button)
    # ------------------------------------------------------------
    merged: Dict[str, Any] = {}
    for key, val in defaults.items():
        if key != "middle_button":
            merged[key] = val

    merged.update(device_raw)

    # ------------------------------------------------------------
    # Resolve device_id
    # ------------------------------------------------------------
    device_id = merged.get("device_id")

    if not device_id:
        name = merged.get("name")
        if not name:
            raise ValueError("Device must define 'device_id' or 'name'.")

        device_id = lookup_device_id(hass, name)
        if not device_id:
            raise ValueError(
                f"No device found in registry with name '{name}'."
            )

        _LOGGER.debug("Resolved device name '%s' → device_id %s", name, device_id)

    # ------------------------------------------------------------
    # Normalize entity lists
    # ------------------------------------------------------------
    covers         = _normalize_list(merged.get("covers"))
    fans           = _normalize_list(merged.get("fans"))
    lights         = _normalize_list(merged.get("lights"))
    media_players  = _normalize_list(merged.get("media_players"))
    switches       = _normalize_list(merged.get("switches"))

    # ------------------------------------------------------------
    # Normalize timing and behavior parameters
    # ------------------------------------------------------------
    hold_time_ms  = _normalize_int(merged.get("hold_time_ms", 250), 250, 100, 2000)
    step_time_ms  = _normalize_int(merged.get("step_time_ms", 750), 750, 100, 2000)

    cover_open_pos = _normalize_int(merged.get("cover_open_pos", 100), 100, 1, 100)
    cover_step_pct = _normalize_int(merged.get("cover_step_pct", 10), 10, 1, 25)

    fan_on_pct = _normalize_int(merged.get("fan_on_pct", merged.get("on_pct", 100)),
                                100, 1, 100)

    try:
        fs = int(merged.get("fan_speeds", 6))
    except Exception:
        fs = 6
    fan_speeds = fs if fs in (4, 6) else 6

    light_on_pct   = _normalize_int(merged.get("light_on_pct",  merged.get("on_pct", 100)),
                                    100, 1, 100)
    light_low_pct  = _normalize_int(merged.get("light_low_pct", merged.get("low_pct", 1)),
                                    1,   1, 99)
    light_step_pct = _normalize_int(merged.get("light_step_pct", merged.get("step_pct", 10)),
                                    10, 1, 25)

    media_player_vol_step = _normalize_int(
        merged.get("media_player_vol_step", 10),
        default=10,
        min_val=1,
        max_val=20,  # corrected: 100 was too large
    )

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
    # INITIAL CONFIG BUILD
    # ------------------------------------------------------------
    conf = PicoConfig(
        device_id=device_id,
        type=device_type,

        covers=covers,
        fans=fans,
        lights=lights,
        media_players=media_players,
        switches=switches,

        hold_time_ms=hold_time_ms,
        step_time_ms=step_time_ms,

        cover_open_pos=cover_open_pos,
        cover_step_pct=cover_step_pct,

        fan_on_pct=fan_on_pct,
        fan_speeds=fan_speeds,

        light_on_pct=light_on_pct,
        light_low_pct=light_low_pct,
        light_step_pct=light_step_pct,

        media_player_vol_step=media_player_vol_step,

        middle_button=middle_button,
        buttons=merged.get("buttons", {}),
    )

    # ------------------------------------------------------------
    # Placeholder expansion for middle_button
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
                new_action["target"] = {"entity_id": PLACEHOLDERS[eid]}

            # Mixed placeholder list
            elif isinstance(eid, list):
                expanded = []
                for x in eid:
                    if x in PLACEHOLDERS:
                        expanded.extend(PLACEHOLDERS[x])
                    else:
                        expanded.append(x)
                new_action["target"] = {"entity_id": expanded}

        rewritten.append(new_action)

    conf.middle_button = rewritten

    # ------------------------------------------------------------
    # FINAL VALIDATION
    # ------------------------------------------------------------
    conf.validate()
    return conf
