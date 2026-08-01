from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any, Mapping, Optional, TypeVar

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

    Responsibilities:
        - Select the profile from the configured Pico type.
        - Verify that reported hardware events match that configured type.
        - Dispatch Pico events to the selected profile.
        - Own all asynchronous task lifecycles.
        - Stop domain gesture state during shutdown.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        conf: PicoConfig,
    ) -> None:
        self.hass = hass
        self.conf = conf

        # Shared non-domain helpers.
        self.utils = SharedUtils(self)

        # All asynchronous work created for this Pico.
        self._tasks: set[asyncio.Future[Any]] = set()

        # Event-listener unsubscribe callback.
        self._unsub_event: Optional[Callable[[], None]] = None

        # Avoid repeatedly logging the same hardware-type problem for
        # every event received from a mismatched or unsupported Pico.
        self._last_type_error: Optional[str] = None

        # Domain-level behaviors.
        self.actions: dict[str, DomainActions] = {
            "cover": CoverActions(self),
            "fan": FanActions(self),
            "light": LightActions(self),
            "media_player": MediaPlayerActions(self),
            "switch": SwitchActions(self),
        }

        # Configuration is authoritative. PicoConfig.validate() has
        # already confirmed that conf.type is a supported configured type.
        behavior_class = BEHAVIOR_CLASSES.get(self.conf.type)

        if behavior_class is None:
            raise ValueError(
                f"Device {self.conf.device_id}: no behavior implementation "
                f"exists for configured Pico type {self.conf.type!r}"
            )

        self._behavior: PicoProfile = behavior_class(self)

    # =============================================================
    # TASK MANAGEMENT
    # =============================================================

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
    def _handle_task_done(
        self,
        task: asyncio.Future[Any],
    ) -> None:
        """Remove a completed task and report unexpected failures."""
        self._tasks.discard(task)

        if task.cancelled():
            return

        try:
            task.result()
        except Exception:
            task_name = task.get_name() if isinstance(task, asyncio.Task) else "unnamed"

            _LOGGER.exception(
                "Device %s: task %r failed",
                self.conf.device_id,
                task_name,
            )

    # =============================================================
    # START
    # =============================================================

    async def async_start(self) -> None:
        """Reset domain handlers and subscribe to Pico events."""
        for action_handler in self.actions.values():
            reset = getattr(
                action_handler,
                "reset_state",
                None,
            )

            if callable(reset):
                reset()

        @callback
        def handle_event(event: Event) -> None:
            data = event.data

            # Only process events belonging to this configured Pico.
            if data.get("device_id") != self.conf.device_id:
                return

            # Configuration selects the behavior. The reported event
            # type is used only to verify that the hardware matches.
            if not self._event_type_matches(data):
                return

            button, action = self._map_event(data)

            if button is None or action is None or button not in SUPPORTED_BUTTONS:
                return

            try:
                if action == "press":
                    self._behavior.handle_press(button)
                else:
                    self._behavior.handle_release(button)

            except Exception:
                _LOGGER.exception(
                    "Device %s error in configured behavior %s during %s/%s",
                    self.conf.device_id,
                    self.conf.type,
                    button,
                    action,
                )

        self._unsub_event = self.hass.bus.async_listen(
            PICO_EVENT_TYPE,
            handle_event,
        )

        _LOGGER.debug(
            "Device %s: subscribed to %s using configured behavior %s",
            self.conf.device_id,
            PICO_EVENT_TYPE,
            self.conf.type,
        )

    # =============================================================
    # HARDWARE-TYPE VERIFICATION
    # =============================================================

    def _event_type_matches(
        self,
        data: Mapping[str, Any],
    ) -> bool:
        """
        Verify that the event's reported type matches the configuration.

        The configured type remains authoritative. An event is ignored
        when the reported hardware type is missing, unsupported, or does
        not match the configured type.
        """
        raw_type = data.get("type")

        if not isinstance(raw_type, str):
            self._log_type_error_once(
                "invalid-type",
                "Device %s: event is missing a valid Pico hardware type; "
                "configured type is %s",
                self.conf.device_id,
                self.conf.type,
            )
            return False

        reported_type = PICO_TYPE_MAP.get(raw_type)

        if reported_type is None:
            self._log_type_error_once(
                f"unsupported:{raw_type}",
                "Device %s: reported unsupported Pico hardware type %r; "
                "configured type is %s",
                self.conf.device_id,
                raw_type,
                self.conf.type,
            )
            return False

        if reported_type != self.conf.type:
            self._log_type_error_once(
                f"mismatch:{reported_type}:{self.conf.type}",
                "Device %s is configured as %s but reported hardware "
                "type %s (%s); this event will be ignored",
                self.conf.device_id,
                self.conf.type,
                reported_type,
                raw_type,
            )
            return False

        # Clear a previous error after receiving a valid matching event.
        self._last_type_error = None

        return True

    def _log_type_error_once(
        self,
        error_key: str,
        message: str,
        *args: Any,
    ) -> None:
        """Log each distinct hardware-type problem only once."""
        if self._last_type_error == error_key:
            return

        self._last_type_error = error_key
        _LOGGER.error(
            message,
            *args,
        )

    # =============================================================
    # STOP
    # =============================================================

    async def async_stop(self) -> None:
        """Unsubscribe, cancel all Pico work, and await completion."""
        # Prevent new Pico events before canceling current work.
        if self._unsub_event is not None:
            self._unsub_event()
            self._unsub_event = None

        # Let domain handlers clear their gesture-specific state.
        for action_handler in self.actions.values():
            reset = getattr(
                action_handler,
                "reset_state",
                None,
            )

            if callable(reset):
                reset()

        # Task completion callbacks mutate self._tasks, so operate on
        # a stable copy.
        tasks = tuple(self._tasks)

        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

        self._tasks.clear()

    # =============================================================
    # EVENT NORMALIZATION
    # =============================================================

    def _map_event(
        self,
        data: Mapping[str, Any],
    ) -> tuple[Optional[str], Optional[str]]:
        """Return a normalized button and press/release action."""
        button = data.get("button_type")
        action = data.get("action")

        if not isinstance(button, str):
            return None, None

        if not isinstance(action, str):
            return None, None

        normalized_action = action.lower()

        if normalized_action not in ("press", "release"):
            return None, None

        return (
            button.lower(),
            normalized_action,
        )
