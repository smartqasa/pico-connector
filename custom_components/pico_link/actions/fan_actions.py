# fan_actions.py
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)


class FanActions:
    """
    Tap-only fan controller.

    Behaviors:
      ON tap     → turn on to fan_on_pct (default 100)
      OFF tap    → turn off
      RAISE tap  → next higher speed
      LOWER tap  → next lower speed
      STOP tap   → reverse direction (or middle_button override)

    Additional behavior:
      - If fan is OFF and RAISE is tapped → go to the first speed step
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl

    # ==============================================================
    # PUBLIC ENTRY POINTS (called by profiles)
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
        STOP behavior:
        - If user provided middle_button actions → run them.
        - Otherwise → reverse direction.
        """
        actions = self.ctrl.conf.middle_button

        if actions:
            for action in actions:
                asyncio.create_task(self.ctrl.utils.execute_button_action(action))
            return

        asyncio.create_task(self._reverse_direction())

    def release_stop(self):
        pass

    def press_raise(self):
        asyncio.create_task(self._step(1))

    def release_raise(self):
        pass

    def press_lower(self):
        asyncio.create_task(self._step(-1))

    def release_lower(self):
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
    # DISCRETE SPEED STEPPING
    # ==============================================================

    async def _step(self, direction: int):
        """
        Step fan speed up/down based on discrete ladder.
        If fan is OFF and stepping upward → go to first step.
        """

        ladder = self._get_speed_ladder()
        if not ladder:
            return

        current = self._get_current_pct()
        if current is None:
            return

        # If fan is off → treat as step from 0 → first step
        if current == 0 and direction > 0:
            new_pct = ladder[1]  # ladder[0] == 0, so first real step is index 1
        else:
            # Find closest index in ladder
            idx = min(range(len(ladder)), key=lambda i: abs(ladder[i] - current))
            new_idx = max(0, min(len(ladder) - 1, idx + direction))
            new_pct = ladder[new_idx]

        await self.ctrl.utils.call_service(
            "set_percentage",
            {"percentage": new_pct},
            domain="fan",
        )

    # ==============================================================
    # HELPERS
    # ==============================================================

    def _get_speed_ladder(self) -> List[int]:
        """
        Builds the ladder using HA's internal percentage_step.

        Example:
            percentage_step=25 → [0,25,50,75,100]
            percentage_step=33 → [0,33,66,99]
        """
        state = self.ctrl.utils.get_entity_state()
        if not state:
            return []

        step = state.attributes.get("percentage_step")
        if not isinstance(step, (int, float)) or step <= 0:
            # Fallback → assume 100%
            return [0, 100]

        ladder = [0]
        pct = step

        # Build until >= 100
        while pct < 100:
            ladder.append(int(pct))
            pct += step

        ladder.append(100)

        return ladder

    def _get_current_pct(self) -> Optional[int]:
        """
        Returns current fan percentage as an integer.
        If OFF → returns 0.
        """
        state = self.ctrl.utils.get_entity_state()
        if not state:
            return None

        if state.state == "off":
            return 0

        pct = state.attributes.get("percentage")
        if pct is None:
            return 0

        try:
            return int(pct)
        except Exception:
            return 0
