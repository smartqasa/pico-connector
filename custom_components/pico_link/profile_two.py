from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .controller import PicoController

_LOGGER = logging.getLogger(__name__)


class TwoButtonProfile:
    """Two-button profile: simple ON/OFF on press."""

    def __init__(self, controller: "PicoController") -> None:
        self._ctrl = controller

    # Public entrypoint used by PicoController
    def handle(self, button: str, action: str) -> None:
        if action != "press":
            return

        if button == "on":
            asyncio.create_task(self._ctrl._short_press_on())
        elif button == "off":
            asyncio.create_task(self._ctrl._short_press_off())
