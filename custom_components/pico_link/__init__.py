# __init__.py — Integration entry point
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant

from .config import parse_pico_config
from .const import DOMAIN
from .controller import PicoController

_LOGGER = logging.getLogger(__name__)

type PicoLinkConfigEntry = ConfigEntry[PicoController]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PicoLinkConfigEntry,
) -> bool:
    """Set up one Pico from a config entry."""
    device_raw = {
        "device_id": entry.data["device_id"],
        "type": entry.data["type"],
        **entry.options,
    }

    try:
        pico_config = parse_pico_config(
            hass,
            device_raw,
        )
    except ValueError as err:
        _LOGGER.error(
            "%s: invalid configuration for entry %s: %s",
            DOMAIN,
            entry.entry_id,
            err,
        )
        return False

    controller = PicoController(
        hass,
        pico_config,
    )

    await controller.async_start()

    entry.runtime_data = controller

    # Make sure Pico work is unsubscribed and stopped on a clean HA
    # shutdown, not just on entry unload.
    unsub_stop = hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STOP,
        lambda _event: hass.async_create_task(controller.async_stop()),
    )
    entry.async_on_unload(unsub_stop)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: PicoLinkConfigEntry,
) -> bool:
    """Unload a Pico config entry."""
    await entry.runtime_data.async_stop()
    return True


async def _async_update_listener(
    hass: HomeAssistant,
    entry: PicoLinkConfigEntry,
) -> None:
    """Reload a Pico when its options are edited."""
    await hass.config_entries.async_reload(entry.entry_id)
