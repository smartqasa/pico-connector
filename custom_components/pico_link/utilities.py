from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional, cast

from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers.script import Script

from .const import DOMAIN

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
        actions: list[dict[str, Any]],
        *,
        name: str = "pico_link_action",
    ) -> None:
        """
        Run a configured action sequence.

        Actions were already validated against Home Assistant's own
        script schema in config.py, so the full range of native
        actions is supported here: plain service calls, conditions,
        if-then, choose, repeat, and templates — executed with the
        same engine Home Assistant scripts and automations use.
        """
        if not actions:
            return

        script = Script(
            self.hass,
            actions,
            name,
            DOMAIN,
        )

        try:
            await script.async_run(context=Context())
        except Exception:
            _LOGGER.exception(
                "Device %s: error running configured action sequence",
                self.conf.device_id,
            )
