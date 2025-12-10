# fan_actions.py
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)


class FanActions:
    """
    Encapsulates all fan logic:

    - on  → set to fan_on_pct
    - off → turn_off
    - stop → reverse direction
    - raise/lower:
        * tap  = next/previous speed step
        * hold = repeated stepping every step_time_ms
        * release = stop stepping
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl
        self._press_ts: dict[str, float] = {}
        self._hold_tasks: dict[str, Optional[asyncio.Task]] = {
            "raise": None,
            "lower": None,
        }

    # -------------------------------------------------------------
    # PUBLIC ENTRY: PRESS
    # -------------------------------------------------------------
    def handle_press(self, button: str) -> None:
        match button:

            case "on":
                asyncio.create_task(self._turn_on())

            case "off":
                asyncio.create_task(self._turn_off())

            case "stop":
                asyncio.create_task(self._reverse_direction())

            case "raise" | "lower":
                self._press_ts[button] = asyncio.get_event_loop().time()
                self.ctrl.utils._pressed[button] = True
                asyncio.create_task(self._handle_raise_lower_press(button))

            case _:
                _LOGGER.debug("FanActions: unrecognized button '%s'", button)

    # -------------------------------------------------------------
    # PUBLIC ENTRY: RELEASE
    # -------------------------------------------------------------
    def handle_release(self, button: str) -> None:
        if button in ("raise", "lower"):
            self.ctrl.utils._pressed[button] = False
            task = self._hold_tasks.get(button)
            if task and not task.done():
                task.cancel()
            self._hold_tasks[button] = None

    # -------------------------------------------------------------
    # ON / OFF / DIRECTION
    # -------------------------------------------------------------
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

        current = state.attributes.get("direction")
        if current in ("forward", "reverse"):
            new_dir = "reverse" if current == "forward" else "forward"
            await self.ctrl.utils.call_service(
                "set_direction",
                {"direction": new_dir},
                domain="fan",
            )

    # -------------------------------------------------------------
    # RAISE / LOWER TAP & HOLD HANDLING
    # -------------------------------------------------------------
    async def _handle_raise_lower_press(self, button: str):
        now = asyncio.get_event_loop().time()
        self._press_ts[button] = now

        direction = 1 if button == "raise" else -1

        # TAP (one step)
        await self._step_discrete(direction)

        # HOLD lifecycle
        task = asyncio.create_task(
            self._hold_lifecycle(button, direction)
        )
        self._hold_tasks[button] = task

    async def _hold_lifecycle(self, button: str, direction: int):
        try:
            await asyncio.sleep(self.ctrl.utils._hold_time)

            if not self.ctrl.utils._pressed.get(button, False):
                return

            interval = self.ctrl.utils._step_time

            while self.ctrl.utils._pressed.get(button, False):
                await self._step_discrete(direction)
                await asyncio.sleep(interval)

        except asyncio.CancelledError:
            pass

        finally:
            self._hold_tasks[button] = None
            self.ctrl.utils._pressed[button] = False

    # -------------------------------------------------------------
    # STEP LOGIC
    # -------------------------------------------------------------
    async def _step_discrete(self, direction: int):
        """
        Fan supports discrete speeds (4 or 6). We choose the nearest step and
        move one level up/down.
        """

        speeds = self.ctrl.conf.fan_speeds
        ladder = self._build_speed_ladder(speeds)

        current = self._get_current_fan_percentage()
        if current is None:
            return

        # Find nearest ladder index
        idx = min(
            range(len(ladder)),
            key=lambda i: abs(ladder[i] - current)
        )
        new_idx = max(0, min(len(ladder) - 1, idx + direction))

        if new_idx == idx:
            return  # already at edge

        new_pct = ladder[new_idx]

        await self.ctrl.utils.call_service(
            "set_percentage",
            {"percentage": new_pct},
            domain="fan",
        )

    # -------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------
    def _build_speed_ladder(self, speeds: int) -> list[int]:
        steps = speeds - 1
        return [round(i * 100 / steps) for i in range(speeds)]

    def _get_current_fan_percentage(self) -> Optional[float]:
        state = self.ctrl.utils.get_entity_state()
        if not state:
            return None

        pct = state.attributes.get("percentage")
        if pct is None:
            return 0.0 if state.state == "off" else float(self.ctrl.conf.fan_on_pct)

        try:
            return float(pct)
        except Exception:
            return None
