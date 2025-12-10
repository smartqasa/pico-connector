# fan_actions.py
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)


class FanActions:
    """
    Unified fan action module.

    Profiles must call:
        press_on / release_on
        press_off / release_off
        press_stop / release_stop
        press_raise / release_raise
        press_lower / release_lower
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl

        # Track per-button press state
        self._pressed = {"raise": False, "lower": False}
        self._press_ts: dict[str, float] = {}

        # Hold ramp tasks
        self._tasks: dict[str, Optional[asyncio.Task]] = {
            "raise": None,
            "lower": None,
        }

    # ==============================================================
    # ON / OFF / STOP
    # ==============================================================

    def press_on(self):
        asyncio.create_task(self._turn_on())

    def release_on(self):
        pass

    def press_off(self):
        asyncio.create_task(self._turn_off())

    def release_off(self):
        pass

    def press_stop(self):
        """
        STOP behavior for FAN:
        - If user configured custom middle_button actions → run them.
        - Otherwise → reverse direction (default behavior).
        """
        actions = self.ctrl.conf.middle_button

        if actions:
            # Run configured STOP actions
            for action in actions:
                asyncio.create_task(self.ctrl.utils.execute_button_action(action))
            return

        # Default STOP behavior → reverse direction
        asyncio.create_task(self._reverse_direction())

    def release_stop(self):
        # STOP is momentary, no hold state → no release logic required.
        pass


    # ==============================================================
    # RAISE / LOWER
    # ==============================================================

    def press_raise(self):
        self._begin_raise_lower("raise", direction=1)

    def release_raise(self):
        self._end_raise_lower("raise")

    def press_lower(self):
        self._begin_raise_lower("lower", direction=-1)

    def release_lower(self):
        self._end_raise_lower("lower")

    # ==============================================================
    # TAP + HOLD LOGIC
    # ==============================================================

    def _begin_raise_lower(self, button: str, direction: int):
        self._pressed[button] = True
        self._press_ts[button] = time.time()

        # TAP (one step immediately)
        asyncio.create_task(self._step_discrete(direction))

        # HOLD lifecycle
        task = asyncio.create_task(self._hold_lifecycle(button, direction))
        self._tasks[button] = task

    def _end_raise_lower(self, button: str):
        self._pressed[button] = False

        task = self._tasks.get(button)
        if task and not task.done():
            task.cancel()

        self._tasks[button] = None

    async def _hold_lifecycle(self, button: str, direction: int):
        try:
            await asyncio.sleep(self.ctrl.utils._hold_time)

            if not self._pressed.get(button):
                return  # tap only

            while self._pressed.get(button):
                await self._step_discrete(direction)
                await asyncio.sleep(self.ctrl.utils._step_time)

        except asyncio.CancelledError:
            pass

    # ==============================================================
    # FAN OPERATIONS
    # ==============================================================

    async def _turn_on(self):
        pct = self.ctrl.conf.fan_on_pct
        await self.ctrl.utils.call_service(
            "set_percentage",
            {"percentage": pct},
            domain="fan",
        )

    async def _turn_off(self):
        await self.ctrl.utils.call_service(
            "turn_off",
            {},
            domain="fan",
        )

    async def _reverse_direction(self):
        state = self.ctrl.utils.get_entity_state()
        if not state:
            return

        cur = state.attributes.get("direction")
        if cur not in ("forward", "reverse"):
            return

        new_dir = "reverse" if cur == "forward" else "forward"

        await self.ctrl.utils.call_service(
            "set_direction",
            {"direction": new_dir},
            domain="fan",
        )

    # ==============================================================
    # DISCRETE FAN SPEED STEPPING
    # ==============================================================

    async def _step_discrete(self, direction: int):
        speeds = self.ctrl.conf.fan_speeds
        ladder = self._build_speed_ladder(speeds)

        current = self._get_current_fan_percentage()
        if current is None:
            return

        # Find closest speed step
        idx = min(range(len(ladder)), key=lambda i: abs(ladder[i] - current))
        new_idx = max(0, min(len(ladder) - 1, idx + direction))

        if new_idx == idx:
            return  # already min/max

        new_pct = ladder[new_idx]

        await self.ctrl.utils.call_service(
            "set_percentage",
            {"percentage": new_pct},
            domain="fan",
        )

    # ==============================================================
    # HELPERS
    # ==============================================================

    def _build_speed_ladder(self, speeds: int) -> list[int]:
        steps = speeds - 1
        return [round(i * 100 / steps) for i in range(speeds)]

    def _get_current_fan_percentage(self) -> Optional[float]:
        state = self.ctrl.utils.get_entity_state()
        if not state:
            return None

        pct = state.attributes.get("percentage")
        if pct is None:
            # If fan is off, treat as 0%
            return 0.0 if state.state == "off" else float(self.ctrl.conf.fan_on_pct)

        try:
            return float(pct)
        except Exception:
            return None
