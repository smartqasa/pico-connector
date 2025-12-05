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
    - STOP (now optionally user-programmable)
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

        # -----------------------------------------------------------
        # MIDDLE BUTTON (STOP)
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

            # Stop any running ramp loops
            for b in ("raise", "lower"):
                self._ctrl._pressed[b] = False
                task = self._ctrl._tasks.get(b)
                if task and not task.done():
                    task.cancel()
                    self._ctrl._tasks[b] = None
            return

        # -----------------------------------------------------------
        # Standard ON/OFF
        # -----------------------------------------------------------
        if button == "on":
            asyncio.create_task(self._ctrl._short_press_on())
            return

        if button == "off":
            asyncio.create_task(self._ctrl._short_press_off())
            return

        # -----------------------------------------------------------
        # RAISE / LOWER (domain-specific)
        # -----------------------------------------------------------
        if button in ("raise", "lower"):

            # LIGHT DOMAIN — step first, then hold-check
            if self._ctrl.conf.domain == "light":
                direction = 1 if button == "raise" else -1

                # Mark the button as pressed
                self._ctrl._pressed[button] = True

                # STEP IMMEDIATELY (Lutron behavior)
                asyncio.create_task(
                    self._ctrl._call_entity_service(
                        "turn_on",
                        {"brightness_step_pct": self._ctrl.conf.step_pct * direction},
                    )
                )

                # Start hold-detection lifecycle
                self._ctrl._tasks[button] = asyncio.create_task(
                    self._hold_check_five(button, direction)
                )
                return

            # COVER DOMAIN
            if self._ctrl.conf.domain == "cover":
                svc = "open_cover" if button == "raise" else "close_cover"
                asyncio.create_task(self._ctrl._call_entity_service(svc, {}))
                return

            # FAN DOMAIN
            if self._ctrl.conf.domain == "fan":
                direction = 1 if button == "raise" else -1
                asyncio.create_task(self._ctrl._fan_step_discrete(direction))
                return

    # ------------------------------------------------------------------
    # Hold detection lifecycle (tap already executed!)
    # ------------------------------------------------------------------

    async def _hold_check_five(self, button: str, direction: int):
        """
        Proper Lutron-style logic:
        - Step happens IMMEDIATELY on press
        - Hold threshold determines whether to begin ramping
        - Ramp stops on release
        """
        try:
            await asyncio.sleep(self._ctrl._hold_time)

            # If button released early, tap is already complete → exit
            if not self._ctrl._pressed.get(button, False):
                return

            # Held long enough → start ramping
            await self._ctrl._ramp_loop(direction, active_button=button)

        except asyncio.CancelledError:
            pass

        finally:
            self._ctrl._pressed[button] = False
            self._ctrl._tasks[button] = None

    # ------------------------------------------------------------------
    # RELEASE handler – stops only this button’s activity
    # ------------------------------------------------------------------

    def _handle_release_five(self, button: str) -> None:
        if button in ("raise", "lower"):
            self._ctrl._pressed[button] = False
            task = self._ctrl._tasks.get(button)
            if task and not task.done():
                task.cancel()
            self._ctrl._tasks[button] = None
