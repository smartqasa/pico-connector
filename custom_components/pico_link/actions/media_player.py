from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)


class MediaPlayerActions:
    """
    Unified media_player action module implementing the full action API.

    Semantics:
        - on    (tap) → play / pause
        - off   (tap) → next track
        - raise (tap) → volume step up
        - raise (hold) → volume ramp up
        - lower (tap) → volume step down
        - lower (hold) → volume ramp down
        - stop  (tap) → middle_button actions OR mute/unmute
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl

        # Track pressed state (raise/lower only)
        self._pressed: dict[str, bool] = {
            "raise": False,
            "lower": False,
        }

        # Track press timestamps (debug / future use)
        self._press_ts: dict[str, float] = {}

        # Async tasks per button
        self._tasks: dict[str, Optional[asyncio.Task]] = {
            "raise": None,
            "lower": None,
        }

    # ==============================================================
    # API METHODS (called by profiles)
    # ==============================================================

    # --- ON --------------------------------------------------------
    def press_on(self):
        asyncio.create_task(self._play_pause())

    def release_on(self):
        pass  # tap-only

    # --- OFF -------------------------------------------------------
    def press_off(self):
        asyncio.create_task(self._next_track())

    def release_off(self):
        pass  # tap-only

    # --- STOP ------------------------------------------------------
    def press_stop(self):
        """
        STOP:
        - execute middle_button actions if defined
        - else mute/unmute toggle
        """
        actions = self.ctrl.conf.middle_button

        if actions:
            for action in actions:
                asyncio.create_task(self.ctrl.utils.execute_button_action(action))
        else:
            asyncio.create_task(self._toggle_mute())

    def release_stop(self):
        pass

    # --- RAISE -----------------------------------------------------
    def press_raise(self):
        self._start_raise_lower("raise", direction=1)

    def release_raise(self):
        self._stop_raise_lower("raise")

    # --- LOWER -----------------------------------------------------
    def press_lower(self):
        self._start_raise_lower("lower", direction=-1)

    def release_lower(self):
        self._stop_raise_lower("lower")

    # ==============================================================
    # INTERNAL STATEFUL BEHAVIOR (RAISE / LOWER)
    # ==============================================================

    def _start_raise_lower(self, button: str, direction: int):
        self._pressed[button] = True
        self._press_ts[button] = time.time()

        # TAP → immediate step
        asyncio.create_task(self._step_volume(direction))

        # HOLD → ramp
        task = asyncio.create_task(self._hold_lifecycle(button, direction))
        self._tasks[button] = task

    def _stop_raise_lower(self, button: str):
        self._pressed[button] = False

        task = self._tasks.get(button)
        if task and not task.done():
            task.cancel()

        self._tasks[button] = None

    async def _hold_lifecycle(self, button: str, direction: int):
        try:
            await asyncio.sleep(self.ctrl.utils._hold_time)

            if not self._pressed.get(button):
                return  # TAP only

            while self._pressed.get(button):
                await self._step_volume(direction)
                await asyncio.sleep(self.ctrl.utils._step_time)

        except asyncio.CancelledError:
            pass

    # ==============================================================
    # DOMAIN LOGIC
    # ==============================================================

    async def _play_pause(self):
        await self.ctrl.utils.call_service(
            "media_play_pause",
            {},
            domain="media_player",
        )

    async def _next_track(self):
        await self.ctrl.utils.call_service(
            "media_next_track",
            {},
            domain="media_player",
        )

    async def _toggle_mute(self):
        state = self.ctrl.utils.get_entity_state()
        if not state:
            return

        is_muted = state.attributes.get("is_volume_muted")
        new_val = not bool(is_muted)

        await self.ctrl.utils.call_service(
            "volume_mute",
            {"is_volume_muted": new_val},
            domain="media_player",
        )

    async def _step_volume(self, direction: int):
        """
        Single volume step (tap or ramp tick).
        """

        step_pct = self.ctrl.conf.media_player_vol_step

        current = self._get_current_volume()
        if current is None:
            return

        current_pct = current * 100.0
        new_pct = max(0.0, min(100.0, current_pct + (step_pct * direction)))

        _LOGGER.debug(
            "MediaPlayerActions: step_volume direction=%s current=%s new=%s",
            direction,
            current_pct,
            new_pct,
        )

        await self.ctrl.utils.call_service(
            "volume_set",
            {"volume_level": new_pct / 100.0},
            domain="media_player",
        )

    # ==============================================================
    # HELPERS
    # ==============================================================

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

    # ==============================================================
    # RESET STATE
    # ==============================================================

    def reset_state(self):
        """Stop all tasks and clear pressed state."""

        for t in self._tasks.values():
            if t and not t.done():
                t.cancel()

        for key in self._pressed:
            self._pressed[key] = False
            self._tasks[key] = None

        self._press_ts.clear()
