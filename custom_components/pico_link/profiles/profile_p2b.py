from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)


class PaddleSwitchPico:
    def __init__(self, controller: "PicoController") -> None:
        self._ctrl = controller

    def _actions(self):
        domain = self._ctrl.utils.entity_domain()
        if not domain:
            return None

        actions = self._ctrl.actions.get(domain)
        if not actions:
            _LOGGER.debug("P2B: No action handler available for domain %s", domain)
            return None

        return actions

    # -------------------------------------------------------------
    # PRESS
    # -------------------------------------------------------------
    def handle_press(self, button: str) -> None:
        actions = self._actions()
        if not actions:
            return

        match button:
            case "on":
                actions.press_on()
            case "off":
                actions.press_off()
            case _:
                _LOGGER.debug("P2B: Ignoring unexpected press button '%s'", button)

    # -------------------------------------------------------------
    # RELEASE
    # -------------------------------------------------------------
    def handle_release(self, button: str) -> None:
        actions = self._actions()
        if not actions:
            return

        match button:
            case "on":
                actions.release_on()
            case "off":
                actions.release_off()
            case _:
                _LOGGER.debug("P2B: Ignoring unexpected release button '%s'", button)
