# cover_actions.py
from __future__ import annotations

import asyncio
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)


class CoverActions:
    """
    Standardized action API for covers.

    - ON (tap)    → open to cover_open_pos
    - OFF (tap)   → close fully
    - STOP        → middle_button or stop_cover

    - RAISE TAP   → step open
    - RAISE HOLD  → open_cover
    - RAISE REL   → stop_cover

    - LOWER TAP   → step close
    - LOWER HOLD  → close_cover
    - LOWER REL   → stop_cover
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl
        self._pressed: dict[str, bool] = {"raise": False, "lower": False}
        self._press_ts: dict[str, float] = {}

    # ==============================================================
    # PUBLIC API (what profiles expect)
    # ==============================================================

    # ---- ON ------------------------------------------------------
    def press_on(self):
        asyncio.create_task(self._open_to_pos())

    def release_on(self):
        pass  # tap-only

    # ---- OFF -----------------------------------------------------
    def press_off(self):
        asyncio.create_task(self._close_full())

    def release_off(self):
        pass  # tap-only

    # ---- STOP ----------------------------------------------------
    def press_stop(self):
        actions = self.ctrl.conf.middle_button
        if actions:
            for act in actions:
                asyncio.create_task(self.ctrl.utils.execute_button_action(act))
        else:
            asyncio.create_task(self._stop())

    def release_stop(self):
        pass

    # ---- RAISE ---------------------------------------------------
    def press_raise(self):
        self._handle_press("raise")

    def release_raise(self):
        self._handle_release("raise")

    # ---- LOWER ---------------------------------------------------
    def press_lower(self):
        self._handle_press("lower")

    def release_lower(self):
        self._handle_release("lower")

    # ==============================================================
    # INTERNAL TAP/HOLD LOGIC
    # ==============================================================

    def _handle_press(self, button: str):
        self._pressed[button] = True
        self._press_ts[button] = asyncio.get_event_loop().time()
        asyncio.create_task(self._press_lifecycle(button))

    def _handle_release(self, button: str):
        self._pressed[button] = False
        asyncio.create_task(self._release_lifecycle(button))

    async def _press_lifecycle(self, button: str):
        """Wait hold time → differentiate tap vs hold."""
        hold_time = self.ctrl.utils._hold_time
        await asyncio.sleep(hold_time)

        if not self._pressed.get(button):
            return  # was released → tap

        # HOLD = continuous open/close
        if button == "raise":
            await self._open_continuous()
        else:
            await self._close_continuous()

    async def _release_lifecycle(self, button: str):
        hold_time = self.ctrl.utils._hold_time
        now = asyncio.get_event_loop().time()
        start = self._press_ts.get(button, now)
        short_press = (now - start) < hold_time

        pos = self._get_position()

        # TAP behavior
        if short_press and pos is not None:
            await self._step(button, pos)

        # ALWAYS stop motion at release
        await self._stop()

    # ==============================================================
    # POSITION + DOMAIN COMMANDS
    # ==============================================================

    def _get_position(self) -> Optional[int]:
        state = self.ctrl.utils.get_entity_state()
        if not state:
            return None
        return state.attributes.get("current_position")

    async def _open_to_pos(self):
        pos = self.ctrl.conf.cover_open_pos
        if pos == 100:
            await self.ctrl.utils.call_service("open_cover", {}, domain="cover")
        else:
            await self.ctrl.utils.call_service(
                "set_cover_position", {"position": pos}, domain="cover"
            )

    async def _close_full(self):
        await self.ctrl.utils.call_service("close_cover", {}, domain="cover")

    async def _open_continuous(self):
        await self.ctrl.utils.call_service("open_cover", {}, domain="cover")

    async def _close_continuous(self):
        await self.ctrl.utils.call_service("close_cover", {}, domain="cover")

    async def _stop(self):
        await self.ctrl.utils.call_service("stop_cover", {}, domain="cover")

    async def _step(self, button: str, pos: int):
        step = self.ctrl.conf.cover_step_pct
        if button == "raise":
            new = min(100, pos + step)
        else:
            new = max(0, pos - step)

        await self.ctrl.utils.call_service(
            "set_cover_position", {"position": new}, domain="cover"
        )
