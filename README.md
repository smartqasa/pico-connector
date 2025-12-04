# Pico Link

### A Reliable Lutron Pico → Home Assistant Device Controller

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/smartqasa/pico-link)
![GitHub License](https://img.shields.io/github/license/smartqasa/pico-link)

---

## 🌟 Overview

**Pico Link** is a lightweight, reliable Home Assistant integration that turns
**Lutron Caseta Pico remotes** into powerful and responsive device controllers.

Support Picos include: classic 5, 4, and 2 button models and the newer paddle
pico.

This integration uses async tasks, requires no polling, and is extremely fast.

It listens directly to `lutron_caseta_button_event` and applies intuitive
dimming logic tailored to the three main Pico families.

---

## 🚀 Installation

### 📦 HACS (Recommended)

1. Open **HACS → Integrations**
2. Click **⋮ → Custom Repositories**
3. Add:

   https://github.com/smartqasa/pico-link

4. Choose **Integration**
5. Search for **Pico Link** and install it
6. Restart Home Assistant

---

## 📁 Manual Installation

Copy the folder into:

config/custom_components/pico_link/

Restart Home Assistant.

---

## ✔ Five Button Pico Behavior

- **ON** → immediate ON at configured brightness
- **OFF** → immediate OFF
- **STOP** → halts any active ramp
- **RAISE / LOWER** → ramps brightness while held (no hold timer)

---

## ✔ Four Button Pico Behavior

Some Pico models provide **four independent buttons**, reporting the following  
`button_type` values:

| Physical Button | `button_type` |
| --------------- | ------------- |
| Top button      | `button_1`    |
| Upper-middle    | `button_2`    |
| Lower-middle    | `button_3`    |
| Bottom button   | `off`         |

The 4-button Pico does **not** support dimming, holding, or ramping.  
Instead, **each button can trigger one or more Home Assistant actions**.

### Behavior

- No long-press
- No ramping
- No brightness stepping
- Each button executes its own action list on **press**

## ✔ Two Button Pico Behavior

- **ON** → immediate ON at configured brightness
- **OFF** → immediate OFF

---

## ✔ Paddle Pico Behavior

- **Tap ON** → sets a configurable brightness (default: 100%)
- **Tap OFF** → turns the lights off
- **Hold ON** → ramps brightness up continuously
- **Hold OFF** → ramps brightness down continuously
- Ramping automatically halts at min/max levels (typically: 0%/100%)

---

## 🛠 Configuration (YAML)

Add one or more Pico mappings in your `configuration.yaml`:

## ⚙️ Options

| Key          | Required | Default | Description                         |
| ------------ | -------- | ------- | ----------------------------------- |
| device_id    | Yes      | —       | Device ID of the Pico (from event). |
| class        | Yes      | light   | Class of the entities controlled.   |
| entities     | Yes      | —       | List of light entities controlled.  |
| profile      | No       | paddle  | "paddle" or "five_button"           |
| hold_time_ms | No       | 250     | Hold threshold (paddle only).       |
| step_pct     | No       | 5       | Brightness step size for ramping.   |
| step_time_ms | No       | 200     | Delay between ramp steps.           |
| on_pct       | No       | 100     | Brightness for short-press ON.      |

```yaml
pico_link:
  - device_id: abc123... (see below for how to locate)
    profile: paddle # "paddle", "five_button", or "two_button"
    hold_time_ms: 250 # paddle only
    step_pct: 5 # paddle and 5 button only - brightness step amount
    step_time_ms: 200 # paddle and 5 button only - time between ramp steps
    on_pct: 100 # initial percentage for on button tap
    class: light # "light", "fan", or "shade (cover)", "garage (cover)
    entities:
      - light.bedroom_color_lights

  - device_id: abc123...
    profile: four_button
    buttons:
      button_1:
        - action: scene.turn_on
          target:
            entity_id: scene.chill_out

      button_2:
        - action: light.turn_on
          target:
            entity_id: light.kitchen
          data:
            brightness_pct: 25

      button_3:
        - action: script.evening_mode

      off:
        - action: homeassistant.turn_off
          target:
            area_id: living_room
```

## 🔍 Finding Your device_id

1. Go to **Developer Tools → Events**
2. Under **Listen to events**, enter:

   lutron_caseta_button_event

3. Click **Start Listening**
4. Press any button on your Pico
5. Look for:

   device_id: abc1234567890... (32 characters)

Use that value in your YAML config.

---

## 🧠 Why Use Pico Link Instead of Automations?

- More reliable long-press & ramp detection
- Perfectly consistent behavior across all Picos
- No duplicated automations or YAML complexity
- Avoids timing issues in busy HA systems
- Pure async → extremely responsive
- Logic similar to native Lutron dimmers

---

## 🤝 Contributing

Issues and PRs are welcome:

https://github.com/smartqasa/pico-link/issues

---

## 📜 License

Licensed under the MIT License. See LICENSE for details.

---

## 🧑‍💻 Maintained By

SmartQasa – Smart Home Solutions © 2025
