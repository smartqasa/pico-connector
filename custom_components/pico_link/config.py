from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, valid_entity_id
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.script import async_validate_actions_config

from .const import VALID_PICO_TYPES

_LOGGER = logging.getLogger(__name__)

_VALID_4B_BUTTONS = frozenset(
    {
        "button_1",
        "button_2",
        "button_3",
        "off",
    }
)

ActionConfig = dict[str, Any]


@dataclass
class PicoConfig:
    """Normalized configuration for one Pico remote."""

    device_id: str
    type: str

    # Exactly one domain must be assigned for non-4B Picos.
    covers: list[str] = field(default_factory=list)
    fans: list[str] = field(default_factory=list)
    lights: list[str] = field(default_factory=list)
    media_players: list[str] = field(default_factory=list)
    switches: list[str] = field(default_factory=list)

    # Normalized action parameters in milliseconds.
    hold_time_ms: int = 400
    step_time_ms: int = 650

    # Cover configuration.
    cover_open_pos: int = 100
    cover_step_pct: int = 10
    cover_inverted: bool = False

    # Fan configuration.
    fan_on_pct: int = 100

    # Light configuration.
    light_on_pct: int = 100
    light_low_pct: int = 5
    light_step_pct: int = 10
    light_transition_on: int = 0
    light_transition_off: int = 0

    # Media-player configuration.
    media_player_vol_step: int = 10

    # 3BRL only.
    middle_button: list[ActionConfig] = field(default_factory=list)

    # 4B only.
    buttons: dict[str, list[ActionConfig]] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate the normalized Pico configuration."""
        if self.type not in VALID_PICO_TYPES:
            valid_types = ", ".join(sorted(VALID_PICO_TYPES))

            raise ValueError(
                f"Invalid Pico type {self.type!r}. Must be one of: {valid_types}"
            )

        domain_lists = {
            "covers": self.covers,
            "fans": self.fans,
            "lights": self.lights,
            "media_players": self.media_players,
            "switches": self.switches,
        }

        active_domains = [name for name, entities in domain_lists.items() if entities]

        if self.type == "4B":
            if active_domains:
                raise ValueError(
                    f"Pico {self.device_id} (4B) cannot define "
                    f"entity domains: {', '.join(active_domains)}. "
                    "Use 'buttons' only."
                )

            if not self.buttons:
                raise ValueError(
                    f"Pico {self.device_id} (4B) must define "
                    "a non-empty 'buttons' mapping."
                )

            if self.middle_button:
                raise ValueError(
                    f"Pico {self.device_id} (4B) cannot define 'middle_button'."
                )

            return

        if len(active_domains) != 1:
            if not active_domains:
                raise ValueError(
                    f"Pico {self.device_id} must define exactly "
                    "one of: covers, fans, lights, media_players, "
                    "switches."
                )

            raise ValueError(
                f"Pico {self.device_id} defines multiple entity "
                f"domains: {', '.join(active_domains)}. "
                "Only one is allowed."
            )

        if self.buttons:
            raise ValueError(
                f"Pico {self.device_id} ({self.type}) cannot "
                "define 'buttons'. 'buttons' is only valid for "
                "4B Picos."
            )


# ================================================================
# DEVICE LOOKUP
# ================================================================


def lookup_device_id(
    hass: HomeAssistant,
    name: str,
) -> str | None:
    """Resolve a unique device by user-assigned or registry name."""
    device_registry = dr.async_get(hass)

    # Prefer the user-assigned name over the integration-provided name.
    for attribute in (
        "name_by_user",
        "name",
    ):
        matches = [
            device
            for device in device_registry.devices.values()
            if getattr(device, attribute) == name
        ]

        if len(matches) > 1:
            raise ValueError(
                f"Multiple devices are named {name!r}. "
                "Configure this Pico using device_id."
            )

        if matches:
            return matches[0].id

    return None


def _resolve_device_id(
    hass: HomeAssistant,
    merged: dict[str, Any],
) -> str:
    """Resolve the configured Pico device ID."""
    raw_device_id = merged.get("device_id")

    if raw_device_id is not None:
        if not isinstance(raw_device_id, str) or not raw_device_id.strip():
            raise ValueError("'device_id' must be a non-empty string.")

        # The Lutron event supplies the Home Assistant device ID.
        # Do not require a particular registry identifier format.
        return raw_device_id.strip()

    raw_name = merged.get("name")

    if not isinstance(raw_name, str) or not raw_name.strip():
        raise ValueError("Device must define a non-empty 'device_id' or 'name'.")

    name = raw_name.strip()

    device_id = lookup_device_id(
        hass,
        name,
    )

    if device_id is None:
        raise ValueError(f"No device was found with name {name!r}.")

    _LOGGER.debug(
        "Resolved device name %r to device_id %s",
        name,
        device_id,
    )

    return device_id


# ================================================================
# VALUE NORMALIZATION
# ================================================================


def _normalize_int(
    raw_val: Any,
    default: int,
    min_val: int,
    max_val: int,
) -> int:
    """
    Convert a value to int and clamp it to the allowed range.

    Invalid values and zero use the supplied default.
    """
    if isinstance(raw_val, bool):
        return default

    try:
        value = int(raw_val)
    except (TypeError, ValueError):
        value = default

    if value == 0:
        return default

    return max(
        min_val,
        min(max_val, value),
    )


def _normalize_bool(
    raw_val: Any,
    default: bool = False,
) -> bool:
    """Normalize a strict Boolean configuration value."""
    if raw_val is None:
        return default

    if isinstance(raw_val, bool):
        return raw_val

    if isinstance(raw_val, str):
        value = raw_val.strip().lower()

        if value in {
            "true",
            "yes",
            "on",
            "1",
        }:
            return True

        if value in {
            "false",
            "no",
            "off",
            "0",
        }:
            return False

    raise ValueError(f"Expected a Boolean value, got {raw_val!r}.")


def _normalize_entities(
    value: Any,
    *,
    key: str,
    domain: str,
) -> list[str]:
    """Normalize and validate an entity ID or entity-ID list."""
    if value is None:
        return []

    if isinstance(value, str):
        raw_entities = [value]
    elif isinstance(value, list):
        raw_entities = value
    else:
        raise ValueError(f"'{key}' must be an entity ID or a list of entity IDs.")

    entities: list[str] = []

    for index, item in enumerate(
        raw_entities,
        start=1,
    ):
        if not isinstance(item, str):
            raise ValueError(
                f"'{key}' entry {index} must be a string, got {type(item).__name__}."
            )

        entity_id = item.strip()

        if not valid_entity_id(entity_id):
            raise ValueError(
                f"'{key}' entry {index} contains invalid entity ID {entity_id!r}."
            )

        entity_domain = entity_id.split(
            ".",
            1,
        )[0]

        if entity_domain != domain:
            raise ValueError(
                f"'{key}' entry {index} must use the "
                f"{domain!r} domain, got {entity_id!r}."
            )

        # Preserve order while removing duplicates.
        if entity_id not in entities:
            entities.append(entity_id)

    return entities


# ================================================================
# ACTION VALIDATION
#
# Actions are validated with Home Assistant's own script schema and
# executed with homeassistant.helpers.script.Script (see
# utilities.py), instead of a hand-rolled plain-service-call
# validator. This means the full range of native Home Assistant
# actions is supported here, including conditions, if-then, choose,
# repeat, and templates — the same building blocks available in the
# automation editor's action picker — not just plain "domain.service"
# calls.
# ================================================================


async def _validate_actions(
    hass: HomeAssistant,
    value: Any,
    *,
    context: str,
) -> list[ActionConfig]:
    """Validate an ordered action list against Home Assistant's own schema."""
    if value is None:
        return []

    if not isinstance(value, list):
        raise ValueError(f"{context} must be a list of actions.")

    try:
        schema_validated = cv.SCRIPT_SCHEMA(value)
        return await async_validate_actions_config(
            hass,
            schema_validated,
        )
    except (vol.Invalid, HomeAssistantError) as err:
        raise ValueError(f"{context}: {err}") from err


