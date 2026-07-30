# __init__.py — Integration entry point

from __future__ import annotations

import asyncio
import logging
from typing import Any, List

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .config import PicoConfig, parse_pico_config
from .const import DOMAIN
from .controller import PicoController

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    root = config.get(DOMAIN)
    if not root:
        _LOGGER.debug("No %s configuration found in configuration.yaml", DOMAIN)
        return True

    if not isinstance(root, dict):
        _LOGGER.error(
            "Invalid pico_link config: expected mapping with optional 'defaults' "
            "and required 'devices'"
        )
        return False

    # ------------------------------------------------------------
    # Validate optional defaults block
    # ------------------------------------------------------------
    defaults = root.get("defaults", {}) or {}

    if not isinstance(defaults, dict):
        _LOGGER.error(
            "Invalid 'defaults' block in pico_link configuration: expected a mapping, got %s. "
            "Example:\n"
            "pico_link:\n"
            "  defaults:\n"
            "    hold_time_ms: 300",
            type(defaults).__name__,
        )
        return False

    # ------------------------------------------------------------
    # Required list of devices
    # ------------------------------------------------------------
    device_list = root.get("devices")
    if not isinstance(device_list, list):
        _LOGGER.error("pico_link.devices must be a list")
        return False

    controllers: List[PicoController] = []

    # ------------------------------------------------------------
    # Build controller per device
    # ------------------------------------------------------------
    for idx, device_raw in enumerate(device_list, start=1):
        try:
            pico_conf: PicoConfig = parse_pico_config(hass, defaults, device_raw)
        except ValueError as err:
            _LOGGER.error(
                "Invalid pico_link config at entry %s (device_id=%s, type=%s): %s",
                idx,
                device_raw.get("device_id") or device_raw.get("name"),
                device_raw.get("type"),
                err,
            )
            continue

        controller = PicoController(hass, pico_conf)
        await controller.async_start()
        controllers.append(controller)

    # ------------------------------------------------------------
    # No controllers created?
    # ------------------------------------------------------------
    if not controllers:
        _LOGGER.warning(
            "%s configured but no valid devices were created; nothing to do",
            DOMAIN,
        )
        return True

    hass.data.setdefault(DOMAIN, {})["controllers"] = controllers

    # ------------------------------------------------------------
    # Cleanup on shutdown
    # ------------------------------------------------------------
    async def _async_stop(_: Any) -> None:
        await asyncio.gather(*(controller.async_stop() for controller in controllers))

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)

    _LOGGER.info(
        "pico_link initialized with %s controller(s)",
        len(controllers),
    )  # <<< NEW

    return True
