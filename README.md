# 🌟 **Pico Link**

### _A Universal Lutron Pico → Home Assistant Device Controller_

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/smartqasa/pico-link)
![GitHub License](https://img.shields.io/github/license/smartqasa/pico-link)

<p align="center">
  <img src="logo.png" width="180" alt="Pico Link Logo">
</p>

---

# 🧠 Overview

**Pico Link** transforms any **Lutron Caséta Pico Remote** — including the **P2B
Paddle Pico** — into a powerful, domain-aware controller for Home Assistant.

It listens directly to:

```
lutron_caseta_button_event
```

and provides:

- Tap vs hold detection
- Step and ramp behavior
- Domain-specific logic (lights, fans, covers, media, switches)
- STOP behavior per domain (3BRL)
- Scene execution for 4-button Picos
- Placeholder expansion for `middle_button:`
- Strong configuration validation

No automations needed — just use your Pico like a native controller.

---

# 🧭 Pico Types at a Glance

| Pico Type | Layout                          | Exposed Buttons                           | Hold Support | STOP?             | Typical Use                 | Notes                                       |
| --------- | ------------------------------- | ----------------------------------------- | ------------ | ----------------- | --------------------------- | ------------------------------------------- |
| **P2B**   | Paddle ON/OFF                   | `on`, `off`                               | ✔ Yes       | Logical STOP only | Lights, fans, covers, media | Hold mapped internally to raise/lower logic |
| **2B**    | Small ON/OFF                    | `on`, `off`                               | ✘ No         | ✘ No              | Simple switches             | Tap-only                                    |
| **3BRL**  | On / Raise / Lower / Off / Stop | `on`, `raise`, `lower`, `off`, `stop`     | ✔ Yes       | ✔ Yes            | Full device control         | STOP uses domain defaults or overrides      |
| **4B**    | 4 Scenes                        | `button_1`, `button_2`, `button_3`, `off` | ✘ No         | ✘ No              | Scenes/scripts              | No domain control                           |

---

# 🚀 Installation

## 📦 Install via HACS (recommended)

1. Open **HACS → Integrations**
2. Click **⋮ → Custom Repositories**
3. Add:

```
https://github.com/smartqasa/pico-link
```

4. Choose **Integration**
5. Install **Pico Link**
6. Restart Home Assistant

## 📁 Manual Installation

Copy into:

```
config/custom_components/pico_link/
```

Restart HA.

---

# ⚙️ Configuration Overview

You configure Pico Link under:

```yaml
pico_link:
  defaults: …
  devices: …
```

Each Pico **must** define:

- `type:`
- `device_id:` or `name:`
- One domain (except 4B)

Valid domains:

```
lights:
fans:
covers:
media_players:
switches:
```

4B uses `buttons:` instead.

---

# 📊 Configuration Parameters

| Field                   | Required     | Default | Description                |
| ----------------------- | ------------ | ------- | -------------------------- |
| `type`                  | ✔           | —       | Pico hardware type         |
| `name` / `device_id`    | ✔           | —       | Identify Pico              |
| Domain (`lights` etc.)  | ✔ except 4B | —       | Target domain              |
| `buttons`               | 4B only      | `{}`    | Scene/action mappings      |
| `middle_button`         | 3BRL only    | `[]`    | STOP overrides             |
| `hold_time_ms`          | optional     | 250     | Hold threshold             |
| `step_time_ms`          | optional     | 750     | Ramp interval              |
| `cover_open_pos`        | optional     | 100     | ON → open to this position |
| `cover_step_pct`        | optional     | 10      | Raise/lower step           |
| `fan_on_pct`            | optional     | 100     | ON fan speed               |
| `fan_speeds`            | optional     | 6       | Allowed: 4 or 6            |
| `light_on_pct`          | optional     | 100     | Brightness for ON          |
| `light_low_pct`         | optional     | 1       | Min dim level              |
| `light_step_pct`        | optional     | 10      | Step size                  |
| `media_player_vol_step` | optional     | 10      | Volume step size           |

---

# 🎮 Domain Behavior Summary

## 💡 Lights

| Button | Behavior                  |
| ------ | ------------------------- |
| ON     | turn_on → `light_on_pct`  |
| OFF    | turn_off                  |
| RAISE  | step or ramp up           |
| LOWER  | step or ramp down         |
| STOP   | no-op (unless overridden) |

---

## 🌀 Fans

| Button | Behavior                      |
| ------ | ----------------------------- |
| ON     | set_percentage → `fan_on_pct` |
| OFF    | turn_off                      |
| RAISE  | step/ramp up                  |
| LOWER  | step/ramp down                |
| STOP   | reverse_direction             |

---

## 🪟 Covers

| Button | Behavior                      |
| ------ | ----------------------------- |
| ON     | open / go to `cover_open_pos` |
| OFF    | close                         |
| RAISE  | step/ramp open                |
| LOWER  | step/ramp close               |
| STOP   | stop_cover                    |

---

## 🎵 Media Players

| Button   | Behavior                 |
| -------- | ------------------------ |
| ON       | turn_on + unmute         |
| OFF      | turn_off + mute          |
| RAISE    | step/ramp volume up      |
| LOWER    | step/ramp volume down    |
| **STOP** | **toggle mute / unmute** |

---

## 🔌 Switches

| Button               | Behavior |
| -------------------- | -------- |
| ON                   | turn_on  |
| OFF                  | turn_off |
| RAISE / LOWER / STOP | no-op    |

---

# 🔁 How Defaults Work

You can define global defaults:

```yaml
pico_link:
  defaults:
    hold_time_ms: 300
    light_step_pct: 12
```

Any device may:

- Inherit defaults
- Override specific values
- Override or accept default STOP logic (3BRL)

### Using a default middle_button

```yaml
pico_link:
  defaults:
    middle_button:
      - action: light.turn_on
        target:
          entity_id: lights
        data:
          brightness_pct: 80

  devices:
    - name: Living Room Pico
      type: 3BRL
      lights:
        - light.living_room
      middle_button: default
```

---

# 🧩 Placeholder Expansion (3BRL Only)

Inside `middle_button:` you may use:

| Placeholder     | Expands To              |
| --------------- | ----------------------- |
| `lights`        | the device's light list |
| `fans`          | assigned fans           |
| `covers`        | assigned covers         |
| `media_players` | assigned media players  |
| `switches`      | assigned switches       |

Example:

```yaml
entity_id:
  - lights
  - light.extra_lamp
```

---

# 🛡 Validation Rules

Pico Link enforces:

- One domain per device (except 4B)
- Valid Pico type
- Valid fan speed count (`4` or `6`)
- Correct middle_button usage
- Valid 4B button mappings
- Numeric ranges validated

If anything is invalid, Home Assistant raises a clear configuration error.

---

# 📘 Full Configuration Example

Below is a complete configuration demonstrating all device types, defaults,
overrides, placeholder expansion, and typical use cases.

```yaml
pico_link:
  # ------------------------------------------------------------
  # GLOBAL DEFAULTS
  # ------------------------------------------------------------
  defaults:
    hold_time_ms: 250
    step_time_ms: 600

    light_on_pct: 85
    light_step_pct: 12
    light_low_pct: 1

    fan_on_pct: 60
    fan_speeds: 6

    cover_open_pos: 100
    cover_step_pct: 10

    media_player_vol_step: 8

    middle_button:
      - action: light.turn_on
        target:
          entity_id: lights
        data:
          brightness_pct: 70
          kelvin: 2700

  # ------------------------------------------------------------
  # DEVICES
  # ------------------------------------------------------------
  devices:
    # 1. Paddle Pico controlling lights
    - name: Kitchen Paddle
      type: P2B
      lights:
        - light.kitchen_main

    # 2. Two-button Pico controlling a switch
    - name: Closet Pico
      type: 2B
      switches:
        - switch.closet_light

    # 3. 3BRL for lighting (inherits defaults)
    - name: Master Bedroom Remote
      type: 3BRL
      lights:
        - light.master_overhead
        - light.master_lamps
      middle_button: default

    # 4. 3BRL for fan (overrides defaults)
    - name: Living Room Fan Control
      type: 3BRL
      fans:
        - fan.living_room_fan
      fan_on_pct: 40
      hold_time_ms: 350
      middle_button:
        - action: fan.set_direction
          target:
            entity_id: fans
          data:
            direction: reverse

    # 5. 3BRL controlling a cover
    - name: Shade Controller
      type: 3BRL
      covers:
        - cover.living_room_shade
      cover_open_pos: 75
      middle_button: [] # STOP = stop_cover (default)

    # 6. 3BRL controlling a media player
    - name: Office Media Remote
      type: 3BRL
      media_players:
        - media_player.office_sonos
      media_player_vol_step: 5
      middle_button: [] # STOP = mute/unmute (default)

    # 7. 4-Button Scene Pico
    - name: Scene Controller
      type: 4B
      buttons:
        button_1:
          - action: scene.turn_on
            target:
              entity_id: scene.movie_mode

        button_2:
          - action: script.dim_lights_soft

        button_3:
          - action: light.turn_off
            target:
              entity_id:
                - light.kitchen
                - light.living_room

        off:
          - action: homeassistant.turn_off
            target:
              area_id: main_floor
```

---

# ☕ Support Development ❤️

<a href="https://buymeacoffee.com/smartqasa" target="_blank">
  <img src="https://www.buymeacoffee.com/assets/img/custom_images/yellow_img.png" height="60">
</a>
