from __future__ import annotations

import logging
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType

from .config import parse_pico_config
from .controller import PicoController
from .const import DOMAIN, PICO_EVENT_TYPE

_LOGGER = logging.getLogger(__name__)

# Store active controllers here
ACTIVE_CONTROLLERS: list[PicoController] = []


async def async_setup(hass: HomeAssistant, config: ConfigType):
    """Set up pico_link integration from YAML."""

    conf = config.get(DOMAIN)
    if not conf:
        return True

    # Remove any previously-loaded controllers (restart scenario)
    await _async_unload_controllers(hass)

    # Parse YAML section
    controllers = []
    for entry in conf:
        try:
            pico_conf = parse_pico_config(entry)
            controller = PicoController(hass, pico_conf)
            controllers.append(controller)
        except Exception as err:
            _LOGGER.error("Invalid Pico config: %s", err)

    # Register event listeners for each controller
    for controller in controllers:
        controller.register_listeners()

    ACTIVE_CONTROLLERS.extend(controllers)

    _LOGGER.info("pico_link initialized with %d controllers", len(controllers))

    # Register RELOAD SERVICE
    async def _reload_service(call: ServiceCall):
        await _async_unload_controllers(hass)
        await async_setup(hass, config)
        _LOGGER.info("pico_link: configuration reloaded.")

    hass.services.async_register(DOMAIN, "reload", _reload_service)

    return True


async def _async_unload_controllers(hass: HomeAssistant):
    """Unload all active controllers and remove listeners."""
    for controller in ACTIVE_CONTROLLERS:
        try:
            controller.unregister_listeners()
        except Exception as err:
            _LOGGER.debug("Error unregistering Pico controller: %s", err)

    ACTIVE_CONTROLLERS.clear()
