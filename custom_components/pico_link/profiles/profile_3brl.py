# profiles/profile_3brl.py
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)


class Pico3ButtonRaiseLower:
    """
    Clean 3BRL profile:
    - Converts button presses/releases into semantic actions
    - Routes actions to the appropriate domain module
    """

    def __init__(self, controller: "PicoController") -> None:
        self._ctrl = controller

    # -------------------------------------------------------------
    # PRESS
    # -------------------------------------------------------------
    def handle_press(self, button: str) -> None:
        domain = self._ctrl.utils.entity_domain()
        if domain is None:
            _LOGGER.debug("Pico3BRL: No domain configured")
            return

        actions = self._ctrl.actions.get(domain)
        if actions is None:
            _LOGGER.error("Pico3BRL: No action module for domain '%s'", domain)
            return

        match button:
            case "on":
                actions.press_on()
            case "off":
                actions.press_off()
            case "stop":
                actions.press_stop()
            case "raise":
                actions.press_raise()
            case "lower":
                actions.press_lower()
            case _:
                _LOGGER.debug("Pico3BRL: unknown button '%s'", button)

    # -------------------------------------------------------------
    # RELEASE
    # -------------------------------------------------------------
    def handle_release(self, button: str) -> None:
        domain = self._ctrl.utils.entity_domain()
        if domain is None:
            return

        actions = self._ctrl.actions.get(domain)
        if actions is None:
            return

        match button:
            case "raise":
                actions.release_raise()
            case "lower":
                actions.release_lower()
            case _:
                pass
