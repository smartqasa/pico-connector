# profiles/profile_4b.py
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)


class Pico4ButtonScene:
    """
    Pico 4-button scene controller:
    - Each button maps to a YAML-defined list of HA service calls.
    - Profile triggers scenes directly via controller/utils.
    - No domain routing used for scenes.
    """

    def __init__(self, controller: "PicoController") -> None:
        self._ctrl = controller

    # -------------------------------------------------------------
    # PRESS
    # -------------------------------------------------------------
    def handle_press(self, button: str) -> None:
        scene_map = self._ctrl.conf.buttons

        if button not in scene_map:
            _LOGGER.debug("Pico4B: button '%s' has no configured scene", button)
            return

        scene_actions = scene_map[button]
        asyncio.create_task(self._ctrl.utils.execute_button_action(scene_actions))

    # -------------------------------------------------------------
    # RELEASE
    # -------------------------------------------------------------
    def handle_release(self, button: str) -> None:
        """
        Scene buttons typically do nothing on release.
        Included only for protocol completeness.
        """
        pass
