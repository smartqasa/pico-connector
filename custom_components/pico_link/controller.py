from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional, Tuple

from homeassistant.core import Event, HomeAssistant, callback

from .config import PicoConfig
from .const import SUPPORTED_BUTTONS, PICO_EVENT_TYPE, PICO_TYPE_MAP
from .shared_utils import SharedUtils

# Profiles
from .profiles.profile_base import PicoProfile
from .profiles.profile_3brl import Pico3ButtonRaiseLower
from .profiles.profile_p2b import PaddleSwitchPico
from .profiles.profile_2b import Pico2Button
from .profiles.profile_4b import Pico4ButtonScene

# Action modules
from .actions.light_actions import LightActions
from .actions.cover_actions import CoverActions
from .actions.fan_actions import FanActions
from .actions.switch_actions import SwitchActions
from .actions.media_player_actions import MediaPlayerActions

_LOGGER = logging.getLogger(__name__)


BEHAVIOR_CLASSES = {
    "P2B": PaddleSwitchPico,
    "2B": Pico2Button,
    "3BRL": Pico3ButtonRaiseLower,
    "4B": Pico4ButtonScene,
}


class PicoController:
    """
    Clean minimal controller:
    - No pressed/task state here
    - Action modules own all state + lifecycles
    - Controller only selects profile and dispatches events
    """

    def __init__(self, hass: HomeAssistant, conf: PicoConfig) -> None:
        self.hass = hass
        self.conf = conf

        # Shared non-domain helpers
        self.utils = SharedUtils(self)

        # Behavior selection
        self._behavior: Optional[PicoProfile] = None
        self._behavior_name: Optional[str] = None
        self._unsub_event = None

        # Domain-level behaviors
        self.actions: Dict[str, Any] = {
            "cover":        CoverActions(self),
            "fan":          FanActions(self),
            "light":        LightActions(self),
            "media_player": MediaPlayerActions(self),
            "switch":       SwitchActions(self),
        }

    @property
    def behavior_name(self) -> Optional[str]:
        return self._behavior_name

    # ---------------------------------------------------------
    # Start (subscribe to Pico events)
    # ---------------------------------------------------------
    async def async_start(self):
        # Ensure all action modules start clean
        for mod in self.actions.values():
            reset = getattr(mod, "reset_state", None)
            if callable(reset):
                reset()

        @callback
        def handle_event(event: Event):
            data = event.data

            # Only handle events for THIS Pico
            if data.get("device_id") != self.conf.device_id:
                return

            button, action = self._map_event(data)
            if button is None or button not in SUPPORTED_BUTTONS:
                return

            # First event triggers behavior selection
            if self._behavior is None:
                if not self._select_behavior(data):
                    return

            # PYLANCE-SAFE GUARD
            if self._behavior is None:
                _LOGGER.error(
                    "Device %s: behavior unexpectedly None during dispatch",
                    self.conf.device_id,
                )
                return

            # Dispatch to profile
            try:
                if action == "press":
                    self._behavior.handle_press(button)
                else:
                    self._behavior.handle_release(button)

            except Exception as e:
                _LOGGER.error(
                    "Device %s error in behavior '%s' during %s/%s: %s",
                    self.conf.device_id,
                    self._behavior_name,
                    button,
                    action,
                    e,
                )

        # Subscribe to lutron_caseta_button_event
        self._unsub_event = self.hass.bus.async_listen(
            PICO_EVENT_TYPE,
            handle_event,
        )

        _LOGGER.debug(
            "Device %s: subscribed to %s",
            self.conf.device_id,
            PICO_EVENT_TYPE,
        )

    # ---------------------------------------------------------
    # Select behavior profile (P2B, 2B, 3BRL, 4B)
    # ---------------------------------------------------------
    def _select_behavior(self, data: Mapping[str, Any]) -> bool:
        raw_type = data.get("type")

        if not raw_type:
            _LOGGER.error(
                "Device %s: missing 'type' in event; cannot determine behavior.",
                self.conf.device_id,
            )
            return False

        normalized = PICO_TYPE_MAP.get(raw_type)
        if not normalized:
            _LOGGER.error(
                "Device %s: unknown Pico type '%s'",
                self.conf.device_id,
                raw_type,
            )
            return False

        behavior_cls = BEHAVIOR_CLASSES.get(normalized)
        if not behavior_cls:
            _LOGGER.error(
                "Device %s: no implementation for Pico type '%s'",
                self.conf.device_id,
                normalized,
            )
            return False

        self._behavior = behavior_cls(self)
        self._behavior_name = normalized

        _LOGGER.debug(
            "Device %s: using behavior '%s' from HW type '%s'",
            self.conf.device_id,
            normalized,
            raw_type,
        )
        return True

    # ---------------------------------------------------------
    # Stop (unsubscribe + reset action modules)
    # ---------------------------------------------------------
    def async_stop(self):
        # Reset all action modules (cancel tasks, clear state)
        for mod in self.actions.values():
            reset = getattr(mod, "reset_state", None)
            if callable(reset):
                reset()

        if self._unsub_event:
            self._unsub_event()
            self._unsub_event = None

    # ---------------------------------------------------------
    # Convert raw Lutron event into normalized button + action
    # ---------------------------------------------------------
    def _map_event(
        self,
        data: Mapping[str, Any],
    ) -> Tuple[Optional[str], Optional[str]]:

        button = data.get("button_type")
        action = data.get("action")

        if not isinstance(button, str) or not isinstance(action, str):
            return None, None

        action = action.lower()
        if action not in ("press", "release"):
            return None, None

        return button.lower(), action
