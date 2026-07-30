from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, Mapping, Optional, Tuple, TypeVar

from homeassistant.core import Event, HomeAssistant, callback

# Action modules
from .actions.base import DomainActions
from .actions.cover import CoverActions
from .actions.fan import FanActions
from .actions.light import LightActions
from .actions.media_player import MediaPlayerActions
from .actions.switch import SwitchActions
from .config import PicoConfig
from .const import DOMAIN, PICO_EVENT_TYPE, PICO_TYPE_MAP, SUPPORTED_BUTTONS

# Profiles
from .profiles.base import PicoProfile
from .profiles.pico_2b import Pico2Button
from .profiles.pico_3brl import Pico3ButtonRaiseLower
from .profiles.pico_4b import Pico4ButtonScene
from .profiles.pico_p2b import PaddleSwitchPico
from .utilities import SharedUtils

_LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")


BEHAVIOR_CLASSES = {
    "P2B": PaddleSwitchPico,
    "2B": Pico2Button,
    "3BRL": Pico3ButtonRaiseLower,
    "4B": Pico4ButtonScene,
}


class PicoController:
    """
    Controller for one configured Pico.

    - Action modules own domain and gesture state
    - Controller owns all asynchronous task lifecycles
    - Controller selects the hardware profile and dispatches events
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
        # All asynchronous work created for this Pico.
        self._tasks: set[asyncio.Future[Any]] = set()

        # Domain-level behaviors
        self.actions: dict[str, DomainActions] = {
            "cover": CoverActions(self),
            "fan": FanActions(self),
            "light": LightActions(self),
            "media_player": MediaPlayerActions(self),
            "switch": SwitchActions(self),
        }

    @property
    def behavior_name(self) -> Optional[str]:
        return self._behavior_name

    @callback
    def create_task(
        self,
        target: Coroutine[Any, Any, _T],
        name: str,
    ) -> asyncio.Task[_T]:
        """
        Create and track asynchronous work for this Pico.

        Home Assistant owns the task at the application level. The
        controller additionally owns it at the Pico lifecycle level.
        """
        task = self.hass.async_create_task(target)

        # Do not pass name= to async_create_task because Pico Link
        # currently supports Home Assistant 2023.1.
        task.set_name(f"{DOMAIN}:{self.conf.device_id}:{name}")

        self._tasks.add(task)
        task.add_done_callback(self._handle_task_done)

        return task

    @callback
    def _handle_task_done(self, task: asyncio.Future[Any]) -> None:
        """Remove a completed task and report unexpected failures."""
        self._tasks.discard(task)

        if task.cancelled():
            return

        try:
            task.result()
        except Exception:
            task_name = task.get_name() if isinstance(task, asyncio.Task) else "unnamed"

            _LOGGER.exception(
                "Device %s: task '%s' failed",
                self.conf.device_id,
                task_name,
            )

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
    async def async_stop(self) -> None:
        """Unsubscribe, cancel all Pico work, and await task completion."""

        # Prevent any new Pico events before cancelling current work.
        if self._unsub_event is not None:
            self._unsub_event()
            self._unsub_event = None

        # Let action modules clear their domain-specific gesture state.
        # Light and media-player modules also cancel their local hold tasks.
        for action_handler in self.actions.values():
            reset = getattr(action_handler, "reset_state", None)

            if callable(reset):
                reset()

        # Make a stable copy because task completion callbacks mutate
        # self._tasks as each cancellation completes.
        tasks = tuple(self._tasks)

        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

        self._tasks.clear()

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
