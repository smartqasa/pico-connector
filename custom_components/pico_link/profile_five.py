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
    - STOP
    - RAISE/LOWER mapped by domain (light/fan/cover)
    """

    def __init__(self, controller: "PicoController") -> None:
        self._ctrl = controller

    # Public entrypoint used by PicoController
    def handle(self, button: str, action: str) -> None:
        if action == "press":
            self._handle_press_five(button)
        elif action == "release":
            self._handle_release_five(button)

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    def _handle_press_five(self, button: str) -> None:
        # Domain-specific STOP
        if button == "stop":
            if self._ctrl.conf.domain == "cover":
                asyncio.create_task(
                    self._ctrl._call_entity_service("stop_cover", {})
                )
            # Cancel raise/lower ramp
            for b in ("raise", "lower"):
                self._ctrl._pressed[b] = False
                task = self._ctrl._tasks.get(b)
                if task and not task.done():
                    task.cancel()
                    self._ctrl._tasks[b] = None
            return

        # Standard ON/OFF
        if button == "on":
            asyncio.create_task(self._ctrl._short_press_on())
            return

        if button == "off":
            asyncio.create_task(self._ctrl._short_press_off())
            return

        # Raise/Lower mapping
        if button in ("raise", "lower"):
            # COVER: simple open/close
            if self._ctrl.conf.domain == "cover":
                svc = "open_cover" if button == "raise" else "close_cover"
                asyncio.create_task(self._ctrl._call_entity_service(svc, {}))
                return

            # FAN: discrete speed steps based on configured speeds
            if self._ctrl.conf.domain == "fan":
                direction = 1 if button == "raise" else -1
                asyncio.create_task(self._ctrl._fan_step_discrete(direction))
                return

            # LIGHT: ramp brightness while held
            if self._ctrl.conf.domain == "light":
                direction = 1 if button == "raise" else -1

                # Cancel any existing raise/lower tasks
                for b in ("raise", "lower"):
                    task = self._ctrl._tasks.get(b)
                    if task and not task.done():
                        task.cancel()
                    self._ctrl._pressed[b] = False

                self._ctrl._pressed[button] = True
                self._ctrl._tasks[button] = asyncio.create_task(
                    self._ctrl._ramp_loop(direction, button)
                )

    def _handle_release_five(self, button: str) -> None:
        if button in ("raise", "lower"):
            self._ctrl._pressed[button] = False
            task = self._ctrl._tasks.get(button)
            if task and not task.done():
                task.cancel()
                self._ctrl._tasks[button] = None
