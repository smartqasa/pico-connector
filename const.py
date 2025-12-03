from __future__ import annotations

DOMAIN = "pico_connector"

# Lutron Caseta event type we listen to
PICO_EVENT_TYPE = "lutron_caseta_button_event"

# Profiles
PROFILE_PADDLE = "paddle"
PROFILE_FIVE_BUTTON = "five_button"

# Logical button names we care about
SUPPORTED_BUTTONS = ("on", "off", "raise", "lower", "stop")
