from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional, Tuple

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback

from .config import PicoConfig
from .const import (
    PROFILE_FIVE_BUTTON,
    PROFILE_FOUR_BUTTON,
    PROFILE_PADDLE,
    PROFILE_TWO_BUTTON,
    SUPPORTED_BUTTONS,
    PICO_EVENT_TYPE,
)
from .behaviors import SharedBehaviors
from .profile_paddle import PaddleProfile
from .profile_five import FiveButtonProfile
from .profile_two import TwoButtonProfile
from .profile_four import FourButtonProfile

_LOGGER = logging.getLogger(__name__)


class PicoController(SharedBehaviors):
    """Implements press/hold/ramp behavior for a single Pico remote."""

    def __init__(self, hass: HomeAssistant, conf: PicoConfig) -> None:
        super().__init__(hass, conf)

        # Instantiate profile handlers
        self._profiles: Dict[str, object] = {
            PROFILE_PADDLE: PaddleProfile(self),
            PROFILE_FIVE_BUTTON: FiveButtonProfile(self),
            PROFILE_TWO_BUTTON: TwoButtonProfile(self),
            PROFILE_FOUR_BUTTON: FourButtonProfile(self),
        }

    async def async_start(self) -> None:
        """Start listening for Pico button events."""

        @callback
        def _handle_event(event: Event) -> None:
            data = event.data

            if data.get("device_id") != self.conf.device_id:
                return

            button, action = self._map_event_payload(data)
            if button is None or action is None:
                return

            if button not in SUPPORTED_BUTTONS:
                _LOGGER.debug(
                    "Device %s: ignoring unsupported button '%s'",
                    self.conf.device_id,
                    button,
                )
                return

            profile_obj = self._profiles.get(self.conf.profile)
            if not profile_obj:
                _LOGGER.warning(
                    "Device %s: unknown profile '%s'",
                    self.conf.device_id,
                    self.conf.profile,
                )
                return

            # Each profile exposes: handle(button, action)
            profile_obj.handle(button, action)  # type: ignore[call-arg]

        self._unsub_event = self.hass.bus.async_listen(PICO_EVENT_TYPE, _handle_event)

        _LOGGER.info(
            "PicoController started for device %s (profile=%s, domain=%s)",
            self.conf.device_id,
            self.conf.profile,
            getattr(self.conf, "domain", None),
        )

    def async_stop(self) -> None:
        """Stop listening and cancel tasks."""
        if self._unsub_event:
            self._unsub_event()
            self._unsub_event = None

        for button in SUPPORTED_BUTTONS:
            task = self._tasks.get(button)
            if task and not task.done():
                task.cancel()
            self._tasks[button] = None

        self._pressed = {btn: False for btn in SUPPORTED_BUTTONS}

    # ---------------------------------------------------------------------
    # Event payload mapping
    # ---------------------------------------------------------------------

    def _map_event_payload(
        self,
        data: Mapping[str, Any],
    ) -> Tuple[Optional[str], Optional[str]]:
        """Translate lutron_caseta event payload into (button, action)."""
        button = data.get("button_type")
        action = data.get("action")

        if not button or not action:
            return None, None

        button = str(button).lower()
        action = str(action).lower()

        if action not in ("press", "release"):
            return None, None

        return button, action
