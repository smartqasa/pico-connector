# cover_actions.py
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)


class CoverActions:
    """
    Unified cover behavior for ALL profiles.

    P2B / 2B:
        ON tap  → open to cover_open_pos
        OFF tap → close fully
        ON/OFF tap while moving → STOP

    3BRL:
        on tap      → open to cover_open_pos
        off tap     → close fully
        raise tap   → step open
        raise hold  → open continuously until release
        lower tap   → step close
        lower hold  → close continuously until release
        release     → always STOP

    STOP (any profile):
        middle_button actions override default stop
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl

        # Track press timestamps for raise/lower
        self._press_ts: dict[str, float] = {}

        # Local button-press state for raise/lower (no dependency on controller._pressed)
        self._pressed: dict[str, bool] = {
            "raise": False,
            "lower": False,
        }

    # -------------------------------------------------------------
    # STATE HELPERS
    # -------------------------------------------------------------
    def _is_moving(self) -> bool:
        """Return True if the cover is currently opening or closing."""
        state = self.ctrl.utils.get_entity_state()
        if not state:
            return False
        return state.state in ("opening", "closing")

    def _current_position(self) -> Optional[int]:
        state = self.ctrl.utils.get_entity_state()
        if not state:
            return None
        return state.attributes.get("current_position")

    # -------------------------------------------------------------
    # PROFILE ROUTING
    # (Profiles call press_* / release_* below)
    # -------------------------------------------------------------

    # ----------------------- ON -----------------------
    def press_on(self):
        # STOP if moving
        if self._is_moving():
            asyncio.create_task(self._stop())
            return

        # Otherwise open to open_pos
        asyncio.create_task(self._open_to_position())

    def release_on(self):
        pass  # tap-only

    # ----------------------- OFF ----------------------
    def press_off(self):
        # STOP if moving
        if self._is_moving():
            asyncio.create_task(self._stop())
            return

        asyncio.create_task(self._close_full())

    def release_off(self):
        pass

    # ----------------------- STOP ----------------------
    def press_stop(self):
        """STOP button: run middle_button OR default stop."""
        actions = self.ctrl.conf.middle_button

        if actions:
            for action in actions:
                asyncio.create_task(self.ctrl.utils.execute_button_action(action))
            return

        asyncio.create_task(self._stop())

    def release_stop(self):
        pass

    # ----------------------- RAISE ---------------------
    def press_raise(self):
        """Tap = step, Hold = continuous open."""
        self._pressed["raise"] = True
        self._press_ts["raise"] = time.time()

        # TAP step immediately
        asyncio.create_task(self._step("raise"))

        # HOLD lifecycle
        asyncio.create_task(self._hold_lifecycle("raise"))

    def release_raise(self):
        self._pressed["raise"] = False
        asyncio.create_task(self._stop())

    # ----------------------- LOWER ---------------------
    def press_lower(self):
        """Tap = step, Hold = continuous close."""
        self._pressed["lower"] = True
        self._press_ts["lower"] = time.time()

        asyncio.create_task(self._step("lower"))
        asyncio.create_task(self._hold_lifecycle("lower"))

    def release_lower(self):
        self._pressed["lower"] = False
        asyncio.create_task(self._stop())

    # -------------------------------------------------------------
    # HOLD LOGIC FOR RAISE/LOWER
    # -------------------------------------------------------------
    async def _hold_lifecycle(self, button: str):
        """After hold_time, begin continuous open/close."""
        await asyncio.sleep(self.ctrl.utils._hold_time)

        if not self._pressed.get(button, False):
            return  # TAP only

        direction = "raise" if button == "raise" else "lower"
        await self._start_motion(direction)

    # -------------------------------------------------------------
    # DOMAIN ACTIONS
    # -------------------------------------------------------------
    async def _open_to_position(self):
        """Open to configured open position."""
        open_pos = self.ctrl.conf.cover_open_pos

        # Fully open
        if open_pos == 100:
            await self.ctrl.utils.call_service(
                "open_cover",
                {},
                domain="cover"
            )
            return

        # Go to set position
        await self.ctrl.utils.call_service(
            "set_cover_position",
            {"position": open_pos},
            domain="cover"
        )

    async def _close_full(self):
        await self.ctrl.utils.call_service(
            "close_cover",
            {},
            domain="cover"
        )

    async def _stop(self):
        await self.ctrl.utils.call_service(
            "stop_cover",
            {},
            domain="cover"
        )

    async def _start_motion(self, direction: str):
        svc = "open_cover" if direction == "raise" else "close_cover"
        await self.ctrl.utils.call_service(svc, {}, domain="cover")

    async def _step(self, button: str):
        """Single step open/close."""
        pos = self._current_position()
        if pos is None:
            return

        step = self.ctrl.conf.cover_step_pct

        if button == "raise":
            new_pos = min(100, pos + step)
        else:
            new_pos = max(0, pos - step)

        await self.ctrl.utils.call_service(
            "set_cover_position",
            {"position": new_pos},
            domain="cover"
        )
