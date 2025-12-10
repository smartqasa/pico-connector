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
    - on  → open
    - off → close
    - stop → stop
    - raise/lower:
        * tap  = step position +/- step_pct
        * hold = open/close
        * release = stop
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl
        self._press_ts: dict[str, float] = {}

    # -------------------------------------------------------------
    # PUBLIC ENTRY POINTS
    # -------------------------------------------------------------
    def handle_press(self, button: str) -> None:
        """
        Dispatches button press:
        - raise/lower → tap/hold logic
        - on/off → simple open/close
        - stop → stop immediately
        """
        match button:
            case "on":
                asyncio.create_task(self._open())

            case "off":
                asyncio.create_task(self._close())

            case "stop":
                asyncio.create_task(self._stop())

            case "raise" | "lower":
                self._press_ts[button] = asyncio.get_event_loop().time()
                self.ctrl._pressed[button] = True
                asyncio.create_task(self._press_lifecycle(button))

            case _:
                _LOGGER.debug(
                    "CoverActions: unrecognized button '%s' for cover domain",
                    button,
                )

    def handle_release(self, button: str) -> None:
        """
        Dispatch release:
        - raise/lower → tap logic + stop
        - on/off/stop → no-op
        """
        if button in ("raise", "lower"):
            asyncio.create_task(self._release_lifecycle(button))

    # -------------------------------------------------------------
    # INTERNAL LIFECYCLES FOR RAISE/LOWER
    # -------------------------------------------------------------
    async def _press_lifecycle(self, button: str):
        """Wait to determine tap/hold."""
        await asyncio.sleep(self.ctrl._hold_time)

        if not self.ctrl._pressed.get(button, False):
            return  # TAP will be handled in release

        # HOLD → continuous motion
        direction = "raise" if button == "raise" else "lower"
        await self._start_motion(direction)

    async def _release_lifecycle(self, button: str):
        """Release: tap = step; always stop movement."""
        self.ctrl._pressed[button] = False

        now = asyncio.get_event_loop().time()
        start = self._press_ts.get(button, now)
        elapsed = now - start

        pos = self._get_position()

        # TAP: short press → step movement
        if elapsed < self.ctrl._hold_time and pos is not None:
            await self._step(button, pos)

        # Always stop
        await self._stop()

    # -------------------------------------------------------------
    # DOMAIN ACTION IMPLEMENTATIONS
    # -------------------------------------------------------------
    def _get_position(self) -> Optional[int]:
        state = self.ctrl.get_entity_state()
        if not state:
            return None
        return state.attributes.get("current_position")

    async def _start_motion(self, direction: str):
        svc = "open_cover" if direction == "raise" else "close_cover"
        await self.ctrl._call_entity_service(svc, {})

    async def _open(self):
        """
        OPEN behavior:
        - If open_pos == 100 → fully open using open_cover
        - Otherwise          → set_cover_position to open_pos
        """
        pos = self.ctrl.conf.cover_open_pos

        if pos == 100:
            await self.ctrl._call_entity_service("open_cover", {})
            return

        await self.ctrl._call_entity_service(
            "set_cover_position",
            {"position": pos}
        )

    async def _close(self):
        await self.ctrl._call_entity_service("close_cover", {})

    async def _stop(self):
        await self.ctrl._call_entity_service("stop_cover", {})

    async def _step(self, button: str, pos: int):
        """Move cover position by configured step_pct."""
        step_pct = self.ctrl.conf.cover_step_pct or 5

        if button == "raise":
            new_pos = min(100, pos + step_pct)
        else:
            new_pos = max(0, pos - step_pct)

        await self.ctrl._call_entity_service(
            "set_cover_position", {"position": new_pos}
        )
