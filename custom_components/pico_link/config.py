# ================================================================
# CONFIG MODULE
# ================================================================
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from homeassistant.helpers import device_registry as dr

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
    step_time_ms: int = 650

    # Cover configuration
    cover_open_pos: int = 100  # 1–100
    cover_step_pct: int = 10  # 1–25
    cover_inverted: bool = False

    # Fan configuration
    fan_on_pct: int = 100  # 1–100

    # Light configuration
    light_on_pct: int = 100  # 1–100
    light_low_pct: int = 5  # 1–99
    light_step_pct: int = 10  # 1–25
    light_transition_on: int = 0  # 0-300
    light_transition_off: int = 0  # 0-300

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

        is_4b = self.type == "4B"

        # Determine domain assignments
        domains = [
            bool(self.covers),
            bool(self.fans),
            bool(self.lights),
            bool(self.media_players),
            bool(self.switches),
        ]
        active_domains = sum(domains)

        # -------------------------
        # 4B — Scene Controller
        # -------------------------
        if is_4b:
            if active_domains != 0:
                raise ValueError(
                    f"Pico {self.device_id} (4B): cannot define domains "
                    f"(covers/fans/lights/media_players/switches). Use `buttons:` only."
                )

            if not isinstance(self.buttons, dict) or not self.buttons:
                raise ValueError(
                    f"Pico {self.device_id} (4B): must define a non-empty `buttons:` block."
                )

            # No other validation applies to 4B
            return

        # -------------------------
        # Non-4B — must define EXACTLY ONE domain
        # -------------------------
        if active_domains == 0:
            raise ValueError(
                f"Pico {self.device_id}: No target domain configured. "
                "Must define exactly one of: covers, fans, lights, media_players, switches."
            )

        if active_domains > 1:
            raise ValueError(
                f"Pico {self.device_id}: Multiple domains configured. "
                "Only ONE domain may be assigned."
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


def _normalize_bool(raw_val, default: bool = False) -> bool:
    """Normalize common YAML/string bool values."""
    if raw_val is None:
        return default

    if isinstance(raw_val, bool):
        return raw_val

    if isinstance(raw_val, str):
        value = raw_val.strip().lower()
        if value in ("true", "yes", "on", "1"):
            return True
        if value in ("false", "no", "off", "0"):
            return False

    return bool(raw_val)


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
            raise ValueError(f"No device found in registry with name '{name}'.")

        _LOGGER.debug("Resolved device name '%s' → device_id %s", name, device_id)

    # ------------------------------------------------------------
    # Normalize entity lists
    # ------------------------------------------------------------
    covers = _normalize_list(merged.get("covers"))
    fans = _normalize_list(merged.get("fans"))
    lights = _normalize_list(merged.get("lights"))
    media_players = _normalize_list(merged.get("media_players"))
    switches = _normalize_list(merged.get("switches"))

    # ------------------------------------------------------------
    # Normalize timing and behavior parameters
    # ------------------------------------------------------------
    hold_time_ms = _normalize_int(
        raw_val=merged.get("hold_time_ms", 400),
        default=400,
        min_val=100,
        max_val=2000,
    )

    step_time_ms = _normalize_int(
        raw_val=merged.get("step_time_ms", 650),
        default=650,
        min_val=100,
        max_val=2000,
    )

    cover_open_pos = _normalize_int(
        raw_val=merged.get("cover_open_pos", 100),
        default=100,
        min_val=1,
        max_val=100,
    )

    cover_step_pct = _normalize_int(
        raw_val=merged.get("cover_step_pct", 10),
        default=10,
        min_val=1,
        max_val=25,
    )

    cover_inverted = _normalize_bool(
        raw_val=merged.get("cover_inverted", False),
        default=False,
    )

    fan_on_pct = _normalize_int(
        raw_val=merged.get("fan_on_pct", 100),
        default=100,
        min_val=1,
        max_val=100,
    )

    light_on_pct = _normalize_int(
        raw_val=merged.get("light_on_pct", 100),
        default=100,
        min_val=1,
        max_val=100,
    )

    light_low_pct = _normalize_int(
        raw_val=merged.get("light_low_pct", 5),
        default=5,
        min_val=1,
        max_val=99,
    )

    light_step_pct = _normalize_int(
        raw_val=merged.get("light_step_pct", 10),
        default=10,
        min_val=1,
        max_val=25,
    )

    light_transition_on = _normalize_int(
        raw_val=merged.get("light_transition_on", 0),
        default=0,
        min_val=0,
        max_val=300,
    )

    light_transition_off = _normalize_int(
        raw_val=merged.get("light_transition_off", 0),
        default=0,
        min_val=0,
        max_val=300,
    )

    media_player_vol_step = _normalize_int(
        raw_val=merged.get("media_player_vol_step", 10),
        default=10,
        min_val=1,
        max_val=20,
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
        cover_inverted=cover_inverted,
        fan_on_pct=fan_on_pct,
        light_on_pct=light_on_pct,
        light_low_pct=light_low_pct,
        light_step_pct=light_step_pct,
        light_transition_on=light_transition_on,
        light_transition_off=light_transition_off,
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
