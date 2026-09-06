# config_flow.py — UI configuration for Pico Link
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import selector

from .const import DOMAIN, DOMAIN_ENTITY_FIELDS, PICO_TYPE_MAP, SCENE_BUTTONS

# ================================================================
# SHARED SCHEMA BUILDERS
#
# Used by both the initial config flow and the options flow so a
# Pico's settings look and validate identically whether it is being
# created or edited.
# ================================================================


def _percent(
    min_val: int,
    max_val: int,
) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=min_val,
            max=max_val,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="%",
        )
    )


def _milliseconds() -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=100,
            max=2000,
            step=50,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="ms",
        )
    )


def _seconds() -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=300,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="s",
        )
    )


def _entities_schema(
    current: dict[str, Any] | None = None,
) -> vol.Schema:
    """
    One optional entity picker per controllable domain.

    Fill in exactly one to both pick the domain and its entities in a
    single step.
    """
    current = current or {}

    return vol.Schema(
        {
            vol.Optional(
                field,
                default=list(current.get(field, [])),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=domain,
                    multiple=True,
                )
            )
            for domain, field in DOMAIN_ENTITY_FIELDS.items()
        }
    )


def _chosen_domain(
    user_input: dict[str, Any],
) -> tuple[str, str] | None:
    """Return the (domain, field) with entities filled in, or None."""
    chosen = [
        (domain, field)
        for domain, field in DOMAIN_ENTITY_FIELDS.items()
        if user_input.get(field)
    ]

    if len(chosen) != 1:
        return None

    return chosen[0]


def _options_schema(
    domain: str,
    current: dict[str, Any] | None = None,
) -> vol.Schema:
    current = current or {}
    fields: dict[Any, Any] = {}

    if domain in ("cover", "light", "media_player"):
        fields[
            vol.Optional(
                "hold_time_ms",
                default=current.get(
                    "hold_time_ms",
                    400,
                ),
            )
        ] = _milliseconds()

        fields[
            vol.Optional(
                "step_time_ms",
                default=current.get(
                    "step_time_ms",
                    650,
                ),
            )
        ] = _milliseconds()

    if domain == "cover":
        fields[
            vol.Optional(
                "cover_open_pos",
                default=current.get(
                    "cover_open_pos",
                    100,
                ),
            )
        ] = _percent(1, 100)

        fields[
            vol.Optional(
                "cover_step_pct",
                default=current.get(
                    "cover_step_pct",
                    10,
                ),
            )
        ] = _percent(1, 25)

        fields[
            vol.Optional(
                "cover_inverted",
                default=current.get(
                    "cover_inverted",
                    False,
                ),
            )
        ] = selector.BooleanSelector()

    elif domain == "fan":
        fields[
            vol.Optional(
                "fan_on_pct",
                default=current.get(
                    "fan_on_pct",
                    100,
                ),
            )
        ] = _percent(1, 100)

    elif domain == "light":
        fields[
            vol.Optional(
                "light_on_pct",
                default=current.get(
                    "light_on_pct",
                    100,
                ),
            )
        ] = _percent(1, 100)

        fields[
            vol.Optional(
                "light_low_pct",
                default=current.get(
                    "light_low_pct",
                    5,
                ),
            )
        ] = _percent(1, 99)

        fields[
            vol.Optional(
                "light_step_pct",
                default=current.get(
                    "light_step_pct",
                    10,
                ),
            )
        ] = _percent(1, 25)

        fields[
            vol.Optional(
                "light_transition_on",
                default=current.get(
                    "light_transition_on",
                    0,
                ),
            )
        ] = _seconds()

        fields[
            vol.Optional(
                "light_transition_off",
                default=current.get(
                    "light_transition_off",
                    0,
                ),
            )
        ] = _seconds()

    elif domain == "media_player":
        fields[
            vol.Optional(
                "media_player_vol_step",
                default=current.get(
                    "media_player_vol_step",
                    10,
                ),
            )
        ] = _percent(1, 20)

    return vol.Schema(fields)


def _middle_button_schema(
    current: list[dict[str, Any]] | None = None,
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                "middle_button",
                default=list(current or []),
            ): selector.ActionSelector(),
        }
    )


def _buttons_schema(
    current: dict[str, list[dict[str, Any]]] | None = None,
) -> vol.Schema:
    current = current or {}

    return vol.Schema(
        {
            vol.Optional(
                name,
                default=list(current.get(name, [])),
            ): selector.ActionSelector()
            for name in SCENE_BUTTONS
        }
    )


def _eligible_pico_devices(
    hass: Any,
) -> dict[str, tuple[str, str]]:
    """
    Find Lutron Pico remotes that aren't already configured.

    Returns {device_id: (display_name, pico_type)}. The Pico type is
    read directly from the model Lutron reports, so it never needs to
    be entered by hand and can never disagree with the hardware.
    """
    device_registry = dr.async_get(hass)

    lutron_entry_ids = {
        entry.entry_id for entry in hass.config_entries.async_entries("lutron_caseta")
    }

    configured_device_ids = {
        entry.data.get("device_id") for entry in hass.config_entries.async_entries(DOMAIN)
    }

    devices: dict[str, tuple[str, str]] = {}

    for device in device_registry.devices.values():
        if not device.config_entries & lutron_entry_ids:
            continue

        if device.id in configured_device_ids:
            continue

        model = device.model or ""
        pico_type = next(
            (code for raw, code in PICO_TYPE_MAP.items() if raw in model),
            None,
        )

        if pico_type is None:
            # Not a Pico (e.g. the Smart Bridge or a Fan Speed Controller).
            continue

        devices[device.id] = (
            device.name_by_user or device.name or device.id,
            pico_type,
        )

    return devices


