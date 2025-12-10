# switch_actions.py
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)


class SwitchActions:
    """
    Encapsulates switch-specific behavior:

    - on   → turn_on
    - off  → turn_off
    - stop → no-op
    - raise/lower → ignored (switches have no levels)
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl

    # -------------------------------------------------------------
    # PUBLIC ENTRY: PRESS
    # -------------------------------------------------------------
    def handle_press(self, button: str) -> None:
        match button:

            case "on":
                asyncio.create_task(self._turn_on())

            case "off":
                asyncio.create_task(self._turn_off())

            case "stop":
                # No meaning for switches
                _LOGGER.debug("SwitchActions: stop ignored")
                return

            case "raise" | "lower":
                _LOGGER.debug("SwitchActions: %s ignored", button)
                return

            case _:
                _LOGGER.debug("SwitchActions: unknown button '%s'", button)

    # -------------------------------------------------------------
    # PUBLIC ENTRY: RELEASE
    # -------------------------------------------------------------
    def handle_release(self, button: str) -> None:
        # Switches have zero release behavior
        pass

    # -------------------------------------------------------------
    # DOMAIN ACTION IMPLEMENTATIONS
    # -------------------------------------------------------------
    async def _turn_on(self):
        await self.ctrl.utils.call_service(
            "turn_on",
            {},
            domain="switch",
        )

    async def _turn_off(self):
        await self.ctrl.utils.call_service(
            "turn_off",
            {},
            domain="switch",
        )
