# profiles/profile_4b.py
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, List, Dict, Any

if TYPE_CHECKING:
    from ..controller import PicoController

_LOGGER = logging.getLogger(__name__)


class Pico4ButtonScene:
    """
    Hardened Pico 4-button scene controller.

    - Each button maps to a YAML-defined list of service actions.
    - Executes each action safely and independently.
    - Never raises exceptions due to misconfiguration.
    """

    def __init__(self, controller: "PicoController") -> None:
        self._ctrl = controller

        # ---------------------------------------------------------
        # Validate high-level configuration early
        # ---------------------------------------------------------
        btns = self._ctrl.conf.buttons

        if not isinstance(btns, dict):
            _LOGGER.error(
                "4B device %s: 'buttons' must be a mapping {button: [actions...]}, got %s",
                self._ctrl.conf.device_id,
                type(btns),
            )
            self._valid = False
            return

        # Validate each button entry
        for key, val in btns.items():
            if not isinstance(key, str):
                _LOGGER.error(
                    "4B device %s: button keys must be strings, got %s",
                    self._ctrl.conf.device_id,
                    type(key),
                )
                self._valid = False
                return

            if not isinstance(val, list):
                _LOGGER.error(
                    "4B device %s: actions for button '%s' must be a list, got %s",
                    self._ctrl.conf.device_id,
                    key,
                    type(val),
                )
                self._valid = False
                return

        self._valid = True

    # ---------------------------------------------------------
    # PRESS → Execute scene
    # ---------------------------------------------------------
    def handle_press(self, button: str) -> None:
        if not self._valid:
            _LOGGER.error(
                "4B device %s: invalid 'buttons' config; ignoring press.",
                self._ctrl.conf.device_id,
            )
            return

        scene_map: Dict[str, List[Any]] = self._ctrl.conf.buttons

        actions = scene_map.get(button)
        if actions is None:
            _LOGGER.debug(
                "4B device %s: button '%s' has no configured scene actions.",
                self._ctrl.conf.device_id,
                button,
            )
            return

        if not isinstance(actions, list):
            _LOGGER.error(
                "4B device %s: actions for button '%s' must be a list, got %s",
                self._ctrl.conf.device_id,
                button,
                type(actions),
            )
            return

        # Schedule execution of each action
        for idx, action in enumerate(actions):
            if not isinstance(action, dict):
                _LOGGER.error(
                    "4B device %s: action #%d for button '%s' must be a dict (YAML object), got %s",
                    self._ctrl.conf.device_id,
                    idx,
                    button,
                    type(action),
                )
                continue

            # Run each action with isolation + logging
            asyncio.create_task(self._execute_scene_action(button, idx, action))

    # ---------------------------------------------------------
    # RELEASE → No behavior
    # ---------------------------------------------------------
    def handle_release(self, button: str) -> None:
        # Scene remotes do not have hold logic → release is ignored.
        pass

    # ---------------------------------------------------------
    # Internal: Safe execution wrapper for each action
    # ---------------------------------------------------------
    async def _execute_scene_action(self, button: str, idx: int, action: Dict[str, Any]):
        """
        Executes a single scene action safely, with detailed error logging.
        """

        try:
            await self._ctrl.utils.execute_button_action(action)

        except Exception as e:
            _LOGGER.error(
                (
                    "4B device %s: error executing scene action #%d for button '%s': %s\n"
                    "Action content: %s"
                ),
                self._ctrl.conf.device_id,
                idx,
                button,
                e,
                action,
            )
