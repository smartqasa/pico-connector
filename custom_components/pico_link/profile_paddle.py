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

    # ------------------------------------------------------------------
    # ENTRY POINTS CALLED BY PicoController
    # ------------------------------------------------------------------
    def handle_press(self, button: str) -> None:
        if button not in ("on", "off"):
            return

        # Cancel any previous lifecycle on this button
        existing = self._ctrl._tasks.get(button)
        if existing and not existing.done():
            existing.cancel()

        # Mark pressed
        self._ctrl._pressed[button] = True

        # Start lifecycle
        self._ctrl._tasks[button] = asyncio.create_task(
            self._press_lifecycle(button)
        )

    def handle_release(self, button: str) -> None:
        """
        DO NOT cancel lifecycle task here.
        That task determines TAP vs HOLD.
        """
        if button not in ("on", "off"):
            return

        self._ctrl._pressed[button] = False

    # ------------------------------------------------------------------
    # TAP / HOLD LIFECYCLE
    # ------------------------------------------------------------------
    async def _press_lifecycle(self, button: str):
        try:
            await asyncio.sleep(self._ctrl._hold_time)

            # TAP
            if not self._ctrl._pressed.get(button, False):
                if button == "on":
                    await self._ctrl._short_press_on()
                else:
                    await self._ctrl._short_press_off()
                return

            # HOLD – only lights ramp
            if self._ctrl.conf.domain == "light":
                direction = 1 if button == "on" else -1
                await self._ctrl._ramp(button, direction)
            else:
                # Non-light → treat hold as tap
                if button == "on":
                    await self._ctrl._short_press_on()
                else:
                    await self._ctrl._short_press_off()

        except asyncio.CancelledError:
            pass

        finally:
            self._ctrl._pressed[button] = False
            self._ctrl._tasks[button] = None