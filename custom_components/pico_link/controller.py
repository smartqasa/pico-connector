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
    """Main controller: routes events to the appropriate profile object."""

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

            # Device filter
            if data.get("device_id") != self.conf.device_id:
                return

            # Map into (button, action)
            button, action = self._map_event_payload(data)
            if button is None or action is None:
                return

            # Ignore unsupported buttons
            if button not in SUPPORTED_BUTTONS:
                _LOGGER.debug(
                    "Device %s: ignoring unsupported button '%s'",
                    self.conf.device_id,
                    button,
                )
                return

            # Lookup profile handler
            profile_obj = self._profiles.get(self.conf.profile)
            if not profile_obj:
                _LOGGER.warning(
                    "Device %s: unknown profile '%s'",
                    self.conf.device_id,
                    self.conf.profile,
                )
                return

            # Every profile now exposes: handle(button, action)
            try:
                profile_obj.handle(button, action)  # type: ignore[call-arg]
            except Exception as err:
                _LOGGER.error(
                    "Device %s: profile '%s' failed handling %s/%s: %s",
                    self.conf.device_id,
                    self.conf.profile,
                    button,
                    action,
                    err,
                )

        # Subscribe to bus events
        self._unsub_event = self.hass.bus.async_listen(PICO_EVENT_TYPE, _handle_event)

    def async_stop(self) -> None:
        """Stop listening and cancel tasks."""
        if self._unsub_event:
            self._unsub_event()
            self._unsub_event = None

        # Cancel any running ramp/hold tasks
        for button in SUPPORTED_BUTTONS:
            task = self._tasks.get(button)
            if task and not task.done():
                task.cancel()
            self._tasks[button] = None

        # Reset pressed state
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