async def _validate_buttons(
    hass: HomeAssistant,
    value: Any,
) -> dict[str, list[ActionConfig]]:
    """Validate a 4B button-to-action mapping."""
    if value is None:
        return {}

    if not isinstance(value, dict):
        raise ValueError("'buttons' must be a mapping of button names to action lists.")

    buttons: dict[str, list[ActionConfig]] = {}

    for raw_button, raw_actions in value.items():
        if not isinstance(raw_button, str):
            raise ValueError("Each 'buttons' key must be a string.")

        button = raw_button.strip()

        if button not in _VALID_4B_BUTTONS:
            valid_buttons = ", ".join(sorted(_VALID_4B_BUTTONS))

            raise ValueError(
                f"Unsupported 4B button {button!r}. Valid buttons are: {valid_buttons}."
            )

        actions = await _validate_actions(
            hass,
            raw_actions,
            context=f"buttons.{button}",
        )

        if not actions:
            raise ValueError(f"'buttons.{button}' must contain at least one action.")

        buttons[button] = actions

    return buttons


# ================================================================
# PLACEHOLDER EXPANSION
#
# Placeholder tokens (e.g. "lights") are not valid entity IDs, so they
# must be expanded before Home Assistant's schema validation runs.
# This walks the raw, not-yet-validated action structure recursively,
# so placeholders are found inside nested if-then/choose/repeat blocks
# too, not just top-level actions.
# ================================================================


