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
    Clean, deterministic cover behavior:

    ON (tap)          → open to cover_open_pos
    OFF (tap)         → close fully

    RAISE (tap)       → step open
    RAISE (hold)      → open_cover (continuous)
    RAISE (release)   → stop_cover

    LOWER (tap)       → step close
    LOWER (hold)      → close_cover (continuous)
    LOWER (release)   → stop_cover

    STOP/MIDDLE (tap) → middle_button actions OR stop_cover
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl

        # Track hold vs tap
        self._pressed: dict[str, bool] = {
            "raise": False,
            "lower": False,
        }
        self._press_ts: dict[str, float] = {}

    # -------------------------------------------------------------
    # PRESS
    # -------------------------------------------------------------
    def handle_press(self, button: str) -> None:
        match button:

            # ON → open to preset position
            case "on":
                asyncio.create_task(self._open_to_pos())
                return

            # OFF → fully close
            case "off":
                asyncio.create_task(self._close_full())
                return

            # MIDDLE → stop or run user actions
            case "stop":
                actions = self.ctrl.conf.middle_button
                if actions:
                    for action in actions:
                        asyncio.create_task(self.ctrl.utils.execute_button_action(action))
                else:
                    asyncio.create_task(self._stop())
                return

            # RAISE / LOWER logic
            case "raise" | "lower":
                self._pressed[button] = True
                self._press_ts[button] = asyncio.get_event_loop().time()
                asyncio.create_task(self._press_lifecycle(button))
                return

            case _:
                _LOGGER.debug("CoverActions: unknown button '%s'", button)
                return

    # -------------------------------------------------------------
    # RELEASE
    # -------------------------------------------------------------
    def handle_release(self, button: str) -> None:
        if button not in ("raise", "lower"):
            return

        self._pressed[button] = False
        asyncio.create_task(self._release_lifecycle(button))

    # -------------------------------------------------------------
    # TAP / HOLD resolution
    # -------------------------------------------------------------
    async def _press_lifecycle(self, button: str):
        """Differentiate TAP vs HOLD."""
        hold_time = self.ctrl.utils._hold_time

        await asyncio.sleep(hold_time)

        # If released → TAP
        if not self._pressed.get(button):
            return

        # HOLD → continuous open/close
        if button == "raise":
            await self._open_continuous()
        else:
            await self._close_continuous()

    async def _release_lifecycle(self, button: str):
        """Handle tap step & always stop."""
        hold_time = self.ctrl.utils._hold_time
        now = asyncio.get_event_loop().time()
        start = self._press_ts.get(button, now)

        short_press = (now - start) < hold_time
        position = self._get_position()

        if short_press and position is not None:
            await self._step(button, position)

        # ALWAYS stop movement
        await self._stop()

    # -------------------------------------------------------------
    # POSITION HELPERS
    # -------------------------------------------------------------
    def _get_position(self) -> Optional[int]:
        state = self.ctrl.utils.get_entity_state()
        if not state:
            return None
        return state.attributes.get("current_position")

    # -------------------------------------------------------------
    # DOMAIN ACTIONS
    # -------------------------------------------------------------
    async def _open_to_pos(self):
        pos = self.ctrl.conf.cover_open_pos

        # If open_pos = 100 → standard open
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
        """One-step increment/decrement."""
        step_pct = self.ctrl.conf.cover_step_pct

        if button == "raise":
            new_pos = min(100, pos + step_pct)
        else:
            new_pos = max(0, pos - step_pct)

        await self.ctrl.utils.call_service(
            "set_cover_position", {"position": new_pos}, domain="cover"
        )
