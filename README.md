# Pico Connector

### A Reliable Lutron Pico → Home Assistant Light Controller

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/smartqasa/pico-connector)
![GitHub License](https://img.shields.io/github/license/smartqasa/pico-connector)

---

## 🌟 Overview

**Pico Connector** is a lightweight, reliable Home Assistant integration that
turns **Lutron Caseta Pico remotes** into powerful and responsive device
controllers.

This integration uses async tasks, requires no polling, and is extremely fast.

It listens directly to `lutron_caseta_button_event` and applies intuitive
dimming logic tailored to the three main Pico families.

---

## ✔ Paddle Pico Behavior

- **Tap ON** → sets a configurable brightness (default: 100%)
- **Tap OFF** → turns the lights off
- **Hold ON** → ramps brightness up continuously
- **Hold OFF** → ramps brightness down continuously
- Ramping automatically halts at min/max levels (typically: 0%/100%)

---

## ✔ Five Button Pico Behavior

- **ON** → immediate ON at configured brightness
- **OFF** → immediate OFF
- **STOP** → halts any active ramp
- **RAISE / LOWER** → ramps brightness while held (no hold timer)

## ✔ Two Button Pico Behavior

- **ON** → immediate ON at configured brightness
- **OFF** → immediate OFF

---

## 🚀 Installation

### 📦 HACS (Recommended)

1. Open **HACS → Integrations**
2. Click **⋮ → Custom Repositories**
3. Add:

   https://github.com/smartqasa/pico-connector

4. Choose **Integration**
5. Search for **Pico Connector** and install it
6. Restart Home Assistant

---

## 📁 Manual Installation

Copy the folder into:

config/custom_components/pico_link/

Restart Home Assistant.

---

## 🛠 Configuration (YAML)

Add one or more Pico mappings in your `configuration.yaml`:

```yaml
pico_link:
  - device_id: f00abdc1ee0fed3b5fd56b1d800154a7
    entities:
      - light.office_desk_strip
    profile: paddle # "paddle", "five_button", or "two_button"
    hold_time_ms: 250 # paddle only
    step_pct: 5 # brightness step amount
    step_time_ms: 200 # time between ramp steps
    brightness_on_pct: 100 # brightness for short ON press
```

---

## ⚙️ Options

| Key               | Required | Default | Description                         |
| ----------------- | -------- | ------- | ----------------------------------- |
| device_id         | Yes      | —       | Device ID of the Pico (from event). |
| entities          | Yes      | —       | List of light entities controlled.  |
| profile           | No       | paddle  | "paddle" or "five_button"           |
| hold_time_ms      | No       | 250     | Hold threshold (paddle only).       |
| step_pct          | No       | 5       | Brightness step size for ramping.   |
| step_time_ms      | No       | 200     | Delay between ramp steps.           |
| brightness_on_pct | No       | 100     | Brightness for short-press ON.      |

---

## 🔍 Finding Your device_id

1. Go to **Developer Tools → Events**
2. Under **Listen to events**, enter:

   lutron_caseta_button_event

3. Click **Start Listening**
4. Press any button on your Pico
5. Look for:

   device_id: abc1234567890...

Use that value in your YAML config.

---

## 🧠 Why Use Pico Connector Instead of Automations?

- More reliable long-press & ramp detection
- Perfectly consistent behavior across all Picos
- No duplicated automations or YAML complexity
- Avoids timing issues in busy HA systems
- Pure async → extremely responsive
- Logic similar to native Lutron dimmers

---

## 🤝 Contributing

Issues and PRs are welcome:

https://github.com/smartqasa/pico-connector/issues

---

## 📜 License

Licensed under the MIT License. See LICENSE for details.

---

## 🧑‍💻 Maintained By

SmartQasa – Smart Home Solutions © 2025
