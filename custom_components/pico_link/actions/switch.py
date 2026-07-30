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
    Switch-specific behavior.

    Behaviors:
      ON press     → turn on
      OFF press    → turn off
      STOP press   → configured middle_button actions, otherwise no-op
      RAISE/LOWER  → no-op
      Releases     → no-op
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl

    # ==============================================================
    # ON
    # ==============================================================

    def press_on(self) -> None:
        asyncio.create_task(self._turn_on())

    def release_on(self) -> None:
        pass

    # ==============================================================
    # OFF
    # ==============================================================

    def press_off(self) -> None:
        asyncio.create_task(self._turn_off())

    def release_off(self) -> None:
        pass

    # ==============================================================
    # STOP
    # ==============================================================

    def press_stop(self) -> None:
        """
        Execute configured middle-button actions.

        Switches have no default STOP behavior.
        """
        actions = self.ctrl.conf.middle_button

        if not actions:
            _LOGGER.debug("Switch STOP pressed: no middle_button actions configured")
            return

        for action in actions:
            asyncio.create_task(self.ctrl.utils.execute_button_action(action))

    def release_stop(self) -> None:
        pass

    # ==============================================================
    # RAISE / LOWER
    # ==============================================================

    def press_raise(self) -> None:
        _LOGGER.debug("Switch RAISE pressed: ignored")

    def release_raise(self) -> None:
        pass

    def press_lower(self) -> None:
        _LOGGER.debug("Switch LOWER pressed: ignored")

    def release_lower(self) -> None:
        pass

    # ==============================================================
    # SWITCH OPERATIONS
    # ==============================================================

    async def _turn_on(self) -> None:
        await self.ctrl.utils.call_service(
            "turn_on",
            {},
            domain="switch",
        )

    async def _turn_off(self) -> None:
        await self.ctrl.utils.call_service(
            "turn_off",
            {},
            domain="switch",
        )
