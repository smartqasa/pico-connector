from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Mapping, Optional, Tuple

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback

from .config import PicoConfig
from .const import (
    PROFILE_FIVE_BUTTON,
    PROFILE_PADDLE,
    PROFILE_TWO_BUTTON,
    SUPPORTED_BUTTONS,
    PICO_EVENT_TYPE,
)

_LOGGER = logging.getLogger(__name__)


class PicoController:
    """Implements press/hold/ramp behavior for a single Pico remote."""

    def __init__(self, hass: HomeAssistant, conf: PicoConfig) -> None:
        self.hass = hass
        self.conf = conf

        # Press state per logical button
        self._pressed: Dict[str, bool] = {btn: False for btn in SUPPORTED_BUTTONS}

        # Task per button to implement lifecycle/ramp
        self._tasks: Dict[str, Optional[asyncio.Task]] = {
            btn: None for btn in SUPPORTED_BUTTONS
        }

        # For future features (double-tap, etc.)
        self._last_press_ts: Dict[str, float] = {btn: 0.0 for btn in SUPPORTED_BUTTONS}

        # Unsubscribe callback from hass.bus.async_listen(...)
        self._unsub_event: Optional[CALLBACK_TYPE] = None

        # Convert ms → seconds
        self._hold_time = conf.hold_time_ms / 1000.0
        self._step_time = conf.step_time_ms / 1000.0

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
                    "Device %s: ignoring unsupported button '%s' (data=%s)",
                    self.conf.device_id,
                    button,
                    data,
                )
                return
            if self.conf.profile == PROFILE_PADDLE:
                self._handle_paddle_event(button, action)
            elif self.conf.profile == PROFILE_FIVE_BUTTON:
                self._handle_five_button_event(button, action)
            elif self.conf.profile == PROFILE_TWO_BUTTON:
                self._handle_two_button_event(button, action)


        self._unsub_event = self.hass.bus.async_listen(PICO_EVENT_TYPE, _handle_event)
        _LOGGER.info(
            "PicoController started for device %s controlling entities %s (profile=%s)",
            self.conf.device_id,
            self.conf.entities,
            self.conf.profile,
        )

    def async_stop(self) -> None:
        """Stop listening and cancel any running tasks."""
        if self._unsub_event:
            self._unsub_event()
            self._unsub_event = None

        for button in SUPPORTED_BUTTONS:
            task = self._tasks.get(button)
            if task and not task.done():
                task.cancel()
                _LOGGER.debug(
                    "Cancelled running task for button '%s' on device %s",
                    button,
                    self.conf.device_id,
                )
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

        if button is None or action is None:
            _LOGGER.debug(
                "Event for device %s missing button_type/action: %s",
                self.conf.device_id,
                data,
            )
            return None, None

        button = str(button).lower()
        action = str(action).lower()

        if action not in ("press", "release"):
            _LOGGER.debug(
                "Device %s: ignoring unsupported action '%s' (data=%s)",
                self.conf.device_id,
                action,
                data,
            )
            return None, None

        return button, action

    # ---------------------------------------------------------------------
    # Paddle profile: tap vs hold on ON/OFF
    # ---------------------------------------------------------------------

    def _handle_paddle_event(self, button: str, action: str) -> None:
        if button not in ("on", "off"):
            # For paddle profile we ignore other buttons (if any)
            return

        if action == "press":
            self._handle_press_paddle(button)
        elif action == "release":
            self._handle_release_paddle(button)

    def _handle_press_paddle(self, button: str) -> None:
        _LOGGER.debug(
            "Device %s (paddle): button '%s' press",
            self.conf.device_id,
            button,
        )

        old_task = self._tasks.get(button)
        if old_task and not old_task.done():
            old_task.cancel()
            _LOGGER.debug(
                "Device %s (paddle): cancelled previous task for '%s' (restart)",
                self.conf.device_id,
                button,
            )

        self._pressed[button] = True
        task = asyncio.create_task(self._press_lifecycle_paddle(button))
        self._tasks[button] = task

    def _handle_release_paddle(self, button: str) -> None:
        _LOGGER.debug(
            "Device %s (paddle): button '%s' release",
            self.conf.device_id,
            button,
        )
        self._pressed[button] = False

    async def _press_lifecycle_paddle(self, button: str) -> None:
        """Paddle lifecycle: hold_time decides short vs long press."""
        try:
            await asyncio.sleep(self._hold_time)

            if not self._pressed.get(button, False):
                # Tap (short press)
                if button == "on":
                    await self._short_press_on()
                else:
                    await self._short_press_off()
                return

            # Hold (long press) -> ramp (on = up, off = down)
            direction = 1 if button == "on" else -1
            await self._ramp_loop(direction, active_button=button)

        except asyncio.CancelledError:
            _LOGGER.debug(
                "Device %s (paddle): lifecycle task for '%s' cancelled",
                self.conf.device_id,
                button,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception(
                "Device %s (paddle): error in lifecycle for '%s': %s",
                self.conf.device_id,
                button,
                err,
            )
        finally:
            self._pressed[button] = False
            self._tasks[button] = None

    # ---------------------------------------------------------------------
    # Five-button profile: instant ON/OFF/STOP, ramp RAISE/LOWER
    # ---------------------------------------------------------------------

    def _handle_five_button_event(self, button: str, action: str) -> None:
        if action == "press":
            self._handle_press_five(button)
        elif action == "release":
            self._handle_release_five(button)

    def _handle_press_five(self, button: str) -> None:
        _LOGGER.debug(
            "Device %s (five_button): button '%s' press",
            self.conf.device_id,
            button,
        )

        # ON/OFF/STOP: ignore hold_time; act immediately.
        if button == "on":
            asyncio.create_task(self._short_press_on())
            return

        if button == "off":
            asyncio.create_task(self._short_press_off())
            return

        if button == "stop":
            # Stop any ramp that might be in progress
            for btn in ("raise", "lower"):
                self._pressed[btn] = False
                task = self._tasks.get(btn)
                if task and not task.done():
                    task.cancel()
                    self._tasks[btn] = None
            _LOGGER.debug(
                "Device %s (five_button): STOP pressed; halted ramping",
                self.conf.device_id,
            )
            return

        # RAISE / LOWER: start ramp immediately; no hold_time
        if button in ("raise", "lower"):
            direction = 1 if button == "raise" else -1

            # Cancel any existing ramp (either direction)
            for btn in ("raise", "lower"):
                task = self._tasks.get(btn)
                if task and not task.done():
                    task.cancel()
                    self._tasks[btn] = None
                self._pressed[btn] = False

            self._pressed[button] = True
            task = asyncio.create_task(self._ramp_loop(direction, active_button=button))
            self._tasks[button] = task

    # ---------------------------------------------------------------------
    # Two-button profile: simple ON/OFF only
    # ---------------------------------------------------------------------

    def _handle_two_button_event(self, button: str, action: str) -> None:
        """Two-button Pico: instant ON or OFF, no holds, no ramp."""
        if action != "press":
            # we ignore releases entirely
            return

        _LOGGER.debug(
            "Device %s (two_button): button '%s' press",
            self.conf.device_id,
            button,
        )

        if button == "on":
            asyncio.create_task(self._short_press_on())
            return

        if button == "off":
            asyncio.create_task(self._short_press_off())
            return

        _LOGGER.debug(
            "Device %s (two_button): ignoring unsupported button '%s'",
            self.conf.device_id,
            button,
        )

    def _handle_release_five(self, button: str) -> None:
        _LOGGER.debug(
            "Device %s (five_button): button '%s' release",
            self.conf.device_id,
            button,
        )

        # For raise/lower, release stops the ramp.
        if button in ("raise", "lower"):
            self._pressed[button] = False
            task = self._tasks.get(button)
            if task and not task.done():
                task.cancel()
                self._tasks[button] = None

        # For on/off/stop we don't care about release.

    # ---------------------------------------------------------------------
    # Shared behaviors
    # ---------------------------------------------------------------------

    async def _short_press_on(self) -> None:
        """Short ON press: set brightness to configured level."""
        _LOGGER.debug(
            "Device %s: ON → brightness_pct=%s for %s",
            self.conf.device_id,
            self.conf.brightness_on_pct,
            self.conf.entities,
        )
        await self._call_light_service(
            "turn_on",
            {"brightness_pct": self.conf.brightness_on_pct},
        )

    async def _short_press_off(self) -> None:
        """Short OFF press: turn lights off."""
        _LOGGER.debug(
            "Device %s: OFF → turn_off for %s",
            self.conf.device_id,
            self.conf.entities,
        )
        await self._call_light_service("turn_off", {})

    async def _ramp_loop(self, direction: int, active_button: str) -> None:
        """Repeatedly apply brightness_step_pct while that button is held."""
        step = self.conf.step_pct * direction
        _LOGGER.debug(
            "Device %s: ramp loop start (btn=%s dir=%s step_pct=%s step_time=%ss) for %s",
            self.conf.device_id,
            active_button,
            direction,
            self.conf.step_pct,
            self._step_time,
            self.conf.entities,
        )

        try:
            while self._pressed.get(active_button, False):
                await self._call_light_service(
                    "turn_on",
                    {"brightness_step_pct": step},
                    continue_on_error=True,
                )

                if not await self._brightness_in_range(direction):
                    _LOGGER.debug(
                        "Device %s: brightness limit reached, stopping ramp",
                        self.conf.device_id,
                    )
                    break

                await asyncio.sleep(self._step_time)
        except asyncio.CancelledError:
            _LOGGER.debug(
                "Device %s: ramp loop cancelled (btn=%s)",
                self.conf.device_id,
                active_button,
            )

    async def _brightness_in_range(self, direction: int) -> bool:
        """Check whether we should keep ramping in the given direction."""
        if not self.conf.entities:
            return False

        state = self.hass.states.get(self.conf.entities[0])
        if not state:
            return False

        brightness = state.attributes.get("brightness")
        if brightness is None:
            _LOGGER.debug(
                "Device %s: entity %s has no brightness attribute; continuing ramp",
                self.conf.device_id,
                self.conf.entities[0],
            )
            return True

        _LOGGER.debug(
            "Device %s: current brightness for %s is %s",
            self.conf.device_id,
            self.conf.entities[0],
            brightness,
        )

        if direction > 0 and brightness >= 254:
            return False
        if direction < 0 and brightness <= 1:
            return False
        return True

    async def _call_light_service(
        self,
        service: str,
        data: Dict[str, Any],
        continue_on_error: bool = False,
    ) -> None:
        """Call a light service for all configured entities."""
        service_data = {**data, "entity_id": self.conf.entities}
        try:
            await self.hass.services.async_call(
                "light",
                service,
                service_data,
                blocking=False,
            )
        except Exception as err:  # noqa: BLE001
            if continue_on_error:
                _LOGGER.debug(
                    "Device %s: error calling light.%s(%s): %s",
                    self.conf.device_id,
                    service,
                    service_data,
                    err,
                )
            else:
                _LOGGER.error(
                    "Device %s: error calling light.%s(%s): %s",
                    self.conf.device_id,
                    service,
                    service_data,
                    err,
                )
