# profiles/profile_p2b.py
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)


class PaddleSwitchPico:
    """
    P2B Paddle Pico:

    - ON / OFF buttons only.
    - Lights: tap vs hold handled inside LightActions.
    - Fans: tap cycles speed, hold ramps, stop reverses direction.
    - Covers: on=open, off=close, stop=stop.
    - Media players: on/off = power; raise/lower = volume.
    - Switches: on/off only.
    """

    def __init__(self, controller: "PicoController") -> None:
        self._ctrl = controller

    def _actions(self):
        """Return the correct domain actions handler."""
        domain = self._ctrl.utils.entity_domain()
        if not domain:
            return None

        actions = self._ctrl.actions.get(domain)
        if not actions:
            _LOGGER.debug("P2B: No action handler available for domain %s", domain)
            return None

        return actions

    # -------------------------------------------------------------
    # PRESS
    # -------------------------------------------------------------
    def handle_press(self, button: str) -> None:
        actions = self._actions()
        if not actions:
            return

        match button:
            case "on":
                actions.press_on()

            case "off":
                actions.press_off()

            case "stop":
                # Covers, fans, lights (middle_button), media → all use stop
                actions.press_stop()

            case "raise":
                # Rare but required for domain compatibility
                actions.press_raise()

            case "lower":
                actions.press_lower()

            case _:
                _LOGGER.debug("P2B: Ignoring unexpected press button '%s'", button)

    # -------------------------------------------------------------
    # RELEASE
    # -------------------------------------------------------------
    def handle_release(self, button: str) -> None:
        actions = self._actions()
        if not actions:
            return

        match button:
            case "on":
                actions.release_on()

            case "off":
                actions.release_off()

            case "stop":
                actions.release_stop()

            case "raise":
                actions.release_raise()

            case "lower":
                actions.release_lower()

            case _:
                _LOGGER.debug("P2B: Ignoring unexpected release button '%s'", button)
