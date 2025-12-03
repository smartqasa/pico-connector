# Pico Connector

### A Reliable Lutron Pico → Home Assistant Light Controller

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)  
![GitHub release (latest by date)](https://img.shields.io/github/v/release/smartqasa/pico-connector)  
![GitHub License](https://img.shields.io/github/license/smartqasa/pico-connector)

---

## 🌟 Overview

**Pico Connector** is a lightweight, reliable, non-polling Home Assistant
integration that turns **Lutron Caseta Pico remotes** into powerful light
controllers.

It listens directly to `lutron_caseta_button_event` and applies intuitive
dimming behavior:

### ✔ Paddle Pico Behavior

- **Short Press ON** → Sets configurable brightness (default: 100%)
- **Short Press OFF** → Turns off
- **Long Press ON** → Ramps up brightness
- **Long Press OFF** → Ramps down brightness
- Automatically stops when max/min brightness is reached

### ✔ 5-Button Pico Behavior (Pico3RaiseLower & true 5-button models)

- **ON** → immediate brightness_on_pct
- **OFF** → immediate off
- **STOP** → halts ramping
- **RAISE / LOWER** → ramps immediately (no hold timer)

This integration requires **no polling**, uses **async**, and is extremely
responsive.

---

## 🚀 Installation

### 📦 HACS (Recommended)

1. Go to **HACS → Integrations**
2. Click **⋮ → Custom Repositories**
3. Add repository URL: https://github.com/smartqasa/pico-connector
4. Choose **Integration**
5. Search for **Pico Connector** in HACS and install
6. Restart Home Assistant

---

## 📁 Manual Installation

Copy this folder into your Home Assistant configuration:
config/custom_components/pico_connector/

Restart Home Assistant.

---

## 🛠 Configuration (YAML)

Add one or more Pico mappings in `configuration.yaml`:

```yaml
pico_connector:
  - device_id: f00abdc1ee0fed3b5fd56b1d800154a7
    entities:
      - light.office_desk_strip
    profile: paddle # "paddle" or "five_button"
    hold_time_ms: 250 # only for paddle
    step_pct: 5 # ramp amount per step
    step_time_ms: 200 # time between steps
    brightness_on_pct: 100 # ON button brightness
```

| Key                 | Required | Default  | Description                            |
| ------------------- | -------- | -------- | -------------------------------------- |
| `pico_device_id`    | Yes      | —        | Device ID of the Pico (from event).    |
| `entities`          | Yes      | —        | List of lights controlled.             |
| `profile`           | No       | `paddle` | `"paddle"` or `"five_button"`          |
| `hold_time_ms`      | No       | 250      | Press vs hold threshold (paddle only). |
| `step_pct`          | No       | 5        | Brightness step for ramping.           |
| `step_time_ms`      | No       | 200      | Delay between ramp steps.              |
| `brightness_on_pct` | No       | 100      | Short ON press brightness.             |

🔍 Finding Your pico_device_id

Go to Developer Tools → Events

Under Listen to events, enter:

lutron_caseta_button_event

Press “Start Listening”

Press any button on the Pico

Find the field:

device_id: abc1234567890...

Paste that into your YAML config.

🧠 Why Not Use Automations Instead?

This integration solves issues that YAML automations struggle with:

Reliable long-press detection

Consistent ramping logic across all entities

No duplicated automations needed for each Pico

No delay issues seen in large HA installs

Async tasks per button → very fast & responsive

You get rock-solid behavior similar to a native Lutron dimmer.

🤝 Contributing

PRs and issues are welcome:

👉 https://github.com/smartqasa/pico-connector/issues

📜 License

Licensed under the MIT License. See LICENSE for details.

🧑‍💻 Maintained by

SmartQasa – Smart Home Solutions © 2025
