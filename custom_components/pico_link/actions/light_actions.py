from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)


class LightActions:
    """
    Unified light action module implementing the full action API.

    Profiles:
      - only route press/release events
      - do NOT contain light logic

    LightActions:
      - tap vs hold (profile-aware)
      - stepping
      - ramping
      - on/off/low_pct behavior
      - HA service calls

    Behavior summary (lights):

      3BRL:
        - ON    → tap only (turn_on)
        - OFF   → tap only (turn_off)
        - RAISE → tap step up, hold = ramp up
        - LOWER → tap step down, hold = ramp down
        - STOP  → middle_button actions (if configured)

      P2B:
        - ON    → tap turn_on, hold = ramp up
        - OFF   → tap turn_off, hold = ramp down
        - (no dedicated raise/lower physically, but supported if present)

      2B:
        - ON/OFF tap only

      4B:
        - does not use LightActions (scenes only)
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl

        # ---------------------------
        # RAISE/LOWER state
        # ---------------------------
        self._pressed_rl: dict[str, bool] = {
            "raise": False,
            "lower": False,
        }
        self._press_ts_rl: dict[str, float] = {
            "raise": 0.0,
            "lower": 0.0,
        }
        self._tasks_rl: dict[str, Optional[asyncio.Task]] = {
            "raise": None,
            "lower": None,
        }
        self._is_holding_rl: dict[str, bool] = {
            "raise": False,
            "lower": False,
        }

        # ---------------------------
        # ON/OFF state (for P2B hold)
        # ---------------------------
        self._pressed_onoff: dict[str, bool] = {
            "on": False,
            "off": False,
        }
        self._press_ts_onoff: dict[str, float] = {
            "on": 0.0,
            "off": 0.0,
        }
        self._tasks_onoff: dict[str, Optional[asyncio.Task]] = {
            "on": None,
            "off": None,
        }
        self._is_holding_onoff: dict[str, bool] = {
            "on": False,
            "off": False,
        }

    # ==============================================================
    # Profile-aware helpers
    # ==============================================================

    def _supports_onoff_hold(self) -> bool:
        """
        Only the P2B paddle uses tap-vs-hold ON/OFF for lights.

        All other profiles (3BRL, 2B, etc.) treat ON/OFF as tap-only.
        """
        return self.ctrl.behavior_name == "P2B"

    # ==============================================================
    # API METHODS (called by profiles)
    # ==============================================================

    # --- ON --------------------------------------------------------
    def press_on(self):
        """
        ON behavior:

          - P2B:
              * Tap  → turn_on(light_on_pct)
              * Hold → ramp brightness up until release

          - Other profiles:
              * ON is simple turn_on (tap-only)
        """
        if self._supports_onoff_hold():
            self._start_onoff_hold(button="on", direction=1)
        else:
            asyncio.create_task(self._turn_on())

    def release_on(self):
        if self._supports_onoff_hold():
            self._finalize_onoff_hold(button="on", tap_coro=self._turn_on)
        # Tap-only profiles do nothing on release.

    # --- OFF -------------------------------------------------------
    def press_off(self):
        """
        OFF behavior:

          - P2B:
              * Tap  → turn_off
              * Hold → ramp brightness down until release

          - Other profiles:
              * OFF is simple turn_off (tap-only)
        """
        if self._supports_onoff_hold():
            self._start_onoff_hold(button="off", direction=-1)
        else:
            asyncio.create_task(self._turn_off())

    def release_off(self):
        if self._supports_onoff_hold():
            self._finalize_onoff_hold(button="off", tap_coro=self._turn_off)
        # Tap-only profiles do nothing on release.

    # --- STOP ------------------------------------------------------
    def press_stop(self):
        """
        STOP = execute middle_button actions (3BRL-style) or no-op.
        """
        actions = self.ctrl.conf.middle_button

        if not actions:
            _LOGGER.debug("Light STOP pressed: no middle_button actions configured")
            return

        for action in actions:
            asyncio.create_task(self.ctrl.utils.execute_button_action(action))

    def release_stop(self):
        # No-op for now
        pass

    # --- RAISE -----------------------------------------------------
    def press_raise(self):
        """
        Used by profiles with dedicated raise/lower buttons (e.g. 3BRL).

        Behavior:
          - Tap  → single brightness step up
          - Hold → continuous ramp up after hold_time
        """
        self._start_raise_lower("raise", direction=1)

    def release_raise(self):
        self._stop_raise_lower("raise")

    # --- LOWER -----------------------------------------------------
    def press_lower(self):
        """
        Used by profiles with dedicated raise/lower buttons (e.g. 3BRL).

        Behavior:
          - Tap  → single brightness step down
          - Hold → continuous ramp down after hold_time
        """
        self._start_raise_lower("lower", direction=-1)

    def release_lower(self):
        self._stop_raise_lower("lower")

    # ==============================================================
    # INTERNAL STATEFUL BEHAVIOR — RAISE / LOWER
    # ==============================================================

    def _start_raise_lower(self, button: str, direction: int):
        if button not in ("raise", "lower"):
            return

        self._pressed_rl[button] = True
        self._is_holding_rl[button] = False
        self._press_ts_rl[button] = time.time()

        # TAP: perform one step immediately
        asyncio.create_task(self._step_brightness(direction))

        # HOLD: schedule lifecycle that may transition into ramping
        task = asyncio.create_task(self._hold_lifecycle_rl(button, direction))
        self._tasks_rl[button] = task

    def _stop_raise_lower(self, button: str):
        if button not in ("raise", "lower"):
            return

        self._pressed_rl[button] = False

        task = self._tasks_rl.get(button)
        if task and not task.done():
            task.cancel()

        self._tasks_rl[button] = None
        self._is_holding_rl[button] = False

    async def _hold_lifecycle_rl(self, button: str, direction: int):
        """
        Tap vs hold for RAISE/LOWER:

          - Wait hold_time
          - If button was released → TAP only (we already stepped once)
          - If still pressed      → enter continuous ramp
        """
        try:
            await asyncio.sleep(self.ctrl.utils._hold_time)

            if not self._pressed_rl.get(button, False):
                # Released before hold_time → no ramp
                return

            # HOLD → continuous ramp
            self._is_holding_rl[button] = True
            await self._ramp_rl(button, direction)

        except asyncio.CancelledError:
            # Normal when released before hold_time
            pass

    # ==============================================================
    # INTERNAL STATEFUL BEHAVIOR — ON/OFF TAP vs HOLD (P2B)
    # ==============================================================

    def _start_onoff_hold(self, button: str, direction: int):
        """
        Used only for P2B:

          - If released before hold_time → TAP (turn_on / turn_off)
          - If still pressed after       → HOLD (continuous ramp up/down)
        """
        if button not in ("on", "off"):
            return

        self._pressed_onoff[button] = True
        self._is_holding_onoff[button] = False
        self._press_ts_onoff[button] = time.time()

        task = asyncio.create_task(self._onoff_hold_lifecycle(button, direction))
        self._tasks_onoff[button] = task

    async def _onoff_hold_lifecycle(self, button: str, direction: int):
        try:
            await asyncio.sleep(self.ctrl.utils._hold_time)

            if not self._pressed_onoff.get(button, False):
                # Released before hold_time → TAP handled in release method
                return

            # HOLD → continuous ramp
            self._is_holding_onoff[button] = True
            await self._ramp_onoff(button, direction)

        except asyncio.CancelledError:
            # Released before hold_time, or explicitly cancelled
            pass

    def _finalize_onoff_hold(self, button: str, tap_coro):
        """
        Common release handler for P2B ON/OFF:

          - If we never started HOLD → TAP → run tap_coro (turn_on/off)
          - If HOLD started          → just stop ramp (no extra toggle)
        """
        if button not in ("on", "off"):
            return

        self._pressed_onoff[button] = False

        task = self._tasks_onoff.get(button)
        if task and not task.done():
            task.cancel()

        if not self._is_holding_onoff.get(button, False):
            # TAP → run the corresponding coroutine
            asyncio.create_task(tap_coro())

        # Reset
        self._tasks_onoff[button] = None
        self._is_holding_onoff[button] = False

    # ==============================================================
    # DOMAIN LOGIC
    # ==============================================================

    async def _turn_on(self):
        pct = self.ctrl.conf.light_on_pct

        await self.ctrl.utils.call_service(
            "turn_on",
            {"brightness_pct": pct},
            domain="light",
        )

    async def _turn_off(self):
        await self.ctrl.utils.call_service(
            "turn_off",
            {},
            domain="light",
        )

    async def _step_brightness(self, direction: int):
        """
        TAP = single step brightness change.
        """

        step_pct = self.ctrl.conf.light_step_pct
        low_pct = self.ctrl.conf.light_low_pct

        state = self.ctrl.utils.get_entity_state()
        if not state:
            return

        raw_brightness = state.attributes.get("brightness")
        if raw_brightness is None:
            current_pct = 0
        else:
            try:
                current_pct = round((int(raw_brightness) / 255) * 100)
            except Exception:
                current_pct = 0

        new_pct = current_pct + (step_pct * direction)

        # Clamp
        if direction < 0:
            new_pct = max(low_pct, new_pct)
        new_pct = min(100, max(1, new_pct))

        await self.ctrl.utils.call_service(
            "turn_on",
            {"brightness_pct": new_pct},
            domain="light",
        )

    # ==============================================================
    # RAMP LOGIC (continuous)
    # ==============================================================

    async def _ramp_rl(self, button: str, direction: int):
        """
        Continuous ramp for RAISE/LOWER:
          step by light_step_pct every step_time,
          while the given button remains pressed.
        """
        step_time = self.ctrl.utils._step_time

        while self._pressed_rl.get(button, False):
            await self._step_brightness(direction)
            await asyncio.sleep(step_time)

    async def _ramp_onoff(self, button: str, direction: int):
        """
        Continuous ramp for ON/OFF on P2B:
          step by light_step_pct every step_time,
          while ON or OFF is held.
        """
        step_time = self.ctrl.utils._step_time

        while self._pressed_onoff.get(button, False):
            await self._step_brightness(direction)
            await asyncio.sleep(step_time)
