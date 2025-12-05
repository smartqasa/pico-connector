from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .controller import PicoController

_LOGGER = logging.getLogger(__name__)


class PaddleProfile:
    """Paddle profile: tap = on/off, hold = ramp (lights only)."""

    def __init__(self, controller: "PicoController") -> None:
        self._ctrl = controller

    # -------------------------------------------------------------
    # Entry point called by the PicoController
    # -------------------------------------------------------------
    def handle(self, button: str, action: str) -> None:
        if button not in ("on", "off"):
            return

        if action == "press":
            self._handle_press(button)
        elif action == "release":
            self._handle_release(button)

    # -------------------------------------------------------------
    # PRESS
    # -------------------------------------------------------------
    def _handle_press(self, button: str) -> None:
        # Cancel any prior lifecycle task
        old = self._ctrl._tasks.get(button)
        if old and not old.done():
            old.cancel()

        self._ctrl._pressed[button] = True

        # Start lifecycle handler (tap vs hold)
        self._ctrl._tasks[button] = asyncio.create_task(
            self._hold_lifecycle(button)
        )

    # -------------------------------------------------------------
    # RELEASE
    # -------------------------------------------------------------
    def _handle_release(self, button: str) -> None:
        self._ctrl._pressed[button] = False
        task = self._ctrl._tasks.get(button)
        if task and not task.done():
            task.cancel()
        self._ctrl._tasks[button] = None

    # -------------------------------------------------------------
    # TAP vs HOLD logic
    # -------------------------------------------------------------
    async def _hold_lifecycle(self, button: str) -> None:
        """
        - Short tap → on/off
        - Hold → ramp (lights only)
        """
        try:
            await asyncio.sleep(self._ctrl._hold_time)

            # Released → short press
            if not self._ctrl._pressed.get(button, False):
                if button == "on":
                    await self._ctrl._short_press_on()
                else:
                    await self._ctrl._short_press_off()
                return

            # Still pressed → hold behavior
            if self._ctrl.conf.domain == "light":
                direction = 1 if button == "on" else -1
                await self._ramp_paddle(direction, button)
            else:
                # Non-light → act like tap
                if button == "on":
                    await self._ctrl._short_press_on()
                else:
                    await self._ctrl._short_press_off()

        except asyncio.CancelledError:
            pass
        finally:
            self._ctrl._pressed[button] = False
            self._ctrl._tasks[button] = None

    # -------------------------------------------------------------
    # LOCAL ramp implementation (unique to paddle)
    # -------------------------------------------------------------
    async def _ramp_paddle(self, direction: int, button: str) -> None:
        """Simple brightness ramp for paddle-only hold."""
        step_pct = self._ctrl.conf.step_pct
        step = step_pct * direction

        try:
            while self._ctrl._pressed.get(button, False):

                await self._ctrl._call_entity_service(
                    "turn_on",
                    {"brightness_step_pct": step},
                    continue_on_error=True,
                )

                await asyncio.sleep(self._ctrl._step_time)

        except asyncio.CancelledError:
            pass
