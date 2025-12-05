from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .controller import PicoController

_LOGGER = logging.getLogger(__name__)


class FiveButtonProfile:
    """5-button Pico:
    - on/off
    - stop (optional custom action)
    - raise/lower → tap = step, hold = ramp
    """

    def __init__(self, controller: "PicoController") -> None:
        self._ctrl = controller

    # -------------------------------------------------------------
    # ENTRY POINTS
    # -------------------------------------------------------------
    def handle_press(self, button: str, token: int) -> None:
        if button == "stop":
            self._handle_stop()
            return

        if button == "on":
            asyncio.create_task(self._ctrl._short_press_on())
            return

        if button == "off":
            asyncio.create_task(self._ctrl._short_press_off())
            return

        if button in ("raise", "lower"):
            self._handle_raise_lower(button, token)

    def handle_release(self, button: str) -> None:
        if button in ("raise", "lower"):
            self._ctrl._pressed[button] = False
            task = self._ctrl._tasks.get(button)
            if task and not task.done():
                task.cancel()
            self._ctrl._tasks[button] = None

    # -------------------------------------------------------------
    # STOP BUTTON
    # -------------------------------------------------------------
    def _handle_stop(self):
        middle_action = getattr(self._ctrl.conf, "middle_button", None)

        if middle_action:
            asyncio.create_task(self._ctrl._execute_button_action(middle_action))
            return

        if self._ctrl.conf.domain == "cover":
            asyncio.create_task(
                self._ctrl._call_entity_service("stop_cover", {})
            )

        # cancel raise/lower
        for b in ("raise", "lower"):
            self._ctrl._pressed[b] = False
            task = self._ctrl._tasks.get(b)
            if task and not task.done():
                task.cancel()
            self._ctrl._tasks[b] = None

    # -------------------------------------------------------------
    # RAISE / LOWER PRESS
    # -------------------------------------------------------------
    def _handle_raise_lower(self, button: str, token: int) -> None:
        direction = 1 if button == "raise" else -1
        domain = self._ctrl.conf.domain

        # LIGHT domain
        if domain == "light":
            self._ctrl._pressed[button] = True

            # immediate step
            asyncio.create_task(
                self._ctrl._call_entity_service(
                    "turn_on",
                    {"brightness_step_pct": self._ctrl.conf.step_pct * direction},
                )
            )

            # start lifecycle
            self._ctrl._tasks[button] = asyncio.create_task(
                self._light_lifecycle(button, direction, token)
            )
            return

        # COVER
        if domain == "cover":
            svc = "open_cover" if button == "raise" else "close_cover"
            asyncio.create_task(self._ctrl._call_entity_service(svc, {}))
            return

        # FAN
        if domain == "fan":
            asyncio.create_task(self._ctrl._fan_step_discrete(direction))

    # -------------------------------------------------------------
    # TAP/HOLD lifecycle (raise/lower)
    # -------------------------------------------------------------
    async def _light_lifecycle(self, button: str, direction: int, token: int):
        try:
            await asyncio.sleep(self._ctrl._hold_time)

            # stale press?
            if token != self._ctrl._press_tokens[button]:
                return

            # released before hold → tap already done
            if not self._ctrl._pressed.get(button, False):
                return

            # HOLD → ramp
            await self._ramp(button, direction, token)

        except asyncio.CancelledError:
            pass

        finally:
            self._ctrl._pressed[button] = False
            self._ctrl._tasks[button] = None

    # -------------------------------------------------------------
    # Ramp with low_pct stop
    # -------------------------------------------------------------
    async def _ramp(self, button: str, direction: int, my_token: int):
        step_pct = self._ctrl.conf.step_pct
        low_pct = self._ctrl.conf.low_pct

        # Convert step and low_pct to 0–255 brightness scale
        step_value = round(255 * (step_pct / 100))
        min_brightness = max(1, round(255 * (low_pct / 100)))

        try:
            while self._ctrl._pressed.get(button, False):

                # TOKEN CHECK — CRITICAL SAFETY
                if my_token != self._ctrl._press_tokens[button]:
                    return

                entity_id = self._ctrl.conf.entities[0]
                state = self._ctrl.hass.states.get(entity_id)
                if not state:
                    return

                b = state.attributes.get("brightness")
                if b is None:
                    return

                # ----------- PRE-CHECK FOR STOP CONDITIONS -----------
                if direction < 0:
                    next_b = b - step_value
                    if next_b < min_brightness:
                        await self._ctrl._call_entity_service(
                            "turn_on",
                            {"brightness": min_brightness},
                            continue_on_error=True,
                        )
                        return

                if direction > 0:
                    next_b = b + step_value
                    if next_b > 255:
                        await self._ctrl._call_entity_service(
                            "turn_on",
                            {"brightness": 255},
                            continue_on_error=True,
                        )
                        return

                # ----------- APPLY STEP -----------
                await self._ctrl._call_entity_service(
                    "turn_on",
                    {"brightness_step_pct": step_pct * direction},
                    continue_on_error=True,
                )

                await asyncio.sleep(self._ctrl._step_time)

        except asyncio.CancelledError:
            pass


