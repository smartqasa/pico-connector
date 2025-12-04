from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .controller import PicoController

_LOGGER = logging.getLogger(__name__)


class FourButtonProfile:
    """Four-button profile: user-defined HA actions per button."""

    def __init__(self, controller: "PicoController") -> None:
        self._ctrl = controller

    # Public entrypoint used by PicoController
    def handle(self, button: str, action: str) -> None:
        if action != "press":
            return

        action_list = self._ctrl.conf.buttons.get(button)
        if not action_list:
            _LOGGER.debug(
                "Device %s (four_button): no actions for button '%s'",
                self._ctrl.conf.device_id,
                button,
            )
            return

        for act in action_list:
            asyncio.create_task(self._ctrl._execute_button_action(act))
