# controller.py
from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional, Tuple

from homeassistant.core import Event, HomeAssistant, callback

from .config import PicoConfig
from .const import SUPPORTED_BUTTONS, PICO_EVENT_TYPE, PICO_TYPE_MAP
from .shared_utils import SharedUtils

# Profiles
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
    Controller for a single Pico device:
    - receives the raw button events
    - selects a behavior profile (3BRL, 4B, etc.)
    - delegates all semantic actions to:
        → profile.* to interpret buttons
        → actions.* modules for domain behavior
    """

    def __init__(self, hass: HomeAssistant, conf: PicoConfig) -> None:
        self.hass = hass
        self.conf = conf

        # Track button state and async ramp/hold tasks
        self._pressed: Dict[str, bool] = {b: False for b in SUPPORTED_BUTTONS}
        self._tasks: Dict[str, Optional[Any]] = {b: None for b in SUPPORTED_BUTTONS}

        # Shared non-domain utilities
        self.utils = SharedUtils(self)

        # Determined once at runtime on first event
        self._behavior = None
        self._behavior_name = None
        self._unsub_event = None

        # Domain-specific actions
        self.actions = {
            "cover": CoverActions(self),
            "fan": FanActions(self),
            "light": LightActions(self),
            "media_player": MediaPlayerActions(self),
            "switch": SwitchActions(self),
        }

    # ---------------------------------------------------------
    # Subscribe to Pico events
    # ---------------------------------------------------------
    async def async_start(self):
        @callback
        def handle_event(event: Event):
            data = event.data

            # Only handle this Pico's events
            if data.get("device_id") != self.conf.device_id:
                return

            button, action = self._map_event(data)
            if button is None:
                return

            if button not in SUPPORTED_BUTTONS:
                _LOGGER.debug("Ignoring unsupported button '%s'", button)
                return

            # Select profile once
            if self._behavior is None:
                if not self._select_behavior(data):
                    return

            # Dispatch to behavior
            try:
                if self._behavior is None:
                    _LOGGER.error(
                        "Device %s: behavior unexpectedly None during dispatch",
                        self.conf.device_id,
                    )
                    return

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
            "Device %s: subscribed to event '%s'",
            self.conf.device_id,
            PICO_EVENT_TYPE,
        )


    # ---------------------------------------------------------
    # Determine which behavior to use (3BRL, 4B, etc.)
    # ---------------------------------------------------------
    def _select_behavior(self, data: Mapping[str, Any]) -> bool:
        raw_type = data.get("type")

        if not raw_type:
            _LOGGER.error(
                "Device %s: missing 'type' in event; cannot select behavior.",
                self.conf.device_id,
            )
            return False

        normalized = PICO_TYPE_MAP.get(raw_type)
        if not normalized:
            _LOGGER.error(
                "Device %s: unknown Pico hardware type '%s'",
                self.conf.device_id, raw_type,
            )
            return False

        behavior_cls = BEHAVIOR_CLASSES.get(normalized)
        if not behavior_cls:
            _LOGGER.error(
                "Device %s: no profile implemented for type '%s'",
                self.conf.device_id, normalized,
            )
            return False

        # Instantiate the profile
        self._behavior = behavior_cls(self)
        self._behavior_name = normalized

        _LOGGER.debug(
            "Device %s: using profile '%s' (from hardware type '%s')",
            self.conf.device_id, normalized, raw_type
        )
        return True

    # ---------------------------------------------------------
    # Stop controller
    # ---------------------------------------------------------
    def async_stop(self):
        if self._unsub_event:
            self._unsub_event()
            self._unsub_event = None

        # Cancel active tasks
        for t in self._tasks.values():
            if t and not t.done():
                t.cancel()

        # Reset state
        for b in SUPPORTED_BUTTONS:
            self._pressed[b] = False
            self._tasks[b] = None

    # ---------------------------------------------------------
    # Convert Lutron event payload → (button, action)
    # ---------------------------------------------------------
    def _map_event(self, data: Mapping[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        button = data.get("button_type")
        action = data.get("action")

        if not isinstance(button, str) or not isinstance(action, str):
            return None, None

        action = action.lower()
        if action not in ("press", "release"):
            return None, None

        return button.lower(), action
