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

    # Public entrypoint used by PicoController
    def handle(self, button: str, action: str) -> None:
        if button not in ("on", "off"):
            return

        if action == "press":
            self._handle_press_paddle(button)
        elif action == "release":
            self._handle_release_paddle(button)

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    def _handle_press_paddle(self, button: str) -> None:
        old_task = self._ctrl._tasks.get(button)
        if old_task and not old_task.done():
            old_task.cancel()

        self._ctrl._pressed[button] = True
        self._ctrl._tasks[button] = asyncio.create_task(
            self._press_lifecycle_paddle(button)
        )

    def _handle_release_paddle(self, button: str) -> None:
        self._ctrl._pressed[button] = False

    async def _press_lifecycle_paddle(self, button: str) -> None:
        """Hold = ramp (lights only). Tap = on/off."""
        try:
            await asyncio.sleep(self._ctrl._hold_time)

            # Short press
            if not self._ctrl._pressed.get(button, False):
                if button == "on":
                    await self._ctrl._short_press_on()
                else:
                    await self._ctrl._short_press_off()
                return

            # Long press (light domain only)
            if self._ctrl.conf.domain == "light":
                direction = 1 if button == "on" else -1
                await self._ctrl._ramp_loop(direction, active_button=button)
            else:
                # Non-light domains: act immediately, no hold behavior
                if button == "on":
                    await self._ctrl._short_press_on()
                else:
                    await self._ctrl._short_press_off()

        except asyncio.CancelledError:
            pass
        finally:
            self._ctrl._pressed[button] = False
            self._ctrl._tasks[button] = None
