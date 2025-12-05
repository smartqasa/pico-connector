from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .controller import PicoController

_LOGGER = logging.getLogger(__name__)


class FiveButtonProfile:
    """Five-button profile:
    - ON/OFF
    - STOP (optional user-programmable)
    - RAISE/LOWER tap = step, hold = ramp
    """

    def __init__(self, controller: "PicoController") -> None:
        self._ctrl = controller

    # ------------------------------------------------------------------
    # Public handler
    # ------------------------------------------------------------------
    def handle(self, button: str, action: str) -> None:
        if action == "press":
            self._handle_press(button)
        elif action == "release":
            self._handle_release(button)

    # ------------------------------------------------------------------
    # PRESS
    # ------------------------------------------------------------------
    def _handle_press(self, button: str) -> None:

        # -----------------------------------------------------------
        # STOP → user-defined OR cover stop
        # -----------------------------------------------------------
        if button == "stop":
            middle_action = getattr(self._ctrl.conf, "middle_button", None)

            if middle_action:
                asyncio.create_task(self._ctrl._execute_button_action(middle_action))
                return

            if self._ctrl.conf.domain == "cover":
                asyncio.create_task(
                    self._ctrl._call_entity_service("stop_cover", {})
                )

            # Cancel raise/lower
            for b in ("raise", "lower"):
                self._ctrl._pressed[b] = False
                task = self._ctrl._tasks.get(b)
                if task and not task.done():
                    task.cancel()
                    self._ctrl._tasks[b] = None
            return

        # -----------------------------------------------------------
        # ON / OFF
        # -----------------------------------------------------------
        if button == "on":
            asyncio.create_task(self._ctrl._short_press_on())
            return

        if button == "off":
            asyncio.create_task(self._ctrl._short_press_off())
            return

        # -----------------------------------------------------------
        # RAISE / LOWER
        # -----------------------------------------------------------
        if button in ("raise", "lower"):

            # LIGHT DOMAIN
            if self._ctrl.conf.domain == "light":
                direction = 1 if button == "raise" else -1

                # Mark pressed
                self._ctrl._pressed[button] = True

                # IMMEDIATE brightness step (Lutron behavior)
                asyncio.create_task(
                    self._ctrl._call_entity_service(
                        "turn_on",
                        {"brightness_step_pct": self._ctrl.conf.step_pct * direction},
                    )
                )

                # Start hold-check
                self._ctrl._tasks[button] = asyncio.create_task(
                    self._hold_lifecycle(button, direction)
                )
                return

            # COVER domain
            if self._ctrl.conf.domain == "cover":
                svc = "open_cover" if button == "raise" else "close_cover"
                asyncio.create_task(self._ctrl._call_entity_service(svc, {}))
                return

            # FAN domain
            if self._ctrl.conf.domain == "fan":
                direction = 1 if button == "raise" else -1
                asyncio.create_task(self._ctrl._fan_step_discrete(direction))
                return

    # ------------------------------------------------------------------
    # HOLD lifecycle (tap already performed on press)
    # ------------------------------------------------------------------
    async def _hold_lifecycle(self, button: str, direction: int):
        try:
            # WAIT for hold threshold
            await asyncio.sleep(self._ctrl._hold_time)

            # Released before threshold → tap complete
            if not self._ctrl._pressed.get(button, False):
                return

            # Begin ramping
            await self._ramp_with_min_limit(button, direction)

        except asyncio.CancelledError:
            pass
        finally:
            self._ctrl._pressed[button] = False
            self._ctrl._tasks[button] = None

    # ------------------------------------------------------------------
    # RAMP WITH MIN-BRIGHTNESS LIMIT (5-button-specific)
    # ------------------------------------------------------------------
    async def _ramp_with_min_limit(self, button: str, direction: int):
        """
        This is the 5-button-specific wrapper around SharedBehaviors._ramp_loop.
        It prevents ramping below the lowest configured step level.
        """
        step_pct = self._ctrl.conf.step_pct
        min_brightness = round(254 * (step_pct / 100))
        if min_brightness < 1:
            min_brightness = 1

        try:
            while self._ctrl._pressed.get(button, False):

                # Get current brightness
                entity_id = self._ctrl.conf.entities[0]
                state = self._ctrl.hass.states.get(entity_id)
                
                if state is None:
                    break
                
                brightness = state.attributes.get("brightness", None)

                if brightness is None:
                    break

                # Check BEFORE applying the next step
                step_value = round(254 * (step_pct / 100))

                if direction < 0:  # dimming
                    next_brightness = brightness - step_value
                    if next_brightness < min_brightness:
                        # STOP BEFORE overshoot
                        break

                if direction > 0:  # brightening
                    next_brightness = brightness + step_value
                    if next_brightness > 254:
                        break

                # Apply the step
                await self._ctrl._call_entity_service(
                    "turn_on",
                    {"brightness_step_pct": step_pct * direction},
                    continue_on_error=True,
                )

                await asyncio.sleep(self._ctrl._step_time)

        except asyncio.CancelledError:
            pass

    # ------------------------------------------------------------------
    # RELEASE
    # ------------------------------------------------------------------
    def _handle_release(self, button: str) -> None:
        if button in ("raise", "lower"):
            self._ctrl._pressed[button] = False
            task = self._ctrl._tasks.get(button)
            if task and not task.done():
                task.cancel()
            self._ctrl._tasks[button] = None