def _expand_placeholders(
    value: Any,
    placeholders: dict[str, list[str]],
) -> Any:
    """Recursively expand entity placeholders anywhere in an action tree."""
    if isinstance(value, dict):
        return {
            key: (
                _expand_target(val, placeholders)
                if key == "target" and isinstance(val, dict)
                else _expand_placeholders(val, placeholders)
            )
            for key, val in value.items()
        }

    if isinstance(value, list):
        return [_expand_placeholders(item, placeholders) for item in value]

    return value


def _expand_target(
    target: dict[str, Any],
    placeholders: dict[str, list[str]],
) -> dict[str, Any]:
    """Expand entity placeholders in one action's target mapping."""
    entity_ids = target.get("entity_id")

    if isinstance(entity_ids, str):
        if entity_ids not in placeholders:
            return target

        new_target = dict(target)
        new_target["entity_id"] = list(placeholders[entity_ids])
        return new_target

    if isinstance(entity_ids, list):
        expanded: list[Any] = []

        for entity_id in entity_ids:
            if isinstance(entity_id, str) and entity_id in placeholders:
                expanded.extend(placeholders[entity_id])
            else:
                expanded.append(entity_id)

        new_target = dict(target)
        new_target["entity_id"] = expanded
        return new_target

    return target


# ================================================================
# CONFIGURATION PARSER
# ================================================================


