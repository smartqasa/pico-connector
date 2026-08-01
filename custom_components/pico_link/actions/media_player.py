from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)


class MediaPlayerActions:
    """
    Media-player behavior for supported Pico profiles.

    Semantics:
        ON tap     → play/pause
        OFF tap    → next track
        RAISE tap  → one volume step up
        RAISE hold → continuously raise volume
        LOWER tap  → one volume step down
        LOWER hold → continuously lower volume
        STOP tap   → configured middle_button actions or mute/unmute
    """

    MAX_RAMP_STEPS = 50

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl

        # Only one raise/lower gesture may be active at a time.
        self._active_button: Optional[str] = None

        # Incremented whenever a gesture starts or is canceled.
        # Delayed tasks must still match this generation before acting.
        self._gesture_generation = 0

        # The most recent volume requested by the active gesture.
        # This avoids depending on immediate state updates during a ramp.
        self._target_volume: Optional[float] = None

        # Retain both tasks so a new gesture or command can cancel them.
        self._step_task: Optional[asyncio.Task] = None
        self._hold_task: Optional[asyncio.Task] = None

    # =============================================================
    # GESTURE STATE
    # =============================================================

    def _clear_volume_gesture(
        self,
        *,
        cancel_step: bool = True,
    ) -> None:
        """
        Cancel the active volume gesture.

        The immediate step is not canceled on a normal release because
        a quick tap must still complete its volume change.
        """
        self._gesture_generation += 1
        self._active_button = None
        self._target_volume = None

        if self._hold_task and not self._hold_task.done():
            self._hold_task.cancel()

        self._hold_task = None

        if cancel_step and self._step_task and not self._step_task.done():
            self._step_task.cancel()

        self._step_task = None

    def _start_raise_lower(
        self,
        button: str,
        direction: int,
    ) -> None:
        """Perform one volume step and arm continuous ramping."""
        current_volume = self._target_volume

        if current_volume is None:
            current_volume = self._get_current_volume()

        # A new directional press supersedes any previous gesture.
        self._clear_volume_gesture()

        if current_volume is None:
            return

        new_volume = self._calculate_next_volume(
            current_volume,
            direction,
        )

        # Already at the requested endpoint.
        if new_volume == current_volume:
            return

        self._active_button = button
        self._target_volume = new_volume
        generation = self._gesture_generation

        # Every press performs one immediate step.
        self._step_task = self.ctrl.create_task(
            self._set_volume(new_volume),
            f"media-{button}-step",
        )

        # Continuous ramping begins only after the hold threshold.
        self._hold_task = self.ctrl.create_task(
            self._hold_lifecycle(
                button,
                direction,
                generation,
            ),
            f"media-{button}-hold",
        )

    def _release_raise_lower(self, button: str) -> None:
        """Finish the active volume gesture."""
        # Ignore releases from a superseded direction.
        if self._active_button != button:
            return

        # Allow the immediate tap step to complete while canceling
        # delayed or active ramp behavior.
        self._clear_volume_gesture(cancel_step=False)

    def _gesture_is_current(
        self,
        button: str,
        generation: int,
    ) -> bool:
        """Return True when a task still belongs to the active gesture."""
        return generation == self._gesture_generation and self._active_button == button

    # =============================================================
    # PROFILE ENTRY POINTS
    # =============================================================

    # -------------------------------------------------------------
    # ON
    # -------------------------------------------------------------

    def press_on(self) -> None:
        # A direct command supersedes any volume ramp.
        self._clear_volume_gesture()

        self.ctrl.create_task(
            self._play_pause(),
            "media-play-pause",
        )

    def release_on(self) -> None:
        pass

    # -------------------------------------------------------------
    # OFF
    # -------------------------------------------------------------

    def press_off(self) -> None:
        # A direct command supersedes any volume ramp.
        self._clear_volume_gesture()

        self.ctrl.create_task(
            self._next_track(),
            "media-next-track",
        )

    def release_off(self) -> None:
        pass

    # -------------------------------------------------------------
    # STOP
    # -------------------------------------------------------------

    def press_stop(self) -> None:
        # A direct command supersedes any volume ramp.
        self._clear_volume_gesture()

        actions = self.ctrl.conf.middle_button

        if actions:
            self.ctrl.create_task(
                self.ctrl.utils.execute_button_action(actions),
                "media-middle-button",
            )
            return

        self.ctrl.create_task(
            self._toggle_mute(),
            "media-toggle-mute",
        )

    def release_stop(self) -> None:
        pass

    # -------------------------------------------------------------
    # RAISE
    # -------------------------------------------------------------

    def press_raise(self) -> None:
        self._start_raise_lower(
            "raise",
            direction=1,
        )

    def release_raise(self) -> None:
        self._release_raise_lower("raise")

    # -------------------------------------------------------------
    # LOWER
    # -------------------------------------------------------------

    def press_lower(self) -> None:
        self._start_raise_lower(
            "lower",
            direction=-1,
        )

    def release_lower(self) -> None:
        self._release_raise_lower("lower")

    # =============================================================
    # HOLD AND RAMP LIFECYCLE
    # =============================================================

    async def _hold_lifecycle(
        self,
        button: str,
        direction: int,
        generation: int,
    ) -> None:
        """Ramp volume after the configured hold threshold."""
        try:
            await asyncio.sleep(self.ctrl.utils._hold_time)

            if not self._gesture_is_current(button, generation):
                return

            for _ in range(self.MAX_RAMP_STEPS):
                if not self._gesture_is_current(button, generation):
                    return

                current_volume = self._target_volume

                if current_volume is None:
                    return

                new_volume = self._calculate_next_volume(
                    current_volume,
                    direction,
                )

                # Stop naturally at volume 0.0 or 1.0.
                if new_volume == current_volume:
                    return

                self._target_volume = new_volume

                if not self._gesture_is_current(button, generation):
                    return

                await self._set_volume(new_volume)

                if not self._gesture_is_current(button, generation):
                    return

                await asyncio.sleep(self.ctrl.utils._step_time)

            if self._gesture_is_current(button, generation):
                _LOGGER.warning(
                    "MediaPlayerActions: volume ramp stopped after %s "
                    "steps for device %s button %s",
                    self.MAX_RAMP_STEPS,
                    self.ctrl.conf.device_id,
                    button,
                )

        except asyncio.CancelledError:
            # Expected when the button is released or another command
            # supersedes this gesture.
            pass

    # =============================================================
    # MEDIA-PLAYER OPERATIONS
    # =============================================================

    async def _play_pause(self) -> None:
        await self.ctrl.utils.call_service(
            "media_play_pause",
            {},
            domain="media_player",
        )

    async def _next_track(self) -> None:
        await self.ctrl.utils.call_service(
            "media_next_track",
            {},
            domain="media_player",
        )

    async def _toggle_mute(self) -> None:
        state = self.ctrl.utils.get_entity_state()

        if not state:
            return

        is_muted = state.attributes.get("is_volume_muted")
        new_value = not bool(is_muted)

        await self.ctrl.utils.call_service(
            "volume_mute",
            {"is_volume_muted": new_value},
            domain="media_player",
        )

    async def _set_volume(self, volume: float) -> None:
        """Set media volume using a normalized 0.0–1.0 value."""
        await self.ctrl.utils.call_service(
            "volume_set",
            {"volume_level": volume},
            domain="media_player",
        )

    # =============================================================
    # VOLUME HELPERS
    # =============================================================

    def _calculate_next_volume(
        self,
        current_volume: float,
        direction: int,
    ) -> float:
        """Return the next clamped volume level."""
        step = self.ctrl.conf.media_player_vol_step / 100.0

        new_volume = current_volume + (step * direction)
        new_volume = max(0.0, min(1.0, new_volume))

        return round(new_volume, 4)

    def _get_current_volume(self) -> Optional[float]:
        """Return the current normalized volume level."""
        state = self.ctrl.utils.get_entity_state()

        if not state:
            return None

        raw_volume = state.attributes.get("volume_level")

        if isinstance(raw_volume, bool) or not isinstance(
            raw_volume, (int, float, str)
        ):
            return None

        try:
            volume = float(raw_volume)
        except ValueError:
            return None

        return max(0.0, min(1.0, volume))

    # =============================================================
    # LIFECYCLE
    # =============================================================

    def reset_state(self) -> None:
        """Cancel all volume tasks and clear gesture state."""
        self._clear_volume_gesture()
