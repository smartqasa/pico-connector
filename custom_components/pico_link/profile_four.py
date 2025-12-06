from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .controller import PicoController

_LOGGER = logging.getLogger(__name__)

FOUR_BUTTON_TYPES = {"button_1", "button_2", "button_3", "off"}


class FourButtonProfile:
    """Four-button scene Pico: all actions come from config."""

    def __init__(self, controller: "PicoController") -> None:
        self._ctrl = controller

    def handle_press(self, button: str) -> None:
        if button not in FOUR_BUTTON_TYPES:
            return

        cfg = self._ctrl.conf.buttons.get(button)
        if not cfg:
            return

        for action in cfg:
            asyncio.create_task(self._ctrl._execute_button_action(action))

    def handle_release(self, button: str) -> None:
        pass
