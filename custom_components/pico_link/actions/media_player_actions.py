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

    - on    → unmute OR turn_on
    - off   → mute OR turn_off
    - raise → step volume up / hold = ramp up
    - lower → step volume down / hold = ramp down
    - stop  → no-op
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl
        self._pressed: dict[str, bool] = {}
        self._tasks: dict[str, Optional[asyncio.Task]] = {}

    # -------------------------------------------------------------
    # PRESS
    # -------------------------------------------------------------
    def handle_press(self, button: str) -> None:
        match button:

            # POWER-LIKE BEHAVIOR
            case "on":
                asyncio.create_task(self._turn_on())

            case "off":
                asyncio.create_task(self._turn_off())

            # MEDIA PLAYERS DO NOT HAVE STOP
            case "stop":
                _LOGGER.debug("MediaPlayerActions: stop → ignored")
                return

            # VOLUME CONTROL
            case "raise" | "lower":
                self._pressed[button] = True

                # TAP = step once immediately
                asyncio.create_task(self._step_volume(button))

                # HOLD = continuous stepping
                task = asyncio.create_task(self._hold_lifecycle(button))
                self._tasks[button] = task

            case _:
                _LOGGER.debug("MediaPlayerActions: unknown button '%s'", button)

    # -------------------------------------------------------------
    # RELEASE
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
    # POWER / MUTE
    # -------------------------------------------------------------
    async def _turn_on(self):
        """
        Best-effort:
        - turn_on()
        - unmute
        """
        await self.ctrl.utils.call_service(
            "turn_on",
            {},
            domain="media_player",
        )

        await self.ctrl.utils.call_service(
            "volume_mute",
            {"is_volume_muted": False},
            domain="media_player",
            continue_on_error=True,
        )

    async def _turn_off(self):
        """
        Best-effort:
        - turn_off()
        - mute
        """
        await self.ctrl.utils.call_service(
            "turn_off",
            {},
            domain="media_player",
        )

        await self.ctrl.utils.call_service(
            "volume_mute",
            {"is_volume_muted": True},
            domain="media_player",
            continue_on_error=True,
        )

    # -------------------------------------------------------------
    # TAP STEP
    # -------------------------------------------------------------
    async def _step_volume(self, button: str):
        """Tap volume step."""

        step_pct = self.ctrl.conf.media_player_vol_step  # already normalized 1–10

        current = self._get_current_volume()
        if current is None:
            return

        # Convert to 0–100 space for easy adds
        current_pct = current * 100.0

        mult = 1 if button == "raise" else -1
        new_pct = max(0.0, min(100.0, current_pct + (step_pct * mult)))

        await self.ctrl.utils.call_service(
            "volume_set",
            {"volume_level": new_pct / 100.0},
            domain="media_player",
        )

    # -------------------------------------------------------------
    # HOLD = continuous ramp
    # -------------------------------------------------------------
    async def _hold_lifecycle(self, button: str):
        try:
            # Wait to distinguish TAP vs HOLD
            await asyncio.sleep(self.ctrl.utils._hold_time)

            if not self._pressed.get(button):
                return  # tap only

            # HOLD → ramp continuously
            while self._pressed.get(button):
                await self._step_volume(button)
                await asyncio.sleep(self.ctrl.utils._step_time)

        except asyncio.CancelledError:
            pass

    # -------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------
    def _get_current_volume(self) -> Optional[float]:
        """Return current volume_level (0.0–1.0)."""
        state = self.ctrl.utils.get_entity_state()
        if not state:
            return None

        try:
            vol = float(state.attributes.get("volume_level", 0.0))
        except Exception:
            vol = 0.0

        return max(0.0, min(1.0, vol))
