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
    Encapsulates all cover-specific logic:

    - on  → open (respect cover_open_pos)
    - off → close
    - stop → stop

    - raise/lower:
        * tap  = step position +/- cover_step_pct
        * hold = open/close continuously
        * release = stop always
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl
        self._press_ts: dict[str, float] = {}

    # -------------------------------------------------------------
    # PUBLIC ENTRY POINTS
    # -------------------------------------------------------------
    def handle_press(self, button: str) -> None:
        match button:

            case "on":
                asyncio.create_task(self._open())

            case "off":
                asyncio.create_task(self._close())

            case "stop":
                actions = self.ctrl.conf.middle_button

                if actions:
                    # Custom middle button actions override default stop_cover
                    for action in actions:
                        asyncio.create_task(self.ctrl.utils.execute_button_action(action))
                else:
                    # Default STOP → stop the cover
                    asyncio.create_task(self._stop())

            case "raise" | "lower":
                self._press_ts[button] = asyncio.get_event_loop().time()
                self.ctrl.utils._pressed[button] = True
                asyncio.create_task(self._press_lifecycle(button))

            case _:
                _LOGGER.debug("CoverActions: unknown button '%s'", button)

    # -------------------------------------------------------------
    # TAP/HOLD LIFECYCLES
    # -------------------------------------------------------------
    async def _press_lifecycle(self, button: str):
        """Wait hold_time to decide TAP vs HOLD."""

        await asyncio.sleep(self.ctrl.utils._hold_time)

        # If button was released → it's a TAP (handled in release)
        if not self.ctrl.utils._pressed.get(button, False):
            return

        # HOLD → begin open or close movement
        direction = "raise" if button == "raise" else "lower"
        await self._start_motion(direction)

    async def _release_lifecycle(self, button: str):
        """Release event: TAP = step, then always STOP."""

        self.ctrl.utils._pressed[button] = False

        now = asyncio.get_event_loop().time()
        start = self._press_ts.get(button, now)
        elapsed = now - start

        pos = self._get_position()

        # TAP if short press
        if elapsed < self.ctrl.utils._hold_time and pos is not None:
            await self._step(button, pos)

        # Always stop cover motion
        await self._stop()

    # -------------------------------------------------------------
    # COVER POSITION HELPERS
    # -------------------------------------------------------------
    def _get_position(self) -> Optional[int]:
        state = self.ctrl.utils.get_entity_state()
        if not state:
            return None
        return state.attributes.get("current_position")

    # -------------------------------------------------------------
    # DOMAIN ACTIONS
    # -------------------------------------------------------------
    async def _start_motion(self, direction: str):
        svc = "open_cover" if direction == "raise" else "close_cover"

        await self.ctrl.utils.call_service(
            svc,
            {},
            domain="cover",
        )

    async def _open(self):
        pos = self.ctrl.conf.cover_open_pos

        # If fully open → use open_cover
        if pos == 100:
            await self.ctrl.utils.call_service(
                "open_cover",
                {},
                domain="cover",
            )
            return

        # Otherwise go to the configured open_pos
        await self.ctrl.utils.call_service(
            "set_cover_position",
            {"position": pos},
            domain="cover",
        )

    async def _close(self):
        await self.ctrl.utils.call_service(
            "close_cover",
            {},
            domain="cover",
        )

    async def _stop(self):
        await self.ctrl.utils.call_service(
            "stop_cover",
            {},
            domain="cover",
        )

    async def _step(self, button: str, pos: int):
        """Move % up/down based on configured step."""

        step_pct = self.ctrl.conf.cover_step_pct

        if button == "raise":
            new_pos = min(100, pos + step_pct)
        else:
            new_pos = max(0, pos - step_pct)

        await self.ctrl.utils.call_service(
            "set_cover_position",
            {"position": new_pos},
            domain="cover",
        )
