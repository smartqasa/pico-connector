from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING
from homeassistant.core import HomeAssistant

if TYPE_CHECKING:
    from .controller import PicoController

_LOGGER = logging.getLogger(__name__)


class SharedUtils:
    """
    PURE utilities shared by all action modules.
    Zero domain-specific state.
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl
        self.hass: HomeAssistant = ctrl.hass
        self.conf = ctrl.conf

        # Timing parameters
        self._hold_time = self.conf.hold_time_ms / 1000.0
        self._step_time = self.conf.step_time_ms / 1000.0

        # Removed controller._pressed / controller._tasks usage entirely

    # -------------------------------------------------------------
    # ENTITY RESOLUTION
    # -------------------------------------------------------------
    def entity_domain(self) -> Optional[str]:
        if self.conf.covers:
            return "cover"
        if self.conf.lights:
            return "light"
        if self.conf.fans:
            return "fan"
        if self.conf.media_players:
            return "media_player"
        if self.conf.switches:
            return "switch"
        return None

    def primary_entity(self) -> Optional[str]:
        if self.conf.covers:
            return self.conf.covers[0]
        if self.conf.lights:
            return self.conf.lights[0]
        if self.conf.fans:
            return self.conf.fans[0]
        if self.conf.media_players:
            return self.conf.media_players[0]
        if self.conf.switches:
            return self.conf.switches[0]
        return None

    def get_entity_state(self):
        entity_id = self.primary_entity()
        if not entity_id:
            return None
        return self.hass.states.get(entity_id)

    # -------------------------------------------------------------
    # GENERIC SERVICE CALLER
    # -------------------------------------------------------------
    async def call_service(
        self,
        service: str,
        data: Dict[str, Any],
        *,
        domain: str,
        continue_on_error: bool = False,
    ) -> None:
        match domain:
            case "cover":
                entities = self.conf.covers
            case "light":
                entities = self.conf.lights
            case "fan":
                entities = self.conf.fans
            case "media_player":
                entities = self.conf.media_players
            case "switch":
                entities = self.conf.switches
            case _:
                entities = []

        svc_data = dict(data)
        if entities:
            svc_data["entity_id"] = entities

        try:
            await self.hass.services.async_call(
                domain,
                service,
                svc_data,
                blocking=False,
            )
        except Exception as err:
            msg = (
                f"Device {self.conf.device_id}: error calling "
                f"{domain}.{service}({svc_data}): {err}"
            )
            if continue_on_error:
                _LOGGER.debug(msg)
            else:
                _LOGGER.error(msg)

    # -------------------------------------------------------------
    # ACTION EXECUTION (Scenes & 4B)
    # -------------------------------------------------------------
    async def execute_button_action(self, action):
        if isinstance(action, list):
            for a in action:
                await self.execute_button_action(a)
            return

        if not isinstance(action, dict):
            _LOGGER.error(
                "Device %s: invalid action format: %s",
                self.ctrl.conf.device_id,
                action,
            )
            return

        try:
            domain, service = action["action"].split(".", 1)
        except Exception:
            _LOGGER.error(
                "Device %s: invalid action string '%s'",
                self.ctrl.conf.device_id,
                action.get("action"),
            )
            return

        data = action.get("data", {})
        target = action.get("target")

        try:
            await self.hass.services.async_call(
                domain,
                service,
                data,
                blocking=False,
                target=target,
            )
        except Exception as err:
            _LOGGER.error(
                "Device %s: error calling %s.%s → %s",
                self.ctrl.conf.device_id,
                domain,
                service,
                err,
            )
