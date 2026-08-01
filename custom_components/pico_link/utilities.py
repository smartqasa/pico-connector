from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional, cast

from homeassistant.core import HomeAssistant

if TYPE_CHECKING:
    from .controller import PicoController

_LOGGER = logging.getLogger(__name__)

# Single source of truth for the relationship between a Home Assistant
# domain and the corresponding PicoConfig entity-list field.
_DOMAIN_ENTITY_FIELDS = {
    "cover": "covers",
    "light": "lights",
    "fan": "fans",
    "media_player": "media_players",
    "switch": "switches",
}


class SharedUtils:
    """
    Shared entity-resolution and service-execution helpers.

    Domain-specific gesture state remains owned by the action modules.
    """

    def __init__(self, ctrl: "PicoController") -> None:
        self.ctrl = ctrl
        self.hass: HomeAssistant = ctrl.hass
        self.conf = ctrl.conf

        # Convert configured millisecond values once for use by
        # tap-versus-hold and ramp behavior.
        self._hold_time = self.conf.hold_time_ms / 1000.0
        self._step_time = self.conf.step_time_ms / 1000.0

    # =============================================================
    # ENTITY RESOLUTION
    # =============================================================

    def entities_for_domain(self, domain: str) -> list[str]:
        """Return all configured entities for a supported domain."""
        field_name = _DOMAIN_ENTITY_FIELDS.get(domain)

        if field_name is None:
            return []

        return cast(
            list[str],
            getattr(self.conf, field_name),
        )

    def entity_domain(self) -> Optional[str]:
        """Return the single configured entity domain."""
        for domain in _DOMAIN_ENTITY_FIELDS:
            if self.entities_for_domain(domain):
                return domain

        return None

    def primary_entity(
        self,
        domain: Optional[str] = None,
    ) -> Optional[str]:
        """Return the first configured entity for a domain."""
        selected_domain = domain or self.entity_domain()

        if selected_domain is None:
            return None

        entities = self.entities_for_domain(selected_domain)

        return entities[0] if entities else None

    def get_entity_state(
        self,
        domain: Optional[str] = None,
    ):
        """Return the state of the primary configured entity."""
        entity_id = self.primary_entity(domain)

        if entity_id is None:
            return None

        return self.hass.states.get(entity_id)

    # =============================================================
    # SERVICE EXECUTION
    # =============================================================

    async def _execute_service_call(
        self,
        domain: str,
        service: str,
        data: dict[str, Any],
        *,
        blocking: bool,
        target: Optional[dict[str, Any]] = None,
    ) -> None:
        """Execute and centrally log a Home Assistant service call."""
        try:
            await self.hass.services.async_call(
                domain,
                service,
                data,
                blocking=blocking,
                target=target,
            )
        except Exception:
            _LOGGER.exception(
                "Device %s: error calling %s.%s with data=%s target=%s",
                self.conf.device_id,
                domain,
                service,
                data,
                target,
            )

    async def call_service(
        self,
        service: str,
        data: dict[str, Any],
        *,
        domain: str,
        blocking: bool = False,
    ) -> None:
        """Call a service for every configured entity in a domain."""
        entities = self.entities_for_domain(domain)

        if not entities:
            _LOGGER.error(
                "Device %s: no entities configured for domain %s; cannot call %s.%s",
                self.conf.device_id,
                domain,
                domain,
                service,
            )
            return

        service_data = dict(data)
        service_data["entity_id"] = entities

        await self._execute_service_call(
            domain,
            service,
            service_data,
            blocking=blocking,
        )

    # =============================================================
    # CONFIGURED ACTION EXECUTION
    # =============================================================

    async def execute_button_action(
        self,
        action: Any,
    ) -> None:
        """Execute one configured action or an ordered list of actions."""
        if isinstance(action, list):
            for item in action:
                await self.execute_button_action(item)

            return

        if not isinstance(action, dict):
            _LOGGER.error(
                "Device %s: invalid action format: %r",
                self.conf.device_id,
                action,
            )
            return

        action_name = action.get("action")

        if not isinstance(action_name, str):
            _LOGGER.error(
                "Device %s: invalid action string %r",
                self.conf.device_id,
                action_name,
            )
            return

        domain, separator, service = action_name.partition(".")

        if not separator or not domain or not service:
            _LOGGER.error(
                "Device %s: invalid action string %r",
                self.conf.device_id,
                action_name,
            )
            return

        raw_data = action.get("data", {})

        if not isinstance(raw_data, dict):
            _LOGGER.error(
                "Device %s: data for %s must be a mapping",
                self.conf.device_id,
                action_name,
            )
            return

        raw_target = action.get("target")

        if raw_target is not None and not isinstance(
            raw_target,
            dict,
        ):
            _LOGGER.error(
                "Device %s: target for %s must be a mapping",
                self.conf.device_id,
                action_name,
            )
            return

        # Configured action lists are deliberately blocking so each
        # action completes before the next action begins.
        await self._execute_service_call(
            domain,
            service,
            raw_data,
            blocking=True,
            target=raw_target,
        )
