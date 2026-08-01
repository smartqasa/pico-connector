# cover_actions.py
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..controller import PicoController


class CoverActions:
    """
    Cover behavior for all supported Pico profiles.

    P2B / 2B:
        ON tap   -> open to cover_open_pos
        ON hold  -> move continuously in the ON direction
        OFF tap  -> close fully
        OFF hold -> move continuously in the OFF direction
        ON/OFF while moving -> stop

        If cover_inverted is true, the ON and OFF directions are reversed.

    3BRL:
        ON tap      -> open to cover_open_pos
        OFF tap     -> close fully
        RAISE tap   -> step open
        RAISE hold  -> open continuously until release
        LOWER tap   -> step close
        LOWER hold  -> close continuously until release

    STOP:
        Configured middle_button actions override the default stop action.
    """

    TARGET_CACHE_SECONDS = 2.0

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl

        # Only one ON/OFF/RAISE/LOWER gesture may be active at a time.
        self._active_button: Optional[str] = None
        self._is_holding = False

        # Retain gesture tasks so releases and newer commands can cancel them.
        self._step_task: Optional[asyncio.Task[Any]] = None
        self._hold_task: Optional[asyncio.Task[Any]] = None

        # Invalidates delayed tasks belonging to older gestures.
        self._gesture_generation = 0

        # Retain the most recently requested position so rapid taps do
        # not depend on Home Assistant updating current_position first.
        self._target_position: Optional[int] = None
        self._target_updated_at = 0.0

    # =============================================================
    # PROFILE HELPERS
    # =============================================================

    def _supports_onoff_hold(self) -> bool:
        """Return True when ON/OFF must distinguish taps from holds."""
        return self.ctrl.conf.type in ("P2B", "2B")

    def _onoff_motion_direction(self, button: str) -> str:
        """Return the movement direction for an ON or OFF hold."""
        if button == "on":
            return "lower" if self.ctrl.conf.cover_inverted else "raise"

        return "raise" if self.ctrl.conf.cover_inverted else "lower"

    # =============================================================
    # POSITION STATE
    # =============================================================

    def _current_position(self) -> Optional[int]:
        """Return the current position of the primary cover."""
        state = self.ctrl.utils.get_entity_state()

        if not state:
            return None

        raw_position = state.attributes.get("current_position")

        if isinstance(raw_position, bool) or not isinstance(
            raw_position,
            (int, float, str),
        ):
            return None

        try:
            position = round(float(raw_position))
        except ValueError:
            return None

        return max(
            0,
            min(100, position),
        )

    def _set_position_target(self, position: int) -> None:
        """Store the most recently requested cover position."""
        self._target_position = max(
            0,
            min(100, position),
        )
        self._target_updated_at = time.monotonic()

    def _clear_position_target(self) -> None:
        """Discard the optimistic cover-position target."""
        self._target_position = None
        self._target_updated_at = 0.0

    def _position_for_step(self) -> Optional[int]:
        """
        Return the recent requested position or resynchronize from HA.

        A short cache allows rapid taps to build on the previous request
        without keeping an optimistic value authoritative indefinitely.
        """
        now = time.monotonic()

        if (
            self._target_position is not None
            and now - self._target_updated_at <= self.TARGET_CACHE_SECONDS
        ):
            return self._target_position

        position = self._current_position()

        if position is not None:
            self._set_position_target(position)

        return position

    def _next_position(self, button: str) -> Optional[int]:
        """Calculate and store the next requested step position."""
        position = self._position_for_step()

        if position is None:
            return None

        step = self.ctrl.conf.cover_step_pct

        if button == "raise":
            new_position = min(
                100,
                position + step,
            )
        else:
            new_position = max(
                0,
                position - step,
            )

        if new_position == position:
            return None

        # Store this target before task creation. Another rapid tap can
        # therefore build from this command even if HA still reports
        # the previous physical position.
        self._set_position_target(new_position)

        return new_position

    # =============================================================
    # GESTURE STATE
    # =============================================================

    def _is_moving(self) -> bool:
        """Return True when the primary cover is opening or closing."""
        state = self.ctrl.utils.get_entity_state()

        if not state:
            return False

        return state.state in (
            "opening",
            "closing",
        )

    def _clear_gesture_state(
        self,
        *,
        cancel_step: bool = True,
    ) -> bool:
        """
        Cancel gesture tasks and invalidate the current gesture.

        Returns True when continuous movement had already started.

        The position-step task is not canceled on a normal RAISE/LOWER
        release because a quick tap must still complete its command.
        """
        was_holding = self._is_holding

        self._gesture_generation += 1
        self._active_button = None
        self._is_holding = False

        if self._hold_task and not self._hold_task.done():
            self._hold_task.cancel()

        self._hold_task = None

        if cancel_step and self._step_task and not self._step_task.done():
            self._step_task.cancel()

        self._step_task = None

        return was_holding

    # =============================================================
    # ON / OFF TAP-HOLD GESTURES
    # =============================================================

    def _press_onoff(self, button: str) -> None:
        """Handle an ON or OFF press for every Pico profile."""
        was_holding = self._clear_gesture_state()

        # A new ON/OFF press while movement is active acts as STOP.
        if was_holding or self._is_moving():
            self._clear_position_target()

            self.ctrl.create_task(
                self._stop(),
                "cover-stop",
            )
            return

        if not self._supports_onoff_hold():
            self._start_onoff_tap(button)
            return

        self._active_button = button
        generation = self._gesture_generation

        # P2B/2B tap actions are deferred until release so the same
        # physical button can be interpreted as a hold.
        self._hold_task = self.ctrl.create_task(
            self._hold_lifecycle(
                button,
                generation,
            ),
            f"cover-{button}-hold",
        )

    def _release_onoff(self, button: str) -> None:
        """Complete a P2B/2B ON or OFF gesture."""
        if not self._supports_onoff_hold():
            return

        # Ignore a release belonging to an older gesture.
        if self._active_button != button:
            return

        was_holding = self._clear_gesture_state()

        if was_holding:
            self._clear_position_target()

            self.ctrl.create_task(
                self._stop(),
                "cover-stop",
            )
            return

        self._start_onoff_tap(button)

    def _start_onoff_tap(self, button: str) -> None:
        """Execute the configured tap action for ON or OFF."""
        should_open = button == "on"

        if self.ctrl.conf.cover_inverted:
            should_open = not should_open

        if should_open:
            open_position = self.ctrl.conf.cover_open_pos

            self._set_position_target(open_position)

            self.ctrl.create_task(
                self._open_to_position(),
                "cover-open",
            )
        else:
            self._set_position_target(0)

            self.ctrl.create_task(
                self._close_full(),
                "cover-close",
            )

    # =============================================================
    # RAISE / LOWER GESTURES
    # =============================================================

    def _start_raise_lower(self, button: str) -> None:
        """Perform one position step and arm continuous movement."""
        previous_was_holding = self._clear_gesture_state()

        self._active_button = button
        generation = self._gesture_generation

        if previous_was_holding:
            # Stop the previous continuous direction before stepping
            # in the newly requested direction.
            self._step_task = self.ctrl.create_task(
                self._stop_then_step(
                    button,
                    generation,
                ),
                f"cover-{button}-transition",
            )
        else:
            self._schedule_step(
                button,
                task_name=f"cover-{button}-step",
            )

        self._hold_task = self.ctrl.create_task(
            self._hold_lifecycle(
                button,
                generation,
            ),
            f"cover-{button}-hold",
        )

    def _release_raise_lower(self, button: str) -> None:
        """Complete the active RAISE or LOWER gesture."""
        # Ignore a release belonging to an older gesture.
        if self._active_button != button:
            return

        # Allow the immediate position step to finish on a quick tap.
        was_holding = self._clear_gesture_state(
            cancel_step=False,
        )

        if was_holding:
            self._clear_position_target()

            self.ctrl.create_task(
                self._stop(),
                "cover-stop",
            )

    def _schedule_step(
        self,
        button: str,
        *,
        task_name: str,
    ) -> None:
        """Calculate a step synchronously and schedule its service call."""
        new_position = self._next_position(button)

        if new_position is None:
            return

        self._step_task = self.ctrl.create_task(
            self._set_position(new_position),
            task_name,
        )

    # =============================================================
    # PROFILE ENTRY POINTS
    # =============================================================

    def press_on(self) -> None:
        self._press_onoff("on")

    def release_on(self) -> None:
        self._release_onoff("on")

    def press_off(self) -> None:
        self._press_onoff("off")

    def release_off(self) -> None:
        self._release_onoff("off")

    def press_stop(self) -> None:
        was_holding = self._clear_gesture_state()
        self._clear_position_target()

        actions = self.ctrl.conf.middle_button

        if actions:
            if was_holding:
                self.ctrl.create_task(
                    self._stop_then_execute(actions),
                    "cover-stop-and-middle-button",
                )
            else:
                self.ctrl.create_task(
                    self.ctrl.utils.execute_button_action(actions),
                    "cover-middle-button",
                )

            return

        self.ctrl.create_task(
            self._stop(),
            "cover-stop",
        )

    def release_stop(self) -> None:
        pass

    def press_raise(self) -> None:
        """Step open immediately and open continuously when held."""
        self._start_raise_lower("raise")

    def release_raise(self) -> None:
        self._release_raise_lower("raise")

    def press_lower(self) -> None:
        """Step closed immediately and close continuously when held."""
        self._start_raise_lower("lower")

    def release_lower(self) -> None:
        self._release_raise_lower("lower")

    # =============================================================
    # GESTURE LIFECYCLE
    # =============================================================

    async def _hold_lifecycle(
        self,
        button: str,
        generation: int,
    ) -> None:
        """Begin continuous movement after the hold threshold."""
        try:
            await asyncio.sleep(self.ctrl.utils._hold_time)

            if generation != self._gesture_generation or self._active_button != button:
                return

            # Continuous movement does not have a known target position.
            self._clear_position_target()
            self._is_holding = True

            direction = (
                self._onoff_motion_direction(button)
                if button in ("on", "off")
                else button
            )

            await self._start_motion(direction)

        except asyncio.CancelledError:
            # Expected when released before the hold threshold.
            pass

    async def _stop_then_step(
        self,
        button: str,
        generation: int,
    ) -> None:
        """Stop previous continuous movement before stepping."""
        await self._stop(blocking=True)

        if generation != self._gesture_generation or self._active_button != button:
            return

        # Continuous movement invalidates the previous optimistic target.
        self._clear_position_target()

        new_position = self._next_position(button)

        if new_position is not None:
            await self._set_position(new_position)

    async def _stop_then_execute(
        self,
        actions: Any,
    ) -> None:
        """Stop movement before running custom middle-button actions."""
        await self._stop(blocking=True)
        await self.ctrl.utils.execute_button_action(actions)

    # =============================================================
    # COVER OPERATIONS
    # =============================================================

    async def _open_to_position(self) -> None:
        """Open to the configured open position."""
        open_position = self.ctrl.conf.cover_open_pos

        if open_position == 100:
            await self.ctrl.utils.call_service(
                "open_cover",
                {},
                domain="cover",
            )
            return

        await self._set_position(open_position)

    async def _close_full(self) -> None:
        await self.ctrl.utils.call_service(
            "close_cover",
            {},
            domain="cover",
        )

    async def _stop(
        self,
        *,
        blocking: bool = False,
    ) -> None:
        await self.ctrl.utils.call_service(
            "stop_cover",
            {},
            domain="cover",
            blocking=blocking,
        )

    async def _start_motion(self, direction: str) -> None:
        service = "open_cover" if direction == "raise" else "close_cover"

        await self.ctrl.utils.call_service(
            service,
            {},
            domain="cover",
        )

    async def _set_position(
        self,
        position: int,
    ) -> None:
        """Set all configured covers to a specific position."""
        await self.ctrl.utils.call_service(
            "set_cover_position",
            {"position": position},
            domain="cover",
        )

    # =============================================================
    # LIFECYCLE
    # =============================================================

    def reset_state(self) -> None:
        """Cancel pending gesture tasks and clear all cover state."""
        self._clear_gesture_state()
        self._clear_position_target()
