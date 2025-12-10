# media_player_actions.py
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)


class MediaPlayerActions:
    """
    Media player behaviors:

    - on    → unmute OR turn_on (if supported)
    - off   → mute OR turn_off (if supported)
    - raise → step volume up / hold = ramp up
    - lower → step volume down / hold = ramp down
    - stop  → no-op (media players do not have a stop concept)
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl
        self._pressed: dict[str, bool] = {}
        self._tasks: dict[str, Optional[asyncio.Task]] = {}

    # -------------------------------------------------------------
    # PUBLIC ENTRY: PRESS
    # -------------------------------------------------------------
    def handle_press(self, button: str) -> None:
        match button:

            # -------------------------
            # POWER / MUTE LOGIC
            # -------------------------
            case "on":
                asyncio.create_task(self._turn_on())

            case "off":
                asyncio.create_task(self._turn_off())

            # -------------------------
            # NO-OP
            # -------------------------
            case "stop":
                _LOGGER.debug("MediaPlayerActions: stop → ignored")
                return

            # -------------------------
            # VOLUME CONTROL
            # -------------------------
            case "raise" | "lower":
                self._pressed[button] = True
                asyncio.create_task(self._step_volume(button))

                # HOLD → ramp
                task = asyncio.create_task(self._hold_lifecycle(button))
                self._tasks[button] = task

            case _:
                _LOGGER.debug("MediaPlayerActions: unknown button '%s'", button)

    # -------------------------------------------------------------
    # PUBLIC ENTRY: RELEASE
    # -------------------------------------------------------------
    def handle_release(self, button: str) -> None:
        if button not in ("raise", "lower"):
            return

        self._pressed[button] = False

        task = self._tasks.get(button)
        if task and not task.done():
            task.cancel()

        self._tasks[button] = None

    # -------------------------------------------------------------
    # POWER / MUTE IMPLEMENTATIONS
    # -------------------------------------------------------------
    async def _turn_on(self):
        """
        Media players vary wildly in supported services.
        Strategy:
        - Attempt turn_on()
        - Also unmute so 'on' is always audible
        """
        await self.ctrl._call_entity_service("turn_on", {})
        await self.ctrl._call_entity_service("volume_mute", {"is_volume_muted": False})


    async def _turn_off(self):
        """
        Strategy:
        - Attempt turn_off()
        - Also mute so 'off' always silences player
        """
        await self.ctrl._call_entity_service("turn_off", {})
        await self.ctrl._call_entity_service("volume_mute", {"is_volume_muted": True})


    # -------------------------------------------------------------
    # TAP STEP
    # -------------------------------------------------------------
    async def _step_volume(self, button: str):
        """Adjust volume one step (tap behavior)."""
        step_pct = self.ctrl.conf.media_player_vol_step  # already 1–100

        cur = self._get_current_volume()
        if cur is None:
            return

        mult = 1 if button == "raise" else -1
        new_pct = max(0.0, min(100.0, cur * 100 + step_pct * mult))

        await self.ctrl._call_entity_service(
            "volume_set",
            {"volume_level": new_pct / 100.0},
        )

    # -------------------------------------------------------------
    # HOLD → RAMP
    # -------------------------------------------------------------
    async def _hold_lifecycle(self, button: str):
        """Repeatedly apply volume steps until released."""
        try:
            await asyncio.sleep(self.ctrl._hold_time)

            if not self._pressed.get(button):
                return  # tap-only

            while self._pressed.get(button):
                await self._step_volume(button)
                await asyncio.sleep(self.ctrl._step_time)

        except asyncio.CancelledError:
            pass

    # -------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------
    def _get_current_volume(self) -> Optional[float]:
        """Return 0.0–1.0 volume"""
        state = self.ctrl.get_entity_state()
        if not state:
            return None

        try:
            vol = float(state.attributes.get("volume_level", 0.0))
        except Exception:
            vol = 0.0

        return max(0.0, min(1.0, vol))