async def parse_pico_config(
    hass: HomeAssistant,
    defaults: dict[str, Any],
    device_raw: dict[str, Any],
) -> PicoConfig:
    """Normalize and validate one Pico Link device configuration."""
    raw_type = device_raw.get("type")

    if raw_type is None:
        raise ValueError("Device must define a 'type'.")

    if not isinstance(raw_type, str) or not raw_type.strip():
        raise ValueError("'type' must be a non-empty string.")

    device_type = raw_type.strip().upper()

    # middle_button defaults require an explicit
    # middle_button: default on the device.
    merged = {key: value for key, value in defaults.items() if key != "middle_button"}
    merged.update(device_raw)

    device_id = _resolve_device_id(
        hass,
        merged,
    )

    # ------------------------------------------------------------
    # ENTITY LISTS
    # ------------------------------------------------------------

    covers = _normalize_entities(
        merged.get("covers"),
        key="covers",
        domain="cover",
    )

    fans = _normalize_entities(
        merged.get("fans"),
        key="fans",
        domain="fan",
    )

    lights = _normalize_entities(
        merged.get("lights"),
        key="lights",
        domain="light",
    )

    media_players = _normalize_entities(
        merged.get("media_players"),
        key="media_players",
        domain="media_player",
    )

    switches = _normalize_entities(
        merged.get("switches"),
        key="switches",
        domain="switch",
    )

    # ------------------------------------------------------------
    # TIMING AND DOMAIN OPTIONS
    # ------------------------------------------------------------

    hold_time_ms = _normalize_int(
        merged.get(
            "hold_time_ms",
            400,
        ),
        default=400,
        min_val=100,
        max_val=2000,
    )

    step_time_ms = _normalize_int(
        merged.get(
            "step_time_ms",
            650,
        ),
        default=650,
        min_val=100,
        max_val=2000,
    )

    cover_open_pos = _normalize_int(
        merged.get(
            "cover_open_pos",
            100,
        ),
        default=100,
        min_val=1,
        max_val=100,
    )

    cover_step_pct = _normalize_int(
        merged.get(
            "cover_step_pct",
            10,
        ),
        default=10,
        min_val=1,
        max_val=25,
    )

    cover_inverted = _normalize_bool(
        merged.get(
            "cover_inverted",
            False,
        ),
        default=False,
    )

    fan_on_pct = _normalize_int(
        merged.get(
            "fan_on_pct",
            100,
        ),
        default=100,
        min_val=1,
        max_val=100,
    )

    light_on_pct = _normalize_int(
        merged.get(
            "light_on_pct",
            100,
        ),
        default=100,
        min_val=1,
        max_val=100,
    )

    light_low_pct = _normalize_int(
        merged.get(
            "light_low_pct",
            5,
        ),
        default=5,
        min_val=1,
        max_val=99,
    )

    light_step_pct = _normalize_int(
        merged.get(
            "light_step_pct",
            10,
        ),
        default=10,
        min_val=1,
        max_val=25,
    )

    light_transition_on = _normalize_int(
        merged.get(
            "light_transition_on",
            0,
        ),
        default=0,
        min_val=0,
        max_val=300,
    )

    light_transition_off = _normalize_int(
        merged.get(
            "light_transition_off",
            0,
        ),
        default=0,
        min_val=0,
        max_val=300,
    )

    media_player_vol_step = _normalize_int(
        merged.get(
            "media_player_vol_step",
            10,
        ),
        default=10,
        min_val=1,
        max_val=20,
    )

    # ------------------------------------------------------------
    # MIDDLE BUTTON
    # ------------------------------------------------------------

    placeholders = {
        "covers": covers,
        "fans": fans,
        "lights": lights,
        "media_players": media_players,
        "switches": switches,
    }

    raw_middle_button = device_raw.get("middle_button")

    if device_type == "3BRL":
        if raw_middle_button == "default":
            expanded_middle_button = _expand_placeholders(
                defaults.get(
                    "middle_button",
                    [],
                ),
                placeholders,
            )
            middle_button = await _validate_actions(
                hass,
                expanded_middle_button,
                context="defaults.middle_button",
            )
        elif raw_middle_button is None:
            middle_button = []
        else:
            expanded_middle_button = _expand_placeholders(
                raw_middle_button,
                placeholders,
            )
            middle_button = await _validate_actions(
                hass,
                expanded_middle_button,
                context="middle_button",
            )
    else:
        if raw_middle_button not in (
            None,
            [],
        ):
            raise ValueError("'middle_button' is only valid for 3BRL Picos.")

        middle_button = []

    # ------------------------------------------------------------
    # 4B BUTTONS
    # ------------------------------------------------------------

    buttons = await _validate_buttons(
        hass,
        merged.get("buttons"),
    )

    # ------------------------------------------------------------
    # BUILD CONFIGURATION
    # ------------------------------------------------------------

    pico_config = PicoConfig(
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
        buttons=buttons,
    )

    pico_config.validate()

    return pico_config
