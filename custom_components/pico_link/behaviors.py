from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from homeassistant.core import CALLBACK_TYPE, HomeAssistant

from .config import PicoConfig
from .const import SUPPORTED_BUTTONS

_LOGGER = logging.getLogger(__name__)


class SharedBehaviors:
    """Mixin providing shared state and behaviors for PicoController."""

    def __init__(self, hass: HomeAssistant, conf: PicoConfig) -> None:
        self.hass = hass
        self.conf = conf

        # Press state per logical button
        self._pressed: Dict[str, bool] = {btn: False for btn in SUPPORTED_BUTTONS}

        # Task per button to implement lifecycle / ramp
        self._tasks: Dict[str, Optional[asyncio.Task]] = {
            btn: None for btn in SUPPORTED_BUTTONS
        }

        # For future features
        self._last_press_ts: Dict[str, float] = {btn: 0.0 for btn in SUPPORTED_BUTTONS}

        # Unsubscribe callback from hass.bus.async_listen
        self._unsub_event: Optional[CALLBACK_TYPE] = None

        # Convert ms → seconds
        self._hold_time = conf.hold_time_ms / 1000.0
        self._step_time = conf.step_time_ms / 1000.0

    # ---------------------------------------------------------------------
    # Shared ON/OFF behaviors (domain-aware)
    # ---------------------------------------------------------------------

    async def _short_press_on(self) -> None:
        domain = self.conf.domain

        if domain == "light":
            await self._call_entity_service(
                "turn_on",
                {"brightness_pct": self.conf.on_pct},
            )

        elif domain == "fan":
            await self._call_entity_service(
                "set_percentage",
                {"percentage": self.conf.on_pct},
            )

        elif domain == "cover":
            await self._call_entity_service("open_cover", {})

    async def _short_press_off(self) -> None:
        domain = self.conf.domain

        if domain == "light":
            await self._call_entity_service("turn_off", {})

        elif domain == "fan":
            await self._call_entity_service("turn_off", {})

        elif domain == "cover":
            await self._call_entity_service("close_cover", {})

    # ---------------------------------------------------------------------
    # Ramping (LIGHT domain only)
    # ---------------------------------------------------------------------

    async def _ramp_loop(self, direction: int, active_button: str) -> None:
        """Repeatedly brightness_step_pct while held (LIGHT ONLY)."""

        if self.conf.domain != "light":
            return  # non-light domains do not support ramping

        step = self.conf.step_pct * direction

        try:
            while self._pressed.get(active_button, False):
                await self._call_entity_service(
                    "turn_on",
                    {"brightness_step_pct": step},
                    continue_on_error=True,
                )

                if not await self._brightness_in_range(direction):
                    break

                await asyncio.sleep(self._step_time)

        except asyncio.CancelledError:
            pass

    async def _brightness_in_range(self, direction: int) -> bool:
        """Check if brightness is still within limits."""

        if not self.conf.entities:
            return False

        state = self.hass.states.get(self.conf.entities[0])
        if not state:
            return False

        brightness = state.attributes.get("brightness")
        if brightness is None:
            return True

        if direction > 0 and brightness >= 254:
            return False
        if direction < 0 and brightness <= 1:
            return False

        return True

    # ---------------------------------------------------------------------
    # FAN discrete speed helpers (domain = fan)
    # ---------------------------------------------------------------------

    def _get_fan_speed_ladder(self) -> list[int]:
        """
        Build the discrete fan speed ladder based on config.speeds.

        speeds = 4 -> ~[0, 33, 67, 100]
        speeds = 6 -> [0, 20, 40, 60, 80, 100] (default)
        """
        speeds = getattr(self.conf, "speeds", 6) or 6
        if speeds not in (4, 6):
            speeds = 6

        steps = speeds - 1
        ladder = [round(i * 100 / steps) for i in range(speeds)]
        return ladder

    def _get_current_fan_percentage(self) -> Optional[float]:
        """Return current fan percentage (0–100), or None if unavailable."""
        if not self.conf.entities:
            return None

        entity_id = self.conf.entities[0]
        state = self.hass.states.get(entity_id)
        if not state:
            return None

        pct = state.attributes.get("percentage")
        if pct is None:
            # Fallback: if fan is off, treat as 0; if on, treat as on_pct
            if state.state == "off":
                return 0.0
            return float(self.conf.on_pct)

        try:
            return float(pct)
        except (TypeError, ValueError):
            return None

    async def _fan_step_discrete(self, direction: int) -> None:
        """
        Step fan speed up or down one discrete level based on the configured
        number of speeds. Does NOT wrap around; clamps at min/max.
        """
        if not self.conf.entities:
            _LOGGER.debug(
                "Device %s (fan): no entities configured for fan control",
                self.conf.device_id,
            )
            return

        ladder = self._get_fan_speed_ladder()
        current_pct = self._get_current_fan_percentage()

        if current_pct is None:
            _LOGGER.debug(
                "Device %s (fan): unable to determine current percentage; "
                "no step performed",
                self.conf.device_id,
            )
            return

        # Find nearest speed index
        current_index = min(
            range(len(ladder)),
            key=lambda i: abs(ladder[i] - current_pct),
        )

        target_index = current_index + direction
        if target_index < 0:
            target_index = 0
        elif target_index >= len(ladder):
            target_index = len(ladder) - 1

        target_pct = ladder[target_index]

        # If no change, nothing to do
        if target_pct == current_pct:
            _LOGGER.debug(
                "Device %s (fan): percentage already at boundary (%s%%)",
                self.conf.device_id,
                target_pct,
            )
            return

        await self._call_entity_service(
            "set_percentage",
            {"percentage": target_pct},
        )

    # ---------------------------------------------------------------------
    # Generic domain-based service caller
    # ---------------------------------------------------------------------

    async def _call_entity_service(
        self,
        service: str,
        data: Dict[str, Any],
        continue_on_error: bool = False,
    ) -> None:
        domain = self.conf.domain  # light, fan, cover

        service_data = {**data}
        if self.conf.entities:
            service_data["entity_id"] = self.conf.entities

        try:
            await self.hass.services.async_call(
                domain, service, service_data, blocking=False
            )
        except Exception as err:  # noqa: BLE001
            msg = (
                f"Device {self.conf.device_id}: error calling "
                f"{domain}.{service}({service_data}): {err}"
            )
            if continue_on_error:
                _LOGGER.debug(msg)
            else:
                _LOGGER.error(msg)

    # ---------------------------------------------------------------------
    # Four-button action executor
    # ---------------------------------------------------------------------

    async def _execute_button_action(self, action: Dict[str, Any]) -> None:
        """
        Executes a mapping such as:
        {
            "action": "light.turn_on",
            "target": {"entity_id": "..."},
            "data": {...}
        }
        """
        try:
            domain, service = action["action"].split(".", 1)
        except Exception as err:
            _LOGGER.error(
                "Device %s (four_button): invalid action '%s': %s",
                self.conf.device_id,
                action,
                err,
            )
            return

        target = action.get("target")
        data = action.get("data", {})

        service_data = {**data}
        if target:
            eid = target.get("entity_id")
            if eid:
                service_data["entity_id"] = eid

        try:
            await self.hass.services.async_call(
                domain, service, service_data, blocking=False
            )
        except Exception as err:
            _LOGGER.error(
                "Device %s (four_button): error calling %s.%s: %s",
                self.conf.device_id,
                domain,
                service,
                err,
            )
