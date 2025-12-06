# Pico Link

### A Reliable Lutron Pico → Home Assistant Device Controller

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/smartqasa/pico-link)
![GitHub License](https://img.shields.io/github/license/smartqasa/pico-link)

---

## 🌟 Overview

**Pico Link** is a lightweight, ultra-responsive Home Assistant integration that
turns  
**Lutron Caseta Pico remotes**—including the **new paddle Pico**—into fully
featured and reliable device controllers.

Pico Link listens directly to:

```
lutron_caseta_button_event
```

and produces **fast, predictable, zero-lag button behavior** using async
lifecycles with hold detection, ramping, and tap logic.

Supported Pico types:

- 5-Button Pico
- 4-Button “Scene” Pico
- 2-Button Pico
- Paddle Pico

All behavior is profile-specific and tuned to perform like native Lutron dimmers
whenever possible.

---

## 🚀 Installation

### 📦 HACS (Recommended)

1. Go to **HACS → Integrations**
2. Click **⋮ → Custom Repositories**
3. Add:

   ```
   https://github.com/smartqasa/pico-link
   ```

4. Select **Integration**
5. Search for **Pico Link** and install it
6. Restart Home Assistant

---

## 📁 Manual Installation

Copy the `pico_link/` folder into:

```
config/custom_components/pico_link/
```

Restart Home Assistant.

---

## ⚙️ Configuration Structure

Pico Link now supports **global defaults** plus a device list:

```yaml
pico_link:
  defaults:
    hold_time_ms: 300
    step_pct: 5
    step_time_ms: 200
    on_pct: 100
    low_pct: 1
    middle_button:
      - action: light.turn_on
        data:
          brightness_pct: 40

  devices:
    - device_id: 111aaa...
      profile: paddle
      domain: light
      entities:
        - light.kitchen

    - device_id: 222bbb...
      profile: five_button
      domain: light
      entities:
        - light.table_lamp
```

### ✔ How Defaults Work

1. **Hardcoded class defaults**
2. **Global defaults**
3. **Per-device overrides** win

### ✔ Middle Button Default Target Injection

If a 5-button Pico inherits a `middle_button:` action from defaults  
and the action does **not** specify `target:`, Pico Link automatically injects:

```yaml
target:
  entity_id: <device entities>
```

Device-level definitions always override defaults.

---

## 🧩 Pico Profiles & Behavior

Each Pico model uses a dedicated behavior profile.

---

## ✔ Paddle Pico Behavior

- **Tap ON** → turn on to `on_pct` brightness
- **Tap OFF** → turn off
- **Hold ON** → smoothly ramp brightness up
- **Hold OFF** → smoothly ramp brightness down
- Ramping stops:
  - at brightness limits (0 / 255)
  - at configured `low_pct` minimum
  - when the button is released

---

## ✔ Five Button Pico Behavior

Buttons:

- **ON** → immediate on (`on_pct`)
- **OFF** → immediate off
- **STOP (middle)**
  - Executes configured `middle_button:` actions
  - If none given and `domain == cover` → stop_cover
- **RAISE / LOWER**
  - One immediate brightness step
  - Hold detection after `hold_time_ms`
  - Continuous ramp until:
    - release
    - min/max brightness reached
    - low-pct boundary reached

---

## ✔ Four Button Pico Behavior

4-button Picos generate:

| Button       | `button_type` |
| ------------ | ------------- |
| Top          | `button_1`    |
| Upper-Middle | `button_2`    |
| Lower-Middle | `button_3`    |
| Bottom       | `off`         |

Behavior:

- No hold detection
- No ramping
- No brightness stepping
- Every press triggers its configured **list of actions**

```yaml
buttons:
  button_1:
    - action: scene.turn_on
      target:
        entity_id: scene.movie
```

---

## ✔ Two Button Pico Behavior

Simple, reliable:

- ON → turn on (`on_pct`)
- OFF → turn off

No ramping, no holds.

---

## 🔍 Finding Your `device_id`

1. Go to **Developer Tools → Events**
2. Under _Listen to events_, enter:

```
lutron_caseta_button_event
```

3. Click **Start Listening**
4. Press buttons on the Pico
5. Look for:

```
device_id: 1234567890abcdef...
```

Use this in your config.

---

## 🛠 Full Configuration Example

```yaml
pico_link:
  defaults:
    hold_time_ms: 300
    step_pct: 5
    step_time_ms: 200
    on_pct: 100
    low_pct: 1
    middle_button:
      - action: light.turn_on
        data:
          brightness_pct: 40

  devices:
    - device_id: abc111...
      profile: paddle
      domain: light
      entities:
        - light.kitchen_main

    - device_id: def222...
      profile: five_button
      domain: light
      entities:
        - light.living_room

    - device_id: ghi333...
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

---

## 🧠 Why Pico Link?

- Ultra-fast async handling
- Reliable long-press detection
- Behavior matches real Lutron dimmers
- No automations to maintain
- Centralized configuration
- Works with any number of lights, fans, media players, covers

---

## 🤝 Contributing

PRs and issues welcome:

https://github.com/smartqasa/pico-link/issues

---

## 📜 License

MIT License — see LICENSE for details.

---

## 🧑‍💻 Maintained By

**SmartQasa – Smart Home Solutions © 2025**
