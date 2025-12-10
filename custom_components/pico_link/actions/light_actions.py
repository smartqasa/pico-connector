# light_actions.py
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)


class LightActions:
    """
    Encapsulates all light-specific logic:

    - on: turn_on → light_on_pct
    - off: turn_off
    - raise/lower:
        * tap  = step brightness +/- light_step_pct
        * hold = ramp using SharedBehaviors._ramp()
        * release = stop ramp
    - stop: cancels ramp (lights have no native stop)
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl
        self._press_ts: dict[str, float] = {}

    # -------------------------------------------------------------
    # PUBLIC ENTRY POINTS
    # -------------------------------------------------------------
    def handle_press(self, button: str) -> None:
        """
        Profiles call this for all button presses.
        """

        match button:

            case "on":
                asyncio.create_task(self._turn_on())

            case "off":
                asyncio.create_task(self._turn_off())

            case "stop":
                # Lights have no real stop → just cancel ramp
                self._cancel_ramp()
                return

            case "raise" | "lower":
                self._handle_raise_lower_press(button)

            case _:
                _LOGGER.debug("LightActions: unrecognized button '%s'", button)

    def handle_release(self, button: str) -> None:
        """
        Release only applies to raise/lower:
        - Cancel ramp
        """
        if button in ("raise", "lower"):
            self._cancel_ramp()

    # -------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------
    def _cancel_ramp(self):
        """Cancel any running ramp task."""
        for btn in ("raise", "lower"):
            self.ctrl._pressed[btn] = False
            task = self.ctrl._tasks.get(btn)
            if task and not task.done():
                task.cancel()
            self.ctrl._tasks[btn] = None

    # -------------------------------------------------------------
    # ON / OFF
    # -------------------------------------------------------------
    async def _turn_on(self):
        pct = self.ctrl.conf.light_on_pct or 100
        await self.ctrl._call_entity_service(
            "turn_on",
            {"brightness_pct": pct},
        )

    async def _turn_off(self):
        await self.ctrl._call_entity_service("turn_off", {})

    # -------------------------------------------------------------
    # RAISE / LOWER PRESS
    # -------------------------------------------------------------
    def _handle_raise_lower_press(self, button: str):
        direction = 1 if button == "raise" else -1

        # Always mark pressed for ramp cancellation
        self.ctrl._pressed[button] = True

        # STEP immediately (tap behavior)
        asyncio.create_task(self._step_brightness(direction))

        # Start HOLD lifecycle
        self.ctrl._tasks[button] = asyncio.create_task(
            self._hold_lifecycle(button, direction)
        )

    # -------------------------------------------------------------
    # TAP/HOLD lifecycle
    # -------------------------------------------------------------
    async def _hold_lifecycle(self, button: str, direction: int):
        try:
            await asyncio.sleep(self.ctrl._hold_time)

            # If released → no hold behavior
            if not self.ctrl._pressed.get(button, False):
                return

            # HOLD → continuous ramp
            await self.ctrl._ramp(button, direction)

        except asyncio.CancelledError:
            pass

        finally:
            self.ctrl._pressed[button] = False
            self.ctrl._tasks[button] = None

    # -------------------------------------------------------------
    # STEP BRIGHTNESS
    # -------------------------------------------------------------
    async def _step_brightness(self, direction: int):
        """
        TAP behavior:
        - Raise/lower brightness by light_step_pct
        - Never go below light_low_pct
        """

        step_pct = self.ctrl.conf.light_step_pct or 10
        low_pct = self.ctrl.conf.light_low_pct or 1

        state = self.ctrl.get_entity_state()
        if not state:
            return

        current = state.attributes.get("brightness")
        if current is None:
            current_pct = 0
        else:
            try:
                current_pct = round((int(current) / 255) * 100)
            except Exception:
                current_pct = 0

        # Calculate new brightness
        new_pct = current_pct + (step_pct * direction)

        # Clamp minimum for LOWER
        if direction < 0:
            new_pct = max(low_pct, new_pct)

        # Clamp max for RAISE
        new_pct = min(100, new_pct)

        await self.ctrl._call_entity_service(
            "turn_on",
            {"brightness_pct": new_pct},
        )
