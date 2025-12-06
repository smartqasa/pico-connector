# __init__.py — Integration entry point

from __future__ import annotations

import logging
from typing import Any, List, Dict

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .config import PicoConfig, parse_pico_config
from .const import DOMAIN
from .controller import PicoController

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """
    Entry point for pico_link integration.

    Expected YAML structure:

    pico_link:
      defaults:
        step_pct: 5
        hold_time_ms: 300
      devices:
        - device_id: ...
          profile: paddle
          entities: [light.kitchen]
    """

    root = config.get(DOMAIN)
    if not root:
        _LOGGER.debug("No %s configuration found in configuration.yaml", DOMAIN)
        return True

    if not isinstance(root, dict):
        _LOGGER.error(
            "Invalid pico_link config: expected mapping with optional 'defaults' and required 'devices'"
        )
        return False

    # ------------------------------------------------------------
    # Optional global defaults (may be empty)
    # ------------------------------------------------------------
    defaults: Dict[str, Any] = root.get("defaults", {}) or {}

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

        # Merge DEFAULTS → device overrides
        merged = {**defaults, **device_raw}

        try:
            pico_conf: PicoConfig = parse_pico_config(hass, merged)
        except ValueError as err:
            _LOGGER.error(
                "Invalid pico_link config at entry %s (device_id=%s): %s",
                idx,
                device_raw.get("device_id"),
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
        for ctl in controllers:
            ctl.async_stop()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)

    _LOGGER.info("pico_link initialized with %s controller(s)", len(controllers))
    return True
