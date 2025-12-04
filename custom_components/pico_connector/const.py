from __future__ import annotations

DOMAIN = "pico_connector"

# Lutron Caseta event type we listen to
PICO_EVENT_TYPE = "lutron_caseta_button_event"

# Profiles
PROFILE_FIVE_BUTTON = "five_button"
PROFILE_PADDLE = "paddle"
PROFILE_TWO_BUTTON = "two_button"

# Logical button names we care about
SUPPORTED_BUTTONS_PADDLE = ("on", "off")
SUPPORTED_BUTTONS_FIVE = ("on", "off", "raise", "lower", "stop")
SUPPORTED_BUTTONS_TWO = ("on", "off")

PROFILE_SUPPORTED_BUTTONS = {
    PROFILE_PADDLE: SUPPORTED_BUTTONS_PADDLE,
    PROFILE_FIVE_BUTTON: SUPPORTED_BUTTONS_FIVE,
    PROFILE_TWO_BUTTON: SUPPORTED_BUTTONS_TWO,
}

