# fan_actions.py
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..controller import PicoController


class FanActions:
    """
    Tap-only fan behavior for all supported Pico profiles.

    ON:
        Set the fan to fan_on_pct.

    OFF:
        Turn the fan off.

    RAISE:
        Move up one discrete fan-speed step.

    LOWER:
        Move down one discrete fan-speed step.

    STOP:
        Execute configured middle_button actions, or reverse the fan
        direction when no custom actions are configured.
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl

        # Retain the most recently requested percentage so rapid taps
        # do not depend on Home Assistant updating entity state between
        # button presses.
        self._target_percentage: Optional[int] = None

    # =============================================================
    # PROFILE ENTRY POINTS
    # =============================================================

    def press_on(self) -> None:
        percentage = self.ctrl.conf.fan_on_pct
        self._target_percentage = percentage

        self.ctrl.create_task(
            self._set_percentage(percentage),
            "fan-turn-on",
        )

    def release_on(self) -> None:
        pass

    def press_off(self) -> None:
        self._target_percentage = 0

        self.ctrl.create_task(
            self._turn_off(),
            "fan-turn-off",
        )

    def release_off(self) -> None:
        pass

    def press_stop(self) -> None:
        # Direction changes and custom actions may alter the fan outside
        # this class, so resynchronize percentage on the next speed tap.
        self._target_percentage = None

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
        """Move to the next higher fan-speed step."""
        self._step(
            direction=1,
            task_name="fan-step-up",
        )

    def release_raise(self) -> None:
        pass

    def press_lower(self) -> None:
        """Move to the next lower fan-speed step."""
        self._step(
            direction=-1,
            task_name="fan-step-down",
        )

    def release_lower(self) -> None:
        pass

    # =============================================================
    # FAN OPERATIONS
    # =============================================================

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

    async def _set_percentage(
        self,
        percentage: int,
    ) -> None:
        await self.ctrl.utils.call_service(
            "set_percentage",
            {"percentage": percentage},
            domain="fan",
        )

    # =============================================================
    # SPEED STEPPING
    # =============================================================

    def _step(
        self,
        *,
        direction: int,
        task_name: str,
    ) -> None:
        """
        Move the fan by one discrete speed step.

        The target is calculated synchronously so rapid button taps build
        on the previous requested percentage instead of waiting for the
        Home Assistant entity state to update.
        """
        speed_ladder = self._get_speed_ladder()

        if not speed_ladder:
            return

        current_percentage = self._target_percentage

        if current_percentage is None:
            current_percentage = self._get_current_percentage()

        if current_percentage is None:
            return

        new_percentage = self._calculate_next_percentage(
            current_percentage,
            direction,
            speed_ladder,
        )

        if new_percentage == current_percentage:
            return

        self._target_percentage = new_percentage

        self.ctrl.create_task(
            self._set_percentage(new_percentage),
            task_name,
        )

    # =============================================================
    # SPEED HELPERS
    # =============================================================

    def _get_speed_ladder(self) -> list[int]:
        """Build a discrete speed ladder from percentage_step."""
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

        step = min(
            100.0,
            max(1.0, float(raw_step)),
        )

        speed_ladder = [0]
        percentage = step

        while percentage < 100:
            value = min(
                99,
                max(1, round(percentage)),
            )

            if value != speed_ladder[-1]:
                speed_ladder.append(value)

            percentage += step

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
            percentage = round(float(raw_percentage))
        except ValueError:
            return 0

        return min(
            100,
            max(0, percentage),
        )

    @staticmethod
    def _calculate_next_percentage(
        current_percentage: int,
        direction: int,
        speed_ladder: list[int],
    ) -> int:
        """Return the next ladder value above or below the current speed."""
        if direction > 0:
            return next(
                (
                    percentage
                    for percentage in speed_ladder
                    if percentage > current_percentage
                ),
                speed_ladder[-1],
            )

        return next(
            (
                percentage
                for percentage in reversed(speed_ladder)
                if percentage < current_percentage
            ),
            speed_ladder[0],
        )

    # =============================================================
    # LIFECYCLE
    # =============================================================

    def reset_state(self) -> None:
        """Clear the optimistic fan-speed target."""
        self._target_percentage = None
