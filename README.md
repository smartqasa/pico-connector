# 🌟 **Pico Link**

### _A Universal Lutron Pico → Home Assistant Device Controller_

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/smartqasa/pico-link)
![GitHub License](https://img.shields.io/github/license/smartqasa/pico-link)

<p align="center">
  <img src="logo.png" width="180" alt="Pico Link Logo">
</p>

---

## 🧠 What Is Pico Link?

**Pico Link** turns any **Lutron Caséta Pico Remote** — including the new **P2B
paddle Pico** — into a fully programmable controller for Home Assistant.

Pico Link listens directly to:

```
lutron_caseta_button_event
```

and provides:

- Tap and hold detection
- Step and ramp logic
- Per-domain action handling
- 4-button scene execution
- Middle-button (STOP) behavior that adapts to your domain
- Placeholder expansion for 3BRL custom actions
- Full validation of configuration

### Supported Pico models

- **P2B** — Paddle
- **2B** — Two Button
- **3BRL** — On / Raise / Lower / Off / Stop
- **4B** — Scene Pico

---

# 🚀 Installation

## 📦 Install via HACS (Recommended)

1. Go to **HACS → Integrations**
2. Click **⋮ → Custom Repositories**
3. Add:

```
https://github.com/smartqasa/pico-link
```

4. Select **Integration**
5. Search for **Pico Link** and install
6. Restart Home Assistant

## 📁 Manual Installation

Copy this folder into:

```
config/custom_components/pico_link/
```

Restart Home Assistant.

---

# ⚙️ Configuration Overview

You configure Pico Link under:

```yaml
pico_link:
  defaults: …
  devices: …
```

### Every device must specify:

- A Pico **type**
- A **device_id** or **name**
- **Exactly one** domain (except 4B)
- Optional behavior settings
- Optional defaults inherited from the global `defaults:` block

---

# 🔧 Valid Domains

Each non-4B Pico must control **exactly one**:

```
lights:
fans:
covers:
media_players:
switches:
```

A Pico cannot control two domains at once.

4B Picos do **not** require a domain.

---

# 📊 Configuration Parameters

| Parameter                                                   | Required?                | Default | Description                     |
| ----------------------------------------------------------- | ------------------------ | ------- | ------------------------------- |
| `type`                                                      | ✔                       | —       | `P2B`, `2B`, `3BRL`, `4B`       |
| `name` / `device_id`                                        | ✔                       | —       | Identify the Pico in HA         |
| `lights` / `fans` / `covers` / `switches` / `media_players` | One required (except 4B) | —       | Domain linkage                  |
| `middle_button`                                             | 3BRL only                | `[]`    | Overrides default STOP behavior |
| `buttons`                                                   | 4B only                  | `{}`    | Scene/action mappings           |
| `hold_time_ms`                                              | optional                 | 250     | Hold detection threshold        |
| `step_time_ms`                                              | optional                 | 750     | Ramp interval                   |
| `cover_open_pos`                                            | optional                 | 100     | Target position for ON          |
| `cover_step_pct`                                            | optional                 | 10      | Raise/lower step size           |
| `fan_on_pct`                                                | optional                 | 100     | ON speed                        |
| `fan_speeds`                                                | optional                 | 6       | Valid: 4 or 6                   |
| `light_on_pct`                                              | optional                 | 100     | Brightness for ON               |
| `light_low_pct`                                             | optional                 | 1       | Min dimming level               |
| `light_step_pct`                                            | optional                 | 10      | Dimming step                    |
| `media_player_vol_step`                                     | optional                 | 10      | Volume step (1–20)              |

---

# 🔍 Button Behavior (Unified Across All Picos)

## 💡 **Lights**

- ON → turn on to `light_on_pct`
- OFF → turn off
- RAISE → tap=step, hold=ramp up
- LOWER → tap=step, hold=ramp down
- STOP → **no-op** unless overridden via `middle_button`

## 🌀 **Fans**

- ON → set percentage to `fan_on_pct`
- OFF → turn_off
- RAISE/LOWER → tap=step, hold=ramp
- STOP → **reverse direction**

## 🪟 **Covers**

- ON → open or move to `cover_open_pos`
- OFF → close
- RAISE/LOWER → step or ramp position
- STOP → **stop_cover**

## 🎵 **Media Players**

- ON → turn_on + unmute
- OFF → turn_off + mute
- RAISE/LOWER → step/ramp volume
- STOP → **play/pause toggle** (unless overridden)

## 🔌 **Switches**

- ON → turn_on
- OFF → turn_off
- RAISE, LOWER, STOP → no-op

---

# 📘 Pico Behavior By Type

| Pico Type | Buttons                 | Hold? | STOP behavior                        |
| --------- | ----------------------- | ----- | ------------------------------------ |
| **P2B**   | on/off                  | yes   | per-domain STOP                      |
| **2B**    | on/off                  | no    | no STOP                              |
| **3BRL**  | on/raise/lower/off/stop | yes   | STOP = domain default (or overrides) |
| **4B**    | 4 scene buttons         | no    | no STOP; uses `buttons:`             |

---

# 🚦 Defaults: How They Work

The `defaults:` block applies to **all devices**, unless overridden.

Example:

```yaml
pico_link:
  defaults:
    hold_time_ms: 300
    step_time_ms: 500
    light_on_pct: 75
    middle_button:
      - action: light.turn_on
        target:
          entity_id: lights
        data:
          brightness_pct: 85

  devices:
    - name: Living Room Pico
      type: 3BRL
      lights:
        - light.living_room
      middle_button: default # inherits from defaults
```

If a device overrides a value:

```yaml
hold_time_ms: 150
```

that device uses its own value; all others use the default.

4B scenes do **not** inherit defaults.

---

# 📁 Example Configurations

## ✔ P2B (Paddle Pico controlling lights)

```yaml
pico_link:
  devices:
    - device_id: 1551fa9867f7b1e58790823d6b92d911
      type: P2B
      lights:
        - light.bedroom_lights
```

---

## ✔ 2B (simple switch controller)

```yaml
pico_link:
  devices:
    - name: Bedside Pico
      type: 2B
      switches:
        - switch.bedside_lamp
```

---

## ✔ 3BRL with defaults + override

```yaml
pico_link:
  defaults:
    light_step_pct: 15
    hold_time_ms: 300
    middle_button:
      - action: light.turn_on
        target:
          entity_id: lights
        data:
          brightness_pct: 50

  devices:
    - name: Living Room
      type: 3BRL
      lights:
        - light.living_room
      middle_button: default # uses the default middle-button actions

    - name: Dining Room
      type: 3BRL
      lights:
        - light.dining_room
      middle_button:
        - action: light.turn_on
          target:
            entity_id: light.dining_room
          data:
            brightness_pct: 40
```

---

## ✔ 4B Scene Pico

```yaml
pico_link:
  devices:
    - name: Scene Controller
      type: 4B
      buttons:
        button_1:
          - action: scene.turn_on
            target: { entity_id: scene.movie }
        button_2:
          - action: script.dim_lights
        button_3:
          - action: light.turn_off
            target: { entity_id: light.kitchen }
        off:
          - action: homeassistant.turn_off
            target: { area_id: living_room }
```

---

# 🧩 Placeholder Expansion (3BRL only)

Inside `middle_button:`, you may reference **device-level entity lists**:

| Placeholder     | Expands To                       |
| --------------- | -------------------------------- |
| `lights`        | the lights assigned to this Pico |
| `fans`          | assigned fans                    |
| `covers`        | assigned covers                  |
| `media_players` | assigned media players           |
| `switches`      | assigned switches                |

Example:

```yaml
middle_button:
  - action: light.turn_on
    target:
      entity_id:
        - lights
        - light.extra_lamp
```

---

# 🔍 Validation Rules

Pico Link enforces:

- ✔ Exactly **one** domain per Pico (except 4B)
- ✔ Pico type must be valid
- ✔ `fan_speeds` must be **4 or 6**
- ✔ `buttons:` must be valid for 4B
- ✔ `middle_button` only valid for 3BRL
- ✔ All numeric settings must fall within safe ranges

If validation fails, HA reports a meaningful configuration error.

---

# ☕ Support Development ❤️

<a href="https://buymeacoffee.com/smartqasa" target="_blank">
  <img src="https://www.buymeacoffee.com/assets/img/custom_images/yellow_img.png" height="60">
</a>
