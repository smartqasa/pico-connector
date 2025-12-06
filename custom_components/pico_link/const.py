from __future__ import annotations

DOMAIN = "pico_link"

# Lutron Caseta event type we listen to
PICO_EVENT_TYPE = "lutron_caseta_button_event"

# Map Lutron's event "type" → internal logical category
PICO_TYPE_MAP = {
    "Pico3ButtonRaiseLower": "five_button",
    "Pico4ButtonScene":      "four_button",
    "PaddleSwitchPico":      "paddle",
    "Pico2Button":           "two_button",
}

# Buttons emitted in Lutron events
SUPPORTED_BUTTONS = [
    "button_1",
    "button_2",
    "button_3",
    "lower",
    "off",
    "on",
    "raise",
    "stop",
]
