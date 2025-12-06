from __future__ import annotations
import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .controller import PicoController

_LOGGER = logging.getLogger(__name__)


class TwoButtonProfile:
    """Two-button Pico: simple ON/OFF on tap."""

    def __init__(self, controller: "PicoController") -> None:
        self._ctrl = controller

    def handle_press(self, button: str) -> None:
        if button == "on":
            asyncio.create_task(self._ctrl._short_press_on())
        elif button == "off":
            asyncio.create_task(self._ctrl._short_press_off())

    def handle_release(self, button: str) -> None:
        # no hold logic → nothing to cancel
        pass
