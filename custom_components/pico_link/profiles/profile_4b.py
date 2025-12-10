from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, List, Dict, Any

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)


class Pico4ButtonScene:
    """
    Pico 4-button scene controller:
    - Each button maps to a YAML-defined list of HA service calls.
    - Executes each action in order.
    """

    def __init__(self, controller: "PicoController") -> None:
        self._ctrl = controller

        # Validate config early
        if not isinstance(self._ctrl.conf.buttons, dict):
            _LOGGER.error(
                "4B device %s has invalid 'buttons' configuration (expected dict).",
                self._ctrl.conf.device_id,
            )

    # -------------------------------------------------------------
    # PRESS
    # -------------------------------------------------------------
    def handle_press(self, button: str) -> None:
        scene_map = self._ctrl.conf.buttons

        if not isinstance(scene_map, dict):
            _LOGGER.error("Pico4B: misconfigured buttons mapping (not a dict)")
            return

        if button not in scene_map:
            _LOGGER.debug(
                "Pico4B: button '%s' has no configured actions for device %s",
                button,
                self._ctrl.conf.device_id,
            )
            return

        actions = scene_map.get(button, [])

        if not isinstance(actions, list):
            _LOGGER.error(
                "Pico4B: actions for button '%s' must be a list, got %s",
                button,
                type(actions),
            )
            return

        # Execute each action individually
        for action in actions:
            asyncio.create_task(self._ctrl.utils.execute_button_action(action))

    # -------------------------------------------------------------
    # RELEASE
    # -------------------------------------------------------------
    def handle_release(self, button: str) -> None:
        """Scene buttons do nothing on release."""
        return
