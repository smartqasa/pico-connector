# light_actions.py
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)


class LightActions:
    """
    Unified light action module implementing the full action API.

    Profiles:
        - only route press/release events
        - do NOT contain light logic

    LightActions:
        - tap vs hold
        - stepping
        - ramping
        - on/off/low_pct behavior
        - HA service calls
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl

        self._pressed: dict[str, bool] = {"raise": False, "lower": False}

        self._press_ts: dict[str, float] = {}
        self._tasks: dict[str, Optional[asyncio.Task]] = {
            "raise": None,
            "lower": None,
        }

    # ==============================================================
    # API METHODS (called by profiles)
    # ==============================================================

    # --- ON --------------------------------------------------------
    def press_on(self):
        asyncio.create_task(self._turn_on())

    def release_on(self):
        pass

    # --- OFF -------------------------------------------------------
    def press_off(self):
        asyncio.create_task(self._turn_off())

    def release_off(self):
        pass

    # --- STOP ------------------------------------------------------
    def press_stop(self):
        """
        STOP = execute middle_button actions (Lutron-like)
        or no-op if none defined.
        """
        actions = self.ctrl.conf.middle_button

        if not actions:
            _LOGGER.debug("Light STOP pressed: no middle_button actions configured")
            return

        for action in actions:
            asyncio.create_task(self.ctrl.utils.execute_button_action(action))

    def release_stop(self):
        pass

    # --- RAISE -----------------------------------------------------
    def press_raise(self):
        self._start_raise_lower("raise", direction=1)

    def release_raise(self):
        self._stop_raise_lower("raise")

    # --- LOWER -----------------------------------------------------
    def press_lower(self):
        self._start_raise_lower("lower", direction=-1)

    def release_lower(self):
        self._stop_raise_lower("lower")

    # ==============================================================
    # INTERNAL STATEFUL BEHAVIOR
    # ==============================================================

    def _start_raise_lower(self, button: str, direction: int):
        self._pressed[button] = True
        self._press_ts[button] = time.time()

        # TAP step immediately
        asyncio.create_task(self._step_brightness(direction))

        # HOLD → ramp
        task = asyncio.create_task(self._hold_lifecycle(button, direction))
        self._tasks[button] = task

    def _stop_raise_lower(self, button: str):
        self._pressed[button] = False

        task = self._tasks.get(button)
        if task and not task.done():
            task.cancel()

        self._tasks[button] = None

    # ==============================================================
    # TAP / HOLD LIFECYCLE
    # ==============================================================

    async def _hold_lifecycle(self, button: str, direction: int):
        try:
            await asyncio.sleep(self.ctrl.utils._hold_time)

            if not self._pressed.get(button):
                return  # TAP only

            # HOLD → continuous ramp
            await self._ramp(direction)

        except asyncio.CancelledError:
            pass

    # ==============================================================
    # DOMAIN LOGIC
    # ==============================================================

    async def _turn_on(self):
        pct = self.ctrl.conf.light_on_pct

        await self.ctrl.utils.call_service(
            "turn_on",
            {"brightness_pct": pct},
            domain="light",
        )

    async def _turn_off(self):
        await self.ctrl.utils.call_service(
            "turn_off",
            {},
            domain="light",
        )

    async def _step_brightness(self, direction: int):
        """
        TAP = single step brightness change.
        """

        step_pct = self.ctrl.conf.light_step_pct
        low_pct = self.ctrl.conf.light_low_pct

        state = self.ctrl.utils.get_entity_state()
        if not state:
            return

        raw_brightness = state.attributes.get("brightness")
        if raw_brightness is None:
            current_pct = 0
        else:
            try:
                current_pct = round((int(raw_brightness) / 255) * 100)
            except Exception:
                current_pct = 0

        new_pct = current_pct + (step_pct * direction)

        # Clamp
        if direction < 0:
            new_pct = max(low_pct, new_pct)
        new_pct = min(100, max(1, new_pct))

        await self.ctrl.utils.call_service(
            "turn_on",
            {"brightness_pct": new_pct},
            domain="light",
        )

    # ==============================================================
    # RAMP LOGIC (continuous)
    # ==============================================================

    async def _ramp(self, direction: int):
        """
        Continuous ramp:
        step by light_step_pct percentage every step_time.
        """

        step_time = self.ctrl.utils._step_time

        while any(self._pressed.values()):
            await self._step_brightness(direction)
            await asyncio.sleep(step_time)
