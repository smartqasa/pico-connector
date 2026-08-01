from __future__ import annotations

DOMAIN = "pico_link"

# Lutron Caseta event type we listen to
PICO_EVENT_TYPE = "lutron_caseta_button_event"

# --------------------------------------------------------------------
# VALID YAML TYPES (explicitly required in device config)
# --------------------------------------------------------------------
VALID_PICO_TYPES = {
    "P2B",  # Paddle Pico
    "2B",  # Two-button on/off Pico
    "3BRL",  # Five-button raise/lower
    "4B",  # Four-button scene Pico
}

# --------------------------------------------------------------------
# MAP LUTRON RAW EVENT TYPES → OUR CONFIG TYPE CODES
#
# These must match VALID_PICO_TYPES exactly, since the controller
# uses this mapping to detect the correct profile class.
# --------------------------------------------------------------------
PICO_TYPE_MAP = {
    "PaddleSwitchPico": "P2B",
    "Pico2Button": "2B",
    "Pico3ButtonRaiseLower": "3BRL",
    "Pico4ButtonScene": "4B",
}

ON_OFF_PICO_TYPES = frozenset({"P2B", "2B"})

# --------------------------------------------------------------------
# BUTTONS EMITTED BY LUTRON CASETA
# (These are the normalized forms used throughout the controller.)
# --------------------------------------------------------------------
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

DOMAIN_ENTITY_FIELDS = {
    "cover": "covers",
    "fan": "fans",
    "light": "lights",
    "media_player": "media_players",
    "switch": "switches",
}
