from __future__ import annotations

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
    """Set up pico_connector from YAML configuration."""
    raw_confs = config.get(DOMAIN)
    if not raw_confs:
        _LOGGER.debug("No %s configuration found in configuration.yaml", DOMAIN)
        return True

    controllers: List[PicoController] = []
    for idx, raw in enumerate(raw_confs, start=1):
        try:
            pico_conf: PicoConfig = parse_pico_config(raw)
        except ValueError as err:
            _LOGGER.error(
                "Invalid %s config at index %s: %s; skipping this entry",
                DOMAIN,
                idx,
                err,
            )
            continue

        controller = PicoController(hass, pico_conf)
        await controller.async_start()
        controllers.append(controller)

    if not controllers:
        _LOGGER.warning(
            "%s configured but no valid entries were created; nothing to do", DOMAIN
        )
        return True

    hass.data.setdefault(DOMAIN, {})["controllers"] = controllers

    async def _async_stop(_: Any) -> None:
        for ctl in controllers:
            ctl.async_stop()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
    _LOGGER.info("pico_connector initialized with %s controller(s)", len(controllers))
    return True