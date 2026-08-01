# fan_actions.py
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..controller import PicoController


class FanActions:
    """
    Tap-only fan controller for all supported Pico profiles.

    Behaviors:
        ON tap     -> turn on to fan_on_pct
        OFF tap    -> turn off
        RAISE tap  -> move to the next higher speed
        LOWER tap  -> move to the next lower speed
        STOP tap   -> reverse direction or execute middle_button actions

    If the fan is off, RAISE moves it to the first available speed.
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl

    # =============================================================
    # PROFILE ENTRY POINTS
    # =============================================================

    def press_on(self) -> None:
        self.ctrl.create_task(
            self._turn_on(),
            "fan-turn-on",
        )

    def release_on(self) -> None:
        pass

    def press_off(self) -> None:
        self.ctrl.create_task(
            self._turn_off(),
            "fan-turn-off",
        )

    def release_off(self) -> None:
        pass

    def press_stop(self) -> None:
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
        self.ctrl.create_task(
            self._step(1),
            "fan-step-up",
        )

    def release_raise(self) -> None:
        pass

    def press_lower(self) -> None:
        self.ctrl.create_task(
            self._step(-1),
            "fan-step-down",
        )

    def release_lower(self) -> None:
        pass

    # =============================================================
    # FAN OPERATIONS
    # =============================================================

    async def _turn_on(self) -> None:
        await self.ctrl.utils.call_service(
            "set_percentage",
            {"percentage": self.ctrl.conf.fan_on_pct},
            domain="fan",
        )

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

    # =============================================================
    # DISCRETE SPEED STEPPING
    # =============================================================

    async def _step(self, direction: int) -> None:
        """
        Move the fan one step up or down its discrete speed ladder.

        If the fan is off, stepping upward selects the first nonzero
        speed.
        """
        speed_ladder = self._get_speed_ladder()

        if not speed_ladder:
            return

        current_percentage = self._get_current_percentage()

        if current_percentage is None:
            return

        if current_percentage == 0 and direction > 0:
            # The ladder always contains at least [0, 100].
            new_percentage = speed_ladder[1]
        else:
            current_index = min(
                range(len(speed_ladder)),
                key=lambda index: abs(speed_ladder[index] - current_percentage),
            )

            new_index = max(
                0,
                min(
                    len(speed_ladder) - 1,
                    current_index + direction,
                ),
            )

            new_percentage = speed_ladder[new_index]

        # Avoid redundant calls at the top or bottom of the ladder.
        if new_percentage == current_percentage:
            return

        await self.ctrl.utils.call_service(
            "set_percentage",
            {"percentage": new_percentage},
            domain="fan",
        )

    # =============================================================
    # SPEED HELPERS
    # =============================================================

    def _get_speed_ladder(self) -> list[int]:
        """
        Build a discrete speed ladder from percentage_step.

        Examples:
            percentage_step=25 -> [0, 25, 50, 75, 100]
            percentage_step=33 -> [0, 33, 66, 99, 100]
        """
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

        speed_ladder = [0]
        percentage = float(raw_step)

        while percentage < 100:
            value = int(percentage)

            if value > 0 and value != speed_ladder[-1]:
                speed_ladder.append(value)

            percentage += raw_step

        if speed_ladder[-1] != 100:
            speed_ladder.append(100)

        return speed_ladder

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
            percentage = int(float(raw_percentage))
        except ValueError:
            return 0

        return max(
            0,
            min(100, percentage),
        )
