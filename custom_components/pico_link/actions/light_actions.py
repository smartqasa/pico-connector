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
        - tap vs hold
        - stepping
        - ramping
        - on/off/low_pct behavior
        - HA service calls
        - profile-aware semantics (P2B vs 3BRL, etc.)
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl

        # Track which logical buttons are currently pressed.
        # We now also track ON / OFF to support tap-vs-hold
        # behavior for certain profiles (e.g. P2B).
        self._pressed: dict[str, bool] = {
            "raise": False,
            "lower": False,
            "on": False,
            "off": False,
        }

        # Track when each button was pressed (mainly for debugging / future use)
        self._press_ts: dict[str, float] = {}

        # Async tasks per button (hold lifecycle / ramp, etc.)
        self._tasks: dict[str, Optional[asyncio.Task]] = {
            "raise": None,
            "lower": None,
            "on": None,
            "off": None,
        }

        # Whether a button has transitioned to a "hold" state
        # (used primarily for ON/OFF tap-vs-hold).
        self._is_holding: dict[str, bool] = {
            "raise": False,
            "lower": False,
            "on": False,
            "off": False,
        }

    # ==============================================================
    # Profile-aware helpers
    # ==============================================================

    def _supports_onoff_hold(self) -> bool:
        """
        Return True if ON/OFF should have tap-vs-hold behavior for lights.

        For now, this is enabled for the P2B paddle profile only.
        Other profiles (e.g. 3BRL) treat ON/OFF as tap-only.
        """
        profile = self.ctrl.behavior_name
        return profile == "P2B"

    # ==============================================================
    # API METHODS (called by profiles)
    # ==============================================================

    # --- ON --------------------------------------------------------
    def press_on(self):
        """
        ON behavior:

        - P2B:
            * Tap  -> turn_on(light_on_pct)
            * Hold -> ramp brightness up until release
        - Other profiles (3BRL, 2B, 4B, etc.):
            * ON is simple turn_on (tap-only)
        """
        if self._supports_onoff_hold():
            self._start_onoff_hold(button="on", direction=1)
        else:
            asyncio.create_task(self._turn_on())

    def release_on(self):
        if self._supports_onoff_hold():
            self._finalize_onoff_hold(button="on", tap_action=self._turn_on)
        # For tap-only profiles, ON release is a no-op.

    # --- OFF -------------------------------------------------------
    def press_off(self):
        """
        OFF behavior:

        - P2B:
            * Tap  -> turn_off
            * Hold -> ramp brightness down until release
        - Other profiles:
            * OFF is simple turn_off (tap-only)
        """
        if self._supports_onoff_hold():
            self._start_onoff_hold(button="off", direction=-1)
        else:
            asyncio.create_task(self._turn_off())

    def release_off(self):
        if self._supports_onoff_hold():
            self._finalize_onoff_hold(button="off", tap_action=self._turn_off)
        # For tap-only profiles, OFF release is a no-op.

    # --- STOP ------------------------------------------------------
    def press_stop(self):
        """
        STOP = execute middle_button actions (Lutron-like)
        or no-op if none defined.
        """
        actions = self.ctrl.conf.middle_button

        if not actions:
            _LOGGER.debug("Light STOP pressed: no middle_button actions configured")
            return

        for action in actions:
            asyncio.create_task(self.ctrl.utils.execute_button_action(action))

    def release_stop(self):
        pass

    # --- RAISE -----------------------------------------------------
    def press_raise(self):
        """
        Used by profiles with dedicated raise/lower buttons (e.g. 3BRL).

        Behavior:
        - Press → single brightness step up
        - Hold  → continuous ramp up after hold_time
        """
        self._start_raise_lower("raise", direction=1)

    def release_raise(self):
        self._stop_raise_lower("raise")

    # --- LOWER -----------------------------------------------------
    def press_lower(self):
        """
        Used by profiles with dedicated raise/lower buttons (e.g. 3BRL).

        Behavior:
        - Press → single brightness step down
        - Hold  → continuous ramp down after hold_time
        """
        self._start_raise_lower("lower", direction=-1)

    def release_lower(self):
        self._stop_raise_lower("lower")

    # ==============================================================
    # INTERNAL STATEFUL BEHAVIOR (RAISE/LOWER)
    # ==============================================================

    def _start_raise_lower(self, button: str, direction: int):
        self._pressed[button] = True
        self._is_holding[button] = False
        self._press_ts[button] = time.time()

        # TAP step immediately
        asyncio.create_task(self._step_brightness(direction))

        # HOLD → ramp
        task = asyncio.create_task(self._hold_lifecycle(button, direction))
        self._tasks[button] = task

    def _stop_raise_lower(self, button: str):
        self._pressed[button] = False

        task = self._tasks.get(button)
        if task and not task.done():
            task.cancel()

        self._tasks[button] = None
        self._is_holding[button] = False

    # ==============================================================
    # INTERNAL STATEFUL BEHAVIOR (ON/OFF TAP vs HOLD for P2B)
    # ==============================================================

    def _start_onoff_hold(self, button: str, direction: int):
        """
        Common press handler for ON/OFF when tap-vs-hold is enabled (P2B).

        - If released before hold_time → TAP (simple on/off)
        - If still pressed after hold_time → HOLD (continuous ramp)
        """
        self._pressed[button] = True
        self._is_holding[button] = False
        self._press_ts[button] = time.time()

        task = asyncio.create_task(self._onoff_hold_lifecycle(button, direction))
        self._tasks[button] = task

    async def _onoff_hold_lifecycle(self, button: str, direction: int):
        try:
            await asyncio.sleep(self.ctrl.utils._hold_time)

            if not self._pressed.get(button):
                # Released before hold_time → treat as TAP in release_*.
                return

            # HOLD → continuous ramp
            self._is_holding[button] = True
            await self._ramp(button, direction)

        except asyncio.CancelledError:
            # Normal path when released before hold_time
            pass

    def _finalize_onoff_hold(self, button: str, tap_action):
        """
        Common release handler for ON/OFF when tap-vs-hold is enabled.

        - If no ramp ever started (_is_holding[button] is False):
            → this was a TAP → call tap_action (turn_on/turn_off)
        - If ramp started:
            → stop ramp, do NOT toggle again
        """
        self._pressed[button] = False

        task = self._tasks.get(button)
        if task and not task.done():
            task.cancel()

        if not self._is_holding.get(button, False):
            # TAP: we never entered holding state
            asyncio.create_task(tap_action())

        # Reset state
        self._tasks[button] = None
        self._is_holding[button] = False

    # ==============================================================
    # TAP / HOLD LIFECYCLE (RAISE/LOWER)
    # ==============================================================

    async def _hold_lifecycle(self, button: str, direction: int):
        try:
            await asyncio.sleep(self.ctrl.utils._hold_time)

            if not self._pressed.get(button):
                return  # TAP only

            # HOLD → continuous ramp
            self._is_holding[button] = True
            await self._ramp(button, direction)

        except asyncio.CancelledError:
            # Released before hold_time → no ramp
            pass

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
            except Exception:  # defensive
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

    async def _ramp(self, button: str, direction: int):
        """
        Continuous ramp:
        step by light_step_pct every step_time
        UNTIL:
        - button is released
        - OR max iterations (50) reached
        """

        step_time = self.ctrl.utils._step_time
        MAX_STEPS = 50     # Your chosen hard limit

        iterations = 0

        while self._pressed.get(button, False):
            if iterations >= MAX_STEPS:
                _LOGGER.warning(
                    "LightActions: ramp stopped after %s steps (safety limit) "
                    "for device %s button %s",
                    MAX_STEPS,
                    self.ctrl.conf.device_id,
                    button,
                )
                break

            await self._step_brightness(direction)
            iterations += 1
            await asyncio.sleep(step_time)