# ================================================================
# CONFIG FLOW (add a new Pico)
# ================================================================


class PicoLinkConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    """Handle adding a single Pico as a config entry."""

    VERSION = 1

    def __init__(self) -> None:
        self._device_id: str | None = None
        self._type: str | None = None
        self._domain: str = ""
        self._title: str = ""
        self._options: dict[str, Any] = {}

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        devices = _eligible_pico_devices(self.hass)

        if not devices:
            return self.async_abort(reason="no_devices_found")

        if user_input is not None:
            device_id = user_input["device_id"]

            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured()

            self._device_id = device_id
            self._title, self._type = devices[device_id]

            if self._type == "4B":
                return await self.async_step_buttons()

            return await self.async_step_entities()

        schema = vol.Schema(
            {
                vol.Required("device_id"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=device_id,
                                label=title,
                            )
                            for device_id, (title, _type) in sorted(
                                devices.items(),
                                key=lambda item: item[1][0],
                            )
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
        )

    async def async_step_entities(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            chosen = _chosen_domain(user_input)

            if chosen is None:
                errors["base"] = "single_domain_required"
            else:
                domain, field = chosen
                self._domain = domain
                self._options = {field: user_input[field]}
                return self._async_finish()

        return self.async_show_form(
            step_id="entities",
            data_schema=_entities_schema(),
            errors=errors,
        )

    async def async_step_buttons(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            buttons = {
                name: actions for name, actions in user_input.items() if actions
            }

            if not buttons:
                errors["base"] = "buttons_required"
            else:
                self._options["buttons"] = buttons
                return self._async_finish()

        return self.async_show_form(
            step_id="buttons",
            data_schema=_buttons_schema(),
            errors=errors,
        )

    def _async_finish(self) -> FlowResult:
        return self.async_create_entry(
            title=self._title,
            data={
                "device_id": self._device_id,
                "type": self._type,
            },
            options=self._options,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "PicoLinkOptionsFlow":
        return PicoLinkOptionsFlow(config_entry)


# ================================================================
# OPTIONS FLOW (edit an existing Pico)
#
# Editing still exposes the timing/behavior options and the 3BRL STOP
# button, which the initial add flow skips in favor of sensible
# defaults.
# ================================================================


class PicoLinkOptionsFlow(config_entries.OptionsFlow):
    """Handle editing an existing Pico's entities, buttons, and options."""

    def __init__(
        self,
        config_entry: config_entries.ConfigEntry,
    ) -> None:
        self._entry = config_entry
        self._type: str = config_entry.data["type"]
        self._domain: str = ""
        self._options: dict[str, Any] = dict(config_entry.options)

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        if self._type == "4B":
            return await self.async_step_buttons()

        return await self.async_step_entities()

    async def async_step_entities(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            chosen = _chosen_domain(user_input)

            if chosen is None:
                errors["base"] = "single_domain_required"
            else:
                domain, field = chosen

                # Drop any other domain's entities if the domain changed.
                for other_field in DOMAIN_ENTITY_FIELDS.values():
                    if other_field != field:
                        self._options.pop(other_field, None)

                self._domain = domain
                self._options[field] = user_input[field]
                return await self.async_step_options()

        return self.async_show_form(
            step_id="entities",
            data_schema=_entities_schema(current=self._options),
            errors=errors,
        )

    async def async_step_options(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        if user_input is not None:
            self._options.update(user_input)

            if self._type == "3BRL":
                return await self.async_step_middle_button()

            return self._async_finish()

        return self.async_show_form(
            step_id="options",
            data_schema=_options_schema(
                self._domain,
                current=self._options,
            ),
            description_placeholders={"domain": self._domain},
        )

    async def async_step_middle_button(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        if user_input is not None:
            self._options["middle_button"] = user_input.get(
                "middle_button",
                [],
            )
            return self._async_finish()

        return self.async_show_form(
            step_id="middle_button",
            data_schema=_middle_button_schema(
                current=self._options.get("middle_button"),
            ),
        )

    async def async_step_buttons(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            buttons = {
                name: actions for name, actions in user_input.items() if actions
            }

            if not buttons:
                errors["base"] = "buttons_required"
            else:
                self._options["buttons"] = buttons
                return self._async_finish()

        return self.async_show_form(
            step_id="buttons",
            data_schema=_buttons_schema(
                current=self._options.get("buttons"),
            ),
            errors=errors,
        )

    def _async_finish(self) -> FlowResult:
        return self.async_create_entry(
            title="",
            data=self._options,
        )
