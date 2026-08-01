# __init__.py — Integration entry point
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .config import PicoConfig, parse_pico_config
from .const import DOMAIN
from .controller import PicoController

_LOGGER = logging.getLogger(__name__)


async def async_setup(
    hass: HomeAssistant,
    config: ConfigType,
) -> bool:
    """Set up Pico Link from configuration.yaml."""
    root = config.get(DOMAIN)

    if root is None:
        _LOGGER.debug(
            "No %s configuration found in configuration.yaml",
            DOMAIN,
        )
        return True

    if not isinstance(root, dict):
        _LOGGER.error(
            "Invalid %s configuration: expected a mapping with optional "
            "'defaults' and required 'devices', got %s",
            DOMAIN,
            type(root).__name__,
        )
        return False

    # =============================================================
    # DEFAULTS
    # =============================================================

    raw_defaults = root.get("defaults")

    if raw_defaults is None:
        defaults: dict[str, Any] = {}
    elif isinstance(raw_defaults, dict):
        defaults = raw_defaults
    else:
        _LOGGER.error(
            "Invalid '%s.defaults' configuration: expected a mapping, got %s",
            DOMAIN,
            type(raw_defaults).__name__,
        )
        return False

    # =============================================================
    # DEVICES
    # =============================================================

    device_list = root.get("devices")

    if not isinstance(device_list, list):
        _LOGGER.error(
            "Invalid '%s.devices' configuration: expected a list, got %s",
            DOMAIN,
            type(device_list).__name__,
        )
        return False

    controllers: list[PicoController] = []

    # Track the configuration entry where each physical Pico was first
    # registered. A second entry for the same device would otherwise
    # create another controller subscribed to the same Pico events.
    configured_device_entries: dict[str, int] = {}

    for index, device_raw in enumerate(
        device_list,
        start=1,
    ):
        if not isinstance(device_raw, dict):
            _LOGGER.error(
                "Invalid %s device entry %s: expected a mapping, got %s: %r",
                DOMAIN,
                index,
                type(device_raw).__name__,
                device_raw,
            )
            continue

        try:
            pico_config: PicoConfig = parse_pico_config(
                hass,
                defaults,
                device_raw,
            )
        except ValueError as err:
            device_identifier = (
                device_raw.get("device_id") or device_raw.get("name") or "<unknown>"
            )
            device_type = device_raw.get("type") or "<unknown>"

            _LOGGER.error(
                "Invalid %s device entry %s (device=%s, type=%s): %s",
                DOMAIN,
                index,
                device_identifier,
                device_type,
                err,
            )
            continue

        first_entry = configured_device_entries.get(pico_config.device_id)

        if first_entry is not None:
            _LOGGER.error(
                "Invalid %s device entry %s: Pico device %s is "
                "already configured by entry %s",
                DOMAIN,
                index,
                pico_config.device_id,
                first_entry,
            )
            continue

        configured_device_entries[pico_config.device_id] = index

        controller = PicoController(
            hass,
            pico_config,
        )

        await controller.async_start()
        controllers.append(controller)

    # =============================================================
    # COMPLETED SETUP
    # =============================================================

    if not controllers:
        _LOGGER.warning(
            "%s is configured, but no valid Pico devices were created",
            DOMAIN,
        )
        return True

    hass.data.setdefault(
        DOMAIN,
        {},
    )["controllers"] = controllers

    # =============================================================
    # SHUTDOWN
    # =============================================================

    async def _async_stop(_: Any) -> None:
        await asyncio.gather(*(controller.async_stop() for controller in controllers))

    hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STOP,
        _async_stop,
    )

    _LOGGER.info(
        "%s initialized with %s controller(s)",
        DOMAIN,
        len(controllers),
    )

    return True
