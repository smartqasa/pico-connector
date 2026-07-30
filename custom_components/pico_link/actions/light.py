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
        # behavior for certain profiles (e.g. P2B, 2B).
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
        """
        return self.ctrl.conf.type in ("P2B", "2B")

    # ==============================================================
    # Motion abort helper
    # ==============================================================

    def _abort_motion(self) -> None:
        """
        Immediately stop any hold/ramp lifecycle (ON/OFF/RAISE/LOWER).

        Rule:
          - Any new press represents new intent and cancels any existing motion.
          - Any tap (release resulting in tap) also stops any motion before acting.
        """
        for btn in ("raise", "lower", "on", "off"):
            self._pressed[btn] = False
            self._is_holding[btn] = False

            task = self._tasks.get(btn)
            if task and not task.done():
                task.cancel()
            self._tasks[btn] = None

    # ==============================================================
    # Transition parameter helper
    # ==============================================================

    def _light_transition_param(self, *, turning_on: bool) -> dict:
        """
        Return a transition parameter dict for light service calls.

        If transition is 0, return {} so it is NOT passed to HA.
        """
        if turning_on:
            transition = self.ctrl.conf.light_transition_on
        else:
            transition = self.ctrl.conf.light_transition_off

        if transition > 0:
            return {"transition": transition}

        return {}

    # ==============================================================
    # API METHODS (called by profiles)
    # ==============================================================

    # --- ON --------------------------------------------------------
    def press_on(self):
        """
        ON behavior:

        - P2B / 2B:
            * Tap  -> turn_on(light_on_pct)
            * Hold -> ramp brightness up until release
        - Other profiles:
            * ON is simple turn_on (tap-only)
        """
        # Any press = new intent; stop any ongoing motion immediately
        self._abort_motion()

        if self._supports_onoff_hold():
            self._start_onoff_hold(button="on", direction=1)
        else:
            self.ctrl.create_task(
                self._turn_on(),
                "light-turn-on",
            )

    def release_on(self):
        if self._supports_onoff_hold():
            self._finalize_onoff_hold(button="on", tap_action=self._turn_on)
        # For tap-only profiles, ON release is a no-op.

    # --- OFF -------------------------------------------------------
    def press_off(self):
        """
        OFF behavior:

        - P2B / 2B:
            * Tap  -> turn_off
            * Hold -> ramp brightness down until release
        - Other profiles:
            * OFF is simple turn_off (tap-only)
        """
        # Any press = new intent; stop any ongoing motion immediately
        self._abort_motion()

        if self._supports_onoff_hold():
            self._start_onoff_hold(button="off", direction=-1)
        else:
            self.ctrl.create_task(
                self._turn_off(),
                "light-turn-off",
            )

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

        self.ctrl.create_task(
            self.ctrl.utils.execute_button_action(actions),
            "light-middle-button",
        )

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
        # Any press = new intent; stop any ongoing motion immediately
        self._abort_motion()
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
        # Any press = new intent; stop any ongoing motion immediately
        self._abort_motion()
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

        self.ctrl.create_task(
            self._step_brightness(direction),
            f"light-{button}-step",
        )

        task = self.ctrl.create_task(
            self._hold_lifecycle(button, direction),
            f"light-{button}-hold",
        )
        self._tasks[button] = task

    def _stop_raise_lower(self, button: str):
        self._pressed[button] = False

        task = self._tasks.get(button)
        if task and not task.done():
            task.cancel()

        self._tasks[button] = None
        self._is_holding[button] = False

    # ==============================================================
    # INTERNAL STATEFUL BEHAVIOR (ON/OFF TAP vs HOLD for P2B/2B)
    # ==============================================================

    def _start_onoff_hold(self, button: str, direction: int):
        """
        Common press handler for ON/OFF when tap-vs-hold is enabled.

        - If released before hold_time → TAP (simple on/off)
        - If still pressed after hold_time → HOLD (continuous ramp)
        """
        self._pressed[button] = True
        self._is_holding[button] = False
        self._press_ts[button] = time.time()

        task = self.ctrl.create_task(
            self._onoff_hold_lifecycle(button, direction),
            f"light-{button}-hold",
        )
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
            → this was a TAP → stop any motion then call tap_action
        - If ramp started:
            → stop ramp, do NOT toggle again
        """
        self._pressed[button] = False

        task = self._tasks.get(button)
        if task and not task.done():
            task.cancel()

        if not self._is_holding.get(button, False):
            # TAP: authoritative stop gesture
            self._abort_motion()
            self.ctrl.create_task(
                tap_action(),
                f"light-{button}-tap",
            )

        # Reset state for this button
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

        params = {
            "brightness_pct": pct,
            **self._light_transition_param(turning_on=True),
        }

        await self.ctrl.utils.call_service(
            "turn_on",
            params,
            domain="light",
        )

    async def _turn_off(self):
        params = {
            **self._light_transition_param(turning_on=False),
        }

        await self.ctrl.utils.call_service(
            "turn_off",
            params,
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

        _LOGGER.debug(
            "LightActions: step_brightness direction=%s current=%s new=%s",
            direction,
            current_pct,
            new_pct,
        )

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
        MAX_STEPS = 50

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

    # ==============================================================
    # RESET STATE (required by controller to avoid runaway loops)
    # ==============================================================

    def reset_state(self):
        """Stop all tasks and clear pressed/hold/ramp state."""
        # Cancel running tasks
        for t in self._tasks.values():
            if t and not t.done():
                t.cancel()

        # Reset tracking
        for key in self._pressed:
            self._pressed[key] = False
            self._is_holding[key] = False
            self._tasks[key] = None

        # Clear press timestamps
        self._press_ts.clear()
