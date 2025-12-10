# profiles/profile_2b.py
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)


class Pico2Button:
    """
    Two-button Pico:
    - ON and OFF only
    """

    def __init__(self, controller: "PicoController") -> None:
        self._ctrl = controller

    # -------------------------------------------------------------
    # PRESS
    # -------------------------------------------------------------
    def handle_press(self, button: str) -> None:
        domain = self._ctrl.utils.entity_domain()
        if domain is None:
            _LOGGER.debug("Pico2Button: No domain configured")
            return

        actions = self._ctrl.actions.get(domain)
        if actions is None:
            _LOGGER.debug("Pico2Button: No action module for domain '%s'", domain)
            return

        match button:
            case "on":
                actions.press_on()
            case "off":
                actions.press_off()
            case _:
                _LOGGER.debug("Pico2Button: unknown button '%s'", button)

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
            case "on":
                actions.release_on()
            case "off":
                actions.release_off()
            case _:
                pass
