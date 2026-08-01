# cover_actions.py
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..controller import PicoController


class CoverActions:
    """
    Unified cover behavior for all supported Pico profiles.

    P2B / 2B:
        ON tap  → open to cover_open_pos
        OFF tap → close fully
        ON/OFF tap while moving → stop

        If cover_inverted is true:
            ON tap  → close fully
            OFF tap → open to cover_open_pos

    3BRL:
        ON tap      → open to cover_open_pos
        OFF tap     → close fully
        RAISE tap   → step open
        RAISE hold  → open continuously until release
        LOWER tap   → step close
        LOWER hold  → close continuously until release

    STOP:
        Configured middle_button actions override the default stop action.
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl

        # Only one raise/lower gesture may be active at a time.
        self._active_button: Optional[str] = None

        # True after the hold threshold has elapsed and continuous
        # open/close movement has started.
        self._is_holding = False

        # Retain the position-step task so a newer command can cancel
        # a step that has not yet been submitted to Home Assistant.
        self._step_task: Optional[asyncio.Task] = None

        # Retain the delayed hold task so release or a newer command
        # can cancel it before continuous movement starts.
        self._hold_task: Optional[asyncio.Task] = None

        # Each new gesture receives a generation number. Delayed tasks
        # must still match the current generation before they may act.
        self._gesture_generation = 0

    # =============================================================
    # STATE HELPERS
    # =============================================================

    def _is_moving(self) -> bool:
        """Return True when the primary cover is opening or closing."""
        state = self.ctrl.utils.get_entity_state()

        if not state:
            return False

        return state.state in ("opening", "closing")

    def _current_position(self) -> Optional[int]:
        """Return the current position of the primary cover."""
        state = self.ctrl.utils.get_entity_state()

        if not state:
            return None

        position = state.attributes.get("current_position")

        if isinstance(position, bool) or not isinstance(position, (int, float, str)):
            return None

        try:
            return round(float(position))
        except ValueError:
            return None

    def _clear_gesture_state(
        self,
        *,
        cancel_step: bool = True,
    ) -> bool:
        """
        Cancel gesture tasks and invalidate the current gesture.

        Returns True when continuous movement had already started.

        The position-step task is not canceled on a normal release because
        a quick tap must still complete its set_cover_position call.
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

    def _start_raise_lower(self, button: str) -> None:
        """Perform one position step and arm continuous movement."""
        previous_was_holding = self._clear_gesture_state()

        self._active_button = button
        generation = self._gesture_generation

        if previous_was_holding:
            # Stop the previous continuous direction before issuing the
            # position step for the new direction.
            self._step_task = self.ctrl.create_task(
                self._stop_then_step(button, generation),
                f"cover-{button}-transition",
            )
        else:
            self._step_task = self.ctrl.create_task(
                self._step(button),
                f"cover-{button}-step",
            )

        self._hold_task = self.ctrl.create_task(
            self._hold_lifecycle(button, generation),
            f"cover-{button}-hold",
        )

    def _release_raise_lower(self, button: str) -> None:
        """Complete the active raise/lower gesture."""
        # Ignore a release belonging to a superseded direction.
        if self._active_button != button:
            return

        # Do not cancel the position step on a normal tap release.
        was_holding = self._clear_gesture_state(cancel_step=False)

        # A tap used set_cover_position and must be allowed to finish.
        # Only continuous open_cover/close_cover movement needs stopping.
        if was_holding:
            self.ctrl.create_task(
                self._stop(),
                "cover-stop",
            )

    # =============================================================
    # PROFILE ENTRY POINTS
    # =============================================================

    # -------------------------------------------------------------
    # ON
    # -------------------------------------------------------------

    def press_on(self) -> None:
        was_holding = self._clear_gesture_state()

        # ON during a Pico hold or while the cover reports movement
        # acts as a stop command.
        if was_holding or self._is_moving():
            self.ctrl.create_task(
                self._stop(),
                "cover-stop",
            )
            return

        if self.ctrl.conf.cover_inverted:
            self.ctrl.create_task(
                self._close_full(),
                "cover-close",
            )
            return

        self.ctrl.create_task(
            self._open_to_position(),
            "cover-open",
        )

    def release_on(self) -> None:
        pass

    # -------------------------------------------------------------
    # OFF
    # -------------------------------------------------------------

    def press_off(self) -> None:
        was_holding = self._clear_gesture_state()

        # OFF during a Pico hold or while the cover reports movement
        # acts as a stop command.
        if was_holding or self._is_moving():
            self.ctrl.create_task(
                self._stop(),
                "cover-stop",
            )
            return

        if self.ctrl.conf.cover_inverted:
            self.ctrl.create_task(
                self._open_to_position(),
                "cover-open",
            )
            return

        self.ctrl.create_task(
            self._close_full(),
            "cover-close",
        )

    def release_off(self) -> None:
        pass

    # -------------------------------------------------------------
    # STOP
    # -------------------------------------------------------------

    def press_stop(self) -> None:
        was_holding = self._clear_gesture_state()
        actions = self.ctrl.conf.middle_button

        if actions:
            if was_holding:
                # Stop Pico-initiated continuous cover movement before
                # executing the configured middle-button actions.
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

    # -------------------------------------------------------------
    # RAISE
    # -------------------------------------------------------------

    def press_raise(self) -> None:
        """Step open immediately and open continuously when held."""
        self._start_raise_lower("raise")

    def release_raise(self) -> None:
        self._release_raise_lower("raise")

    # -------------------------------------------------------------
    # LOWER
    # -------------------------------------------------------------

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

            # The task may belong to an earlier press that was released
            # or superseded by a newer gesture.
            if generation != self._gesture_generation or self._active_button != button:
                return

            self._is_holding = True
            await self._start_motion(button)

        except asyncio.CancelledError:
            # Expected when released before the hold threshold.
            pass

    async def _stop_then_step(
        self,
        button: str,
        generation: int,
    ) -> None:
        """Stop previous continuous movement before stepping."""
        await self._stop()

        # Do not execute the step if another gesture has superseded this one.
        if generation != self._gesture_generation or self._active_button != button:
            return

        await self._step(button)

    async def _stop_then_execute(
        self,
        actions: Any,
    ) -> None:
        """Stop Pico-initiated movement before running custom actions."""
        await self._stop()
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

        await self.ctrl.utils.call_service(
            "set_cover_position",
            {"position": open_position},
            domain="cover",
        )

    async def _close_full(self) -> None:
        await self.ctrl.utils.call_service(
            "close_cover",
            {},
            domain="cover",
        )

    async def _stop(self) -> None:
        await self.ctrl.utils.call_service(
            "stop_cover",
            {},
            domain="cover",
        )

    async def _start_motion(self, direction: str) -> None:
        service = "open_cover" if direction == "raise" else "close_cover"

        await self.ctrl.utils.call_service(
            service,
            {},
            domain="cover",
        )

    async def _step(self, button: str) -> None:
        """Move the cover by one configured position step."""
        position = self._current_position()

        if position is None:
            return

        step = self.ctrl.conf.cover_step_pct

        if button == "raise":
            new_position = min(100, position + step)
        else:
            new_position = max(0, position - step)

        # Avoid sending an unnecessary command at either endpoint.
        if new_position == position:
            return

        await self.ctrl.utils.call_service(
            "set_cover_position",
            {"position": new_position},
            domain="cover",
        )

    # =============================================================
    # LIFECYCLE
    # =============================================================

    def reset_state(self) -> None:
        """Cancel pending gesture tasks and clear all gesture state."""
        self._clear_gesture_state()
