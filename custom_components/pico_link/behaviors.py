from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from homeassistant.core import CALLBACK_TYPE, HomeAssistant

from .config import PicoConfig
from .const import SUPPORTED_BUTTONS

_LOGGER = logging.getLogger(__name__)


class SharedBehaviors:
    """Mixin providing shared behaviors for all PicoController profiles."""

    def __init__(self, hass: HomeAssistant, conf: PicoConfig) -> None:
        self.hass = hass
        self.conf = conf

        # Press state per logical button
        self._pressed: Dict[str, bool] = {btn: False for btn in SUPPORTED_BUTTONS}

        # Task per button for ramp-type behaviors
        self._tasks: Dict[str, Optional[asyncio.Task]] = {
            btn: None for btn in SUPPORTED_BUTTONS
        }

        self._last_press_ts: Dict[str, float] = {btn: 0.0 for btn in SUPPORTED_BUTTONS}
        self._unsub_event: Optional[CALLBACK_TYPE] = None

        # Convert ms → seconds
        self._hold_time = conf.hold_time_ms / 1000.0
        self._step_time = conf.step_time_ms / 1000.0

    # ---------------------------------------------------------------------
    # ON / OFF BEHAVIORS (DOMAIN-AWARE)
    # ---------------------------------------------------------------------

    async def _short_press_on(self) -> None:
        domain = self.conf.domain

        #
        # MEDIA PLAYER
        #
        if domain == "media_player":
            await self._media_play_pause()
            return

        #
        # LIGHT
        #
        if domain == "light":
            await self._call_entity_service(
                "turn_on",
                {"brightness_pct": self.conf.on_pct},
            )
            return

        #
        # FAN
        #
        if domain == "fan":
            await self._call_entity_service(
                "set_percentage",
                {"percentage": self.conf.on_pct},
            )
            return

        #
        # COVER
        #
        if domain == "cover":
            entity_id = (
                self.conf.entities[0] if self.conf.entities else None
            )

            fallback = False

            if entity_id:
                state = self.hass.states.get(entity_id)
                supports_position = (
                    "current_position" in state.attributes
                    if state else False
                )
            else:
                supports_position = False

            # Use position if supported
            if supports_position:
                try:
                    await self._call_entity_service(
                        "set_cover_position",
                        {"position": self.conf.on_pct},
                    )
                    return
                except Exception as err:
                    _LOGGER.debug(
                        "Device %s (cover): position failed (%s), fallback to open",
                        self.conf.device_id,
                        err,
                    )
                    fallback = True
            else:
                fallback = True

            if fallback:
                await self._call_entity_service("open_cover", {})

    async def _short_press_off(self) -> None:
        domain = self.conf.domain

        #
        # MEDIA PLAYER
        #
        if domain == "media_player":
            await self._media_next()
            return

        #
        # LIGHT
        #
        if domain == "light":
            await self._call_entity_service("turn_off", {})
            return

        #
        # FAN
        #
        if domain == "fan":
            await self._call_entity_service("turn_off", {})
            return

        #
        # COVER
        #
        if domain == "cover":
            await self._call_entity_service("close_cover", {})
            return

    # ---------------------------------------------------------------------
    # MEDIA PLAYER BEHAVIORS
    # ---------------------------------------------------------------------

    async def _media_play_pause(self) -> None:
        """Toggle play/pause."""
        await self._call_entity_service("media_play_pause", {})

    async def _media_next(self) -> None:
        """Next track."""
        await self._call_entity_service("media_next_track", {})

    async def _media_volume_step(self, direction: int) -> None:
        """
        direction = +1 → volume_up
        direction = -1 → volume_down
        """
        service = "volume_up" if direction > 0 else "volume_down"
        await self._call_entity_service(service, {})

    # ---------------------------------------------------------------------
    # LIGHT BRIGHTNESS RAMPING (HOLD BEHAVIOR)
    # ---------------------------------------------------------------------

    async def _ramp_loop(self, direction: int, active_button: str) -> None:
        """Repeated brightness_step_pct while held (LIGHT ONLY)."""

        if self.conf.domain != "light":
            return

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
    # FAN SPEED LADDER (DISCRETE SPEED CONTROL)
    # ---------------------------------------------------------------------

    def _get_fan_speed_ladder(self) -> list[int]:
        speeds = getattr(self.conf, "fan_speeds", 6) or 6
        if speeds not in (4, 6):
            speeds = 6
        steps = speeds - 1
        return [round(i * 100 / steps) for i in range(speeds)]


    def _get_current_fan_percentage(self) -> Optional[float]:
        if not self.conf.entities:
            return None

        entity_id = self.conf.entities[0]
        state = self.hass.states.get(entity_id)
        if not state:
            return None

        pct = state.attributes.get("percentage")

        if pct is None:
            return 0.0 if state.state == "off" else float(self.conf.on_pct)

        try:
            return float(pct)
        except Exception:
            return None

    async def _fan_step_discrete(self, direction: int) -> None:
        if not self.conf.entities:
            return

        ladder = self._get_fan_speed_ladder()
        current_pct = self._get_current_fan_percentage()
        if current_pct is None:
            return

        current_index = min(
            range(len(ladder)),
            key=lambda i: abs(ladder[i] - current_pct),
        )
        target_index = max(
            0, min(len(ladder) - 1, current_index + direction)
        )

        target_pct = ladder[target_index]
        if target_pct == current_pct:
            return

        await self._call_entity_service(
            "set_percentage",
            {"percentage": target_pct},
        )

    # ---------------------------------------------------------------------
    # SHARED SERVICE CALLER
    # ---------------------------------------------------------------------

    async def _call_entity_service(
        self,
        service: str,
        data: Dict[str, Any],
        continue_on_error: bool = False,
    ) -> None:

        domain = self.conf.domain  # light, fan, cover, media_player
        service_data = {**data}

        if self.conf.entities:
            service_data["entity_id"] = self.conf.entities

        try:
            await self.hass.services.async_call(
                domain,
                service,
                service_data,
                blocking=True,
            )
        except Exception as err:
            msg = (
                f"Device {self.conf.device_id}: error calling "
                f"{domain}.{service}({service_data}): {err}"
            )
            if continue_on_error:
                _LOGGER.debug(msg)
            else:
                _LOGGER.error(msg)

    # ---------------------------------------------------------------------
    # FOUR-BUTTON ACTION EXECUTOR
    # ---------------------------------------------------------------------

    async def _execute_button_action(self, action: Dict[str, Any] | list) -> None:
        # ------------------------------------------------------------
        # NEW: Support lists of actions
        # ------------------------------------------------------------
        if isinstance(action, list):
            for a in action:
                await self._execute_button_action(a)
            return

        # Must be a dict from here on
        if not isinstance(action, dict):
            _LOGGER.error(
                "Device %s: invalid action format (expected dict or list): %s",
                self.conf.device_id,
                action,
            )
            return

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
                "Device %s (four_button): error calling %s.%s: %s",
                self.conf.device_id,
                domain,
                service,
                err,
            )

