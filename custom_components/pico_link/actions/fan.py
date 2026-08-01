# fan_actions.py
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)

TapAction = Callable[[], Coroutine[Any, Any, None]]


class FanActions:
    """
    Fan behavior for all supported Pico profiles.

    P2B / 2B:
        ON tap   -> set fan_on_pct
        ON hold  -> repeatedly step speed upward
        OFF tap  -> turn off
        OFF hold -> repeatedly step speed downward

    3BRL:
        ON tap      -> set fan_on_pct
        OFF tap     -> turn off
        RAISE tap   -> one speed step up
        RAISE hold  -> repeatedly step speed upward
        LOWER tap   -> one speed step down
        LOWER hold  -> repeatedly step speed downward
        STOP tap    -> reverse direction or run middle_button actions
    """

    MAX_RAMP_STEPS = 50

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl

        # Only one ON/OFF/RAISE/LOWER gesture may be active at a time.
        self._active_button: Optional[str] = None
        self._is_holding = False
        self._gesture_generation = 0

        # Track the most recently requested speed so ramps do not depend
        # on immediate Home Assistant entity-state updates.
        self._target_percentage: Optional[int] = None
        self._speed_ladder: list[int] = []

        self._step_task: Optional[asyncio.Task[Any]] = None
        self._hold_task: Optional[asyncio.Task[Any]] = None

    # =============================================================
    # PROFILE HELPERS
    # =============================================================

    def _supports_onoff_hold(self) -> bool:
        """Return True when ON/OFF must distinguish taps from holds."""
        return self.ctrl.conf.type in ("P2B", "2B")

    # =============================================================
    # GESTURE STATE
    # =============================================================

    def _clear_speed_gesture(
        self,
        *,
        cancel_step: bool = True,
    ) -> bool:
        """
        Cancel the current speed gesture.

        Returns True when the hold threshold had already elapsed.
        """
        was_holding = self._is_holding

        self._gesture_generation += 1
        self._active_button = None
        self._is_holding = False
        self._target_percentage = None
        self._speed_ladder = []

        if self._hold_task and not self._hold_task.done():
            self._hold_task.cancel()

        self._hold_task = None

        if cancel_step and self._step_task and not self._step_task.done():
            self._step_task.cancel()

        self._step_task = None

        return was_holding

    def _start_speed_gesture(
        self,
        button: str,
        direction: int,
        *,
        immediate_step: bool,
    ) -> None:
        """Start a tap/hold speed gesture."""
        current = self._target_percentage

        if current is None:
            current = self._get_current_percentage()

        ladder = self._get_speed_ladder()

        self._clear_speed_gesture()

        self._active_button = button
        self._target_percentage = current
        self._speed_ladder = ladder
        generation = self._gesture_generation

        if immediate_step and current is not None and ladder:
            new_percentage = self._calculate_next_percentage(
                current,
                direction,
                ladder,
            )

            if new_percentage != current:
                self._target_percentage = new_percentage
                self._step_task = self.ctrl.create_task(
                    self._set_percentage(new_percentage),
                    f"fan-{button}-step",
                )

        self._hold_task = self.ctrl.create_task(
            self._hold_lifecycle(
                button,
                direction,
                generation,
            ),
            f"fan-{button}-hold",
        )

    def _release_speed_gesture(
        self,
        button: str,
        *,
        tap_action: Optional[TapAction] = None,
    ) -> None:
        """Finish an ON/OFF/RAISE/LOWER gesture."""
        if self._active_button != button:
            return

        was_holding = self._is_holding

        # Allow an immediate RAISE/LOWER step to finish on a quick tap.
        self._clear_speed_gesture(cancel_step=False)

        if tap_action is not None and not was_holding:
            self.ctrl.create_task(
                tap_action(),
                f"fan-{button}-tap",
            )

    def _gesture_is_current(
        self,
        button: str,
        generation: int,
    ) -> bool:
        return generation == self._gesture_generation and self._active_button == button

    # =============================================================
    # PROFILE ENTRY POINTS
    # =============================================================

    def press_on(self) -> None:
        if self._supports_onoff_hold():
            self._start_speed_gesture(
                "on",
                direction=1,
                immediate_step=False,
            )
            return

        self._clear_speed_gesture()

        self.ctrl.create_task(
            self._turn_on(),
            "fan-turn-on",
        )

    def release_on(self) -> None:
        if self._supports_onoff_hold():
            self._release_speed_gesture(
                "on",
                tap_action=self._turn_on,
            )

    def press_off(self) -> None:
        if self._supports_onoff_hold():
            self._start_speed_gesture(
                "off",
                direction=-1,
                immediate_step=False,
            )
            return

        self._clear_speed_gesture()

        self.ctrl.create_task(
            self._turn_off(),
            "fan-turn-off",
        )

    def release_off(self) -> None:
        if self._supports_onoff_hold():
            self._release_speed_gesture(
                "off",
                tap_action=self._turn_off,
            )

    def press_stop(self) -> None:
        self._clear_speed_gesture()
        actions = self.ctrl.conf.middle_button

        if actions:
            self.ctrl.create_task(
                self.ctrl.utils.execute_button_action(actions),
                "fan-middle-button",
            )
            return

        self.ctrl.create_task(
            self._reverse_direction(),
            "fan-reverse-direction",
        )

    def release_stop(self) -> None:
        pass

    def press_raise(self) -> None:
        self._start_speed_gesture(
            "raise",
            direction=1,
            immediate_step=True,
        )

    def release_raise(self) -> None:
        self._release_speed_gesture("raise")

    def press_lower(self) -> None:
        self._start_speed_gesture(
            "lower",
            direction=-1,
            immediate_step=True,
        )

    def release_lower(self) -> None:
        self._release_speed_gesture("lower")

    # =============================================================
    # HOLD / RAMP LIFECYCLE
    # =============================================================

    async def _hold_lifecycle(
        self,
        button: str,
        direction: int,
        generation: int,
    ) -> None:
        """Repeatedly step fan speed after the hold threshold."""
        try:
            await asyncio.sleep(self.ctrl.utils._hold_time)

            if not self._gesture_is_current(button, generation):
                return

            # Crossing the threshold makes ON/OFF a hold even when the
            # fan has no usable percentage state.
            self._is_holding = True

            for _ in range(self.MAX_RAMP_STEPS):
                if not self._gesture_is_current(button, generation):
                    return

                current = self._target_percentage
                ladder = self._speed_ladder

                if current is None or not ladder:
                    return

                new_percentage = self._calculate_next_percentage(
                    current,
                    direction,
                    ladder,
                )

                if new_percentage == current:
                    return

                self._target_percentage = new_percentage

                await self._set_percentage(new_percentage)

                if not self._gesture_is_current(button, generation):
                    return

                await asyncio.sleep(self.ctrl.utils._step_time)

            if self._gesture_is_current(button, generation):
                _LOGGER.warning(
                    "FanActions: speed ramp stopped after %s steps "
                    "for device %s button %s",
                    self.MAX_RAMP_STEPS,
                    self.ctrl.conf.device_id,
                    button,
                )

        except asyncio.CancelledError:
            # Expected when the button is released or superseded.
            pass

    # =============================================================
    # FAN OPERATIONS
    # =============================================================

    async def _turn_on(self) -> None:
        await self._set_percentage(self.ctrl.conf.fan_on_pct)

    async def _turn_off(self) -> None:
        await self.ctrl.utils.call_service(
            "turn_off",
            {},
            domain="fan",
        )

    async def _reverse_direction(self) -> None:
        state = self.ctrl.utils.get_entity_state()

        if not state:
            return

        current_direction = state.attributes.get("direction")

        if current_direction not in ("forward", "reverse"):
            return

        new_direction = "reverse" if current_direction == "forward" else "forward"

        await self.ctrl.utils.call_service(
            "set_direction",
            {"direction": new_direction},
            domain="fan",
        )

    async def _set_percentage(self, percentage: int) -> None:
        await self.ctrl.utils.call_service(
            "set_percentage",
            {"percentage": percentage},
            domain="fan",
        )

    # =============================================================
    # SPEED HELPERS
    # =============================================================

    def _get_speed_ladder(self) -> list[int]:
        """Build a speed ladder from the fan's percentage_step."""
        state = self.ctrl.utils.get_entity_state()

        if not state:
            return []

        raw_step = state.attributes.get("percentage_step")

        if (
            isinstance(raw_step, bool)
            or not isinstance(raw_step, (int, float))
            or raw_step <= 0
        ):
            return [0, 100]

        ladder = [0]
        percentage = float(raw_step)

        while percentage < 100:
            value = max(1, min(99, round(percentage)))

            if value != ladder[-1]:
                ladder.append(value)

            percentage += float(raw_step)

        if ladder[-1] != 100:
            ladder.append(100)

        return ladder

    def _get_current_percentage(self) -> Optional[int]:
        """Return the current fan percentage, treating OFF as zero."""
        state = self.ctrl.utils.get_entity_state()

        if not state:
            return None

        if state.state == "off":
            return 0

        raw_percentage = state.attributes.get("percentage")

        if raw_percentage is None:
            return 0

        if isinstance(raw_percentage, bool) or not isinstance(
            raw_percentage,
            (int, float, str),
        ):
            return 0

        try:
            percentage = round(float(raw_percentage))
        except ValueError:
            return 0

        return max(0, min(100, percentage))

    @staticmethod
    def _calculate_next_percentage(
        current: int,
        direction: int,
        ladder: list[int],
    ) -> int:
        """Return the next percentage in the selected direction."""
        current_index = min(
            range(len(ladder)),
            key=lambda index: abs(ladder[index] - current),
        )

        next_index = max(
            0,
            min(len(ladder) - 1, current_index + direction),
        )

        return ladder[next_index]

    # =============================================================
    # LIFECYCLE
    # =============================================================

    def reset_state(self) -> None:
        """Cancel all speed tasks and clear gesture state."""
        self._clear_speed_gesture()
