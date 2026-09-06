# Pico Link

### Lutron Pico remotes as domain-aware Home Assistant controllers

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
![GitHub release](https://img.shields.io/github/v/release/smartqasa/pico-link)
![GitHub License](https://img.shields.io/github/license/smartqasa/pico-link)

<p align="center">
  <img src="pico.png" width="180" alt="Pico Link logo">
</p>

---

## Overview

Pico Link converts supported **Lutron Caséta Pico remotes** into configurable,
domain-aware Home Assistant controllers.

It listens for:

```text
lutron_caseta_button_event
```

and routes Pico button events to lights, fans, covers, media players, switches,
scenes, scripts, and other Home Assistant services.

Features include:

- Tap-versus-hold detection where supported
- Brightness, volume, and cover-position stepping
- Continuous light, cover, and media-player ramping
- Tap-only fan speed control
- Domain-specific STOP-button behavior
- Ordered custom action execution
- Entity placeholder expansion
- Optimistic light and cover targets for responsive repeated taps
- Validation of Pico types, entities, domains, actions, and button mappings
- Protection against duplicate Pico device configuration
- Verification that the configured Pico type matches the reported hardware type

---

## Requirements

- Home Assistant 2023.1.0 or newer
- The Home Assistant **Lutron Caséta** integration configured and working
- Pico button events available as `lutron_caseta_button_event`
- YAML configuration in `configuration.yaml`

Pico Link depends on the Home Assistant `lutron_caseta` integration and is
loaded after it.

---

## Supported Pico Types

| Type   | Layout                          | Buttons                                   | Supported behavior                                     |
| ------ | ------------------------------- | ----------------------------------------- | ------------------------------------------------------ |
| `P2B`  | Paddle Pico                     | `on`, `off`                               | Domain-specific ON/OFF tap and hold behavior           |
| `2B`   | Two-button Pico                 | `on`, `off`                               | Domain-specific ON/OFF tap and hold behavior           |
| `3BRL` | On / Raise / Stop / Lower / Off | `on`, `raise`, `stop`, `lower`, `off`     | Full domain control with dedicated raise/lower buttons |
| `4B`   | Four-button scene Pico          | `button_1`, `button_2`, `button_3`, `off` | Ordered custom actions only                            |

The configured `type` is authoritative. Pico Link verifies the hardware type
reported by Lutron events. Events are ignored when the reported hardware type
does not match the configured type.

---

## Installation

### HACS

1. Open **HACS → Integrations**.

2. Open the menu and choose **Custom repositories**.

3. Add:

   ```text
   https://github.com/smartqasa/pico-link
   ```

4. Select **Integration** as the repository type.

5. Install **Pico Link**.

6. Restart Home Assistant.

### Manual installation

Copy the integration directory to:

```text
config/custom_components/pico_link/
```

The resulting structure should include:

```text
config/
└── custom_components/
    └── pico_link/
        ├── __init__.py
        ├── manifest.json
        ├── config.py
        ├── controller.py
        ├── utilities.py
        ├── actions/
        └── profiles/
```

Restart Home Assistant after installation or updates.

---

## Basic Configuration

Add Pico Link to `configuration.yaml`:

```yaml
pico_link:
  defaults:
    # Optional shared settings

  devices:
    # One entry per physical Pico
```

Each non-4B device must define:

- `type`
- `name` or `device_id`
- Exactly one controlled domain

Supported domain keys are:

```yaml
covers:
fans:
lights:
media_players:
switches:
```

A 4B Pico uses `buttons:` instead of an entity domain.

---

## Device Identification

A Pico can be identified by Home Assistant device name:

```yaml
- name: Kitchen Pico
  type: 3BRL
  lights:
    - light.kitchen
```

Or by Home Assistant device ID:

```yaml
- device_id: 0123456789abcdef0123456789abcdef
  type: 3BRL
  lights:
    - light.kitchen
```

Name matching checks the user-assigned device name first, then the
integration-provided device name.

When more than one device has the same name, configure the Pico using
`device_id`.

The same physical Pico `device_id` may appear only once under `devices:`. Later
duplicate entries are rejected.

---

## Entity Configuration

A domain may be configured as one entity ID:

```yaml
lights: light.kitchen
```

Or as a list:

```yaml
lights:
  - light.kitchen_ceiling
  - light.kitchen_pendants
```

Pico Link validates that:

- Every entity ID is a string.
- Every entity ID has a valid Home Assistant format.
- Every entity belongs to the expected domain.
- Duplicate entity IDs are removed while preserving order.
- Non-4B devices configure exactly one domain.

Examples of invalid assignments:

```yaml
lights:
  - fan.bedroom
```

```yaml
fans:
  - null
```

```yaml
covers:
  - living_room_shade
```

### Multiple entities

When multiple entities are configured:

- Service commands are sent to all configured entities.
- State-dependent calculations use the first configured entity as the reference.

For example, when several lights are assigned, brightness steps are calculated
from the first light and the resulting brightness is sent to all assigned
lights.

---

## Timing Configuration

Pico Link uses timing thresholds for tap-versus-hold detection and repeated ramp
operations.

| Parameter      | Default | Accepted range | Purpose                              |
| -------------- | ------: | -------------: | ------------------------------------ |
| `hold_time_ms` |   `400` |     `100–2000` | Delay before a press becomes a hold  |
| `step_time_ms` |   `650` |     `100–2000` | Delay between repeated ramp commands |

Recommended values:

```yaml
hold_time_ms: 400
step_time_ms: 650
```

Poor timing values can cause missed taps, overly sensitive holds, or slow ramp
behavior.

These settings affect lights, covers, and media players. Fans are always
tap-only.

---

## Configuration Options

| Key                     | Applies to          |        Default | Accepted range or values              |
| ----------------------- | ------------------- | -------------: | ------------------------------------- |
| `type`                  | All                 |       Required | `P2B`, `2B`, `3BRL`, `4B`             |
| `name`                  | All                 |              — | Home Assistant device name            |
| `device_id`             | All                 |              — | Home Assistant device ID              |
| `covers`                | Non-4B              |              — | One or more `cover.*` entities        |
| `fans`                  | Non-4B              |              — | One or more `fan.*` entities          |
| `lights`                | Non-4B              |              — | One or more `light.*` entities        |
| `media_players`         | Non-4B              |              — | One or more `media_player.*` entities |
| `switches`              | Non-4B              |              — | One or more `switch.*` entities       |
| `buttons`               | 4B                  |       Required | Button-to-action mapping              |
| `middle_button`         | 3BRL                | Domain default | Custom STOP actions                   |
| `hold_time_ms`          | Light, cover, media |          `400` | `100–2000` ms                         |
| `step_time_ms`          | Light, cover, media |          `650` | `100–2000` ms                         |
| `cover_open_pos`        | Cover               |          `100` | `1–100` percent                       |
| `cover_step_pct`        | Cover               |           `10` | `1–25` percent                        |
| `cover_inverted`        | Cover               |        `false` | Boolean                               |
| `fan_on_pct`            | Fan                 |          `100` | `1–100` percent                       |
| `light_on_pct`          | Light               |          `100` | `1–100` percent                       |
| `light_low_pct`         | Light               |            `5` | `1–99` percent                        |
| `light_step_pct`        | Light               |           `10` | `1–25` percent                        |
| `light_transition_on`   | Light               |            `0` | `0–300` seconds                       |
| `light_transition_off`  | Light               |            `0` | `0–300` seconds                       |
| `media_player_vol_step` | Media player        |           `10` | `1–20` percent                        |

Numeric values outside their accepted ranges are clamped. Invalid numeric values
use their defaults.

---

## Domain Behavior

### Lights

#### P2B and 2B

| Gesture  | Action                    |
| -------- | ------------------------- |
| ON tap   | Turn on at `light_on_pct` |
| ON hold  | Ramp brightness upward    |
| OFF tap  | Turn off                  |
| OFF hold | Ramp brightness downward  |

#### 3BRL

| Button | Tap                                         | Hold          |
| ------ | ------------------------------------------- | ------------- |
| ON     | Turn on at `light_on_pct`                   | —             |
| OFF    | Turn off                                    | —             |
| RAISE  | Increase by `light_step_pct`                | Ramp upward   |
| LOWER  | Decrease by `light_step_pct`                | Ramp downward |
| STOP   | Custom `middle_button`, otherwise no action | —             |

Brightness does not ramp below `light_low_pct`.

Rapid repeated brightness taps use the most recently requested brightness for a
short period instead of waiting for Home Assistant state to update.

### Light transitions

`light_transition_on` and `light_transition_off` apply only to ON and OFF tap
actions.

```yaml
light_transition_on: 1
light_transition_off: 3
```

When a transition is `0`, the transition field is omitted from the service call.

Brightness steps and ramps do not use transitions.

---

### Fans

Fan controls are always tap-only. Holding a fan button does not initiate a ramp.

| Button | Action                                              |
| ------ | --------------------------------------------------- |
| ON     | Set speed to `fan_on_pct`                           |
| OFF    | Turn off                                            |
| RAISE  | Move up one available fan speed                     |
| LOWER  | Move down one available fan speed                   |
| STOP   | Custom `middle_button`, otherwise reverse direction |

Fan speed steps are calculated from the entity’s `percentage_step` attribute.

If the fan is off, RAISE moves it to the first nonzero speed.

If the fan does not expose a usable `percentage_step`, Pico Link falls back to:

```text
0 → 100
```

---

### Covers

#### P2B and 2B

| Gesture                | Action                                 |
| ---------------------- | -------------------------------------- |
| ON tap                 | Open to `cover_open_pos`               |
| ON hold                | Move continuously in the ON direction  |
| OFF tap                | Close fully                            |
| OFF hold               | Move continuously in the OFF direction |
| ON or OFF while moving | Stop movement                          |

When `cover_inverted: true`, ON and OFF tap and hold directions are reversed.

#### 3BRL

| Button | Tap                                    | Hold               |
| ------ | -------------------------------------- | ------------------ |
| ON     | Open to `cover_open_pos`               | —                  |
| OFF    | Close fully                            | —                  |
| RAISE  | Increase position by `cover_step_pct`  | Open continuously  |
| LOWER  | Decrease position by `cover_step_pct`  | Close continuously |
| STOP   | Custom `middle_button`, otherwise stop | —                  |

Rapid repeated cover taps use the most recently requested target position for a
short period instead of waiting for `current_position` to update.

When changing direction after continuous movement, Pico Link waits for
`stop_cover` to complete before submitting the next position command.

---

### Media Players

#### P2B and 2B

| Gesture  | Action                    |
| -------- | ------------------------- |
| ON tap   | Play or pause             |
| ON hold  | Raise volume continuously |
| OFF tap  | Next track                |
| OFF hold | Lower volume continuously |

#### 3BRL

| Button | Tap                                           | Hold                      |
| ------ | --------------------------------------------- | ------------------------- |
| ON     | Play or pause                                 | —                         |
| OFF    | Next track                                    | —                         |
| RAISE  | Raise volume one step                         | Raise volume continuously |
| LOWER  | Lower volume one step                         | Lower volume continuously |
| STOP   | Custom `middle_button`, otherwise toggle mute | —                         |

The volume step is configured as a percentage:

```yaml
media_player_vol_step: 5
```

Volume commands are clamped between `0.0` and `1.0`.

---

### Switches

| Button | Action                                      |
| ------ | ------------------------------------------- |
| ON     | Turn on                                     |
| OFF    | Turn off                                    |
| STOP   | Custom `middle_button`, otherwise no action |
| RAISE  | No action                                   |
| LOWER  | No action                                   |

Switches do not support hold behavior.

---

### 4B Scene Controllers

A 4B Pico does not control a domain directly. Each button executes a configured
list of Home Assistant actions.

Supported keys are:

```text
button_1
button_2
button_3
off
```

Each configured button must contain at least one action.

Actions execute sequentially in the order listed. Each action completes before
the next action begins.

Example:

```yaml
- name: Scene Pico
  type: 4B
  buttons:
    button_1:
      - action: scene.turn_on
        target:
          entity_id: scene.movie

    button_2:
      - action: script.turn_on
        target:
          entity_id: script.good_night

    button_3:
      - action: light.turn_off
        target:
          area_id: main_floor

    off:
      - action: homeassistant.turn_off
        target:
          area_id: main_floor
```

---

## STOP and `middle_button`

`middle_button` is valid only for `3BRL` Picos.

Resolution order:

1. Explicit actions configured on the device
2. Shared default actions when the device specifies `middle_button: default`
3. Domain-specific STOP behavior when `middle_button` is omitted or empty

### Domain defaults

| Domain       | Default STOP behavior |
| ------------ | --------------------- |
| Cover        | Stop movement         |
| Fan          | Reverse direction     |
| Light        | No action             |
| Media player | Toggle mute           |
| Switch       | No action             |

### Use domain default

Omit `middle_button`:

```yaml
- name: Living Room Fan
  type: 3BRL
  fans:
    - fan.living_room
```

Or explicitly provide an empty list:

```yaml
middle_button: []
```

### Use the shared default

Define a shared default:

```yaml
pico_link:
  defaults:
    middle_button:
      - action: light.turn_on
        target:
          entity_id: light.accent
```

Opt in from a 3BRL device:

```yaml
middle_button: default
```

### Device-specific actions

```yaml
middle_button:
  - action: scene.turn_on
    target:
      entity_id: scene.relax

  - action: media_player.media_play
    target:
      entity_id: media_player.living_room
```

Custom action lists execute sequentially.

---

## Entity Placeholders

Within a 3BRL `middle_button` action, these values can be used as
`target.entity_id` placeholders:

| Placeholder     | Expands to                           |
| --------------- | ------------------------------------ |
| `covers`        | All configured cover entities        |
| `fans`          | All configured fan entities          |
| `lights`        | All configured light entities        |
| `media_players` | All configured media-player entities |
| `switches`      | All configured switch entities       |

Single placeholder:

```yaml
middle_button:
  - action: light.turn_on
    target:
      entity_id: lights
```

Placeholder mixed with explicit entities:

```yaml
middle_button:
  - action: light.turn_on
    target:
      entity_id:
        - lights
        - light.accent_lamp
```

Other target fields are preserved during placeholder expansion:

```yaml
middle_button:
  - action: light.turn_on
    target:
      entity_id: lights
      area_id: living_room
```

---

## Action Format

`middle_button` and `buttons` are validated and executed with Home
Assistant's own action engine — the same one behind automations and
scripts — not just a hand-rolled list of service calls. A plain action uses
Home Assistant's `domain.service` format:

```yaml
- action: light.turn_on
  target:
    entity_id: light.kitchen
  data:
    brightness_pct: 80
```

Because validation and execution go through Home Assistant's real script
schema (`cv.SCRIPT_SCHEMA` + `homeassistant.helpers.script.Script`), the
full range of native actions is available too — conditions, **if-then**,
**choose**, **repeat**, **wait**, and templates in service data — not just
plain service calls. For example, a STOP action that behaves differently
depending on current state:

```yaml
middle_button:
  - if:
      - condition: state
        entity_id: light.kitchen_edge
        state: "on"
      - condition: state
        entity_id: light.kitchen_center
        state: "off"
    then:
      - action: light.turn_off
        target:
          entity_id: light.kitchen_edge
      - action: light.turn_on
        target:
          entity_id: light.kitchen_center
    else:
      - action: light.turn_on
        target:
          entity_id: light.kitchen_edge
      - action: light.turn_off
        target:
          entity_id: light.kitchen_center
```

Pico Link validates that:

- The action list is a list, and each item conforms to Home Assistant's
  action schema.
- 4B button values are nonempty action lists.

Entity placeholders (see [Entity Placeholders](#entity-placeholders) above)
are expanded before validation, and work inside nested if-then/choose
branches too.

---

## Complete Example

```yaml
pico_link:
  defaults:
    hold_time_ms: 400
    step_time_ms: 650

    middle_button:
      - action: light.turn_on
        target:
          entity_id: lights
        data:
          brightness_pct: 80

  devices:
    # Paddle Pico controlling a light
    - name: Kitchen Paddle
      type: P2B
      lights:
        - light.kitchen_main
      light_on_pct: 100
      light_transition_on: 1
      light_transition_off: 3

    # Two-button Pico controlling a switch
    - name: Closet Pico
      type: 2B
      switches:
        - switch.closet_light

    # 3BRL controlling multiple lights
    - name: Bedroom Remote
      type: 3BRL
      lights:
        - light.bedroom_main
        - light.bedroom_lamps
      light_on_pct: 80
      light_low_pct: 5
      light_step_pct: 10
      middle_button: default

    # Tap-only fan control
    - name: Living Room Fan
      type: 3BRL
      fans:
        - fan.living_room
      fan_on_pct: 40

    # Cover control
    - name: Shade Remote
      type: 3BRL
      covers:
        - cover.living_room_shade
      cover_open_pos: 100
      cover_step_pct: 10
      cover_inverted: false

    # Media-player control
    - name: Office Media
      type: 3BRL
      media_players:
        - media_player.office_sonos
      media_player_vol_step: 5

    # Four-button scene control
    - name: Scene Pico
      type: 4B
      buttons:
        button_1:
          - action: scene.turn_on
            target:
              entity_id: scene.movie

        button_2:
          - action: script.turn_on
            target:
              entity_id: script.good_night

        button_3:
          - action: light.turn_off
            target:
              area_id: main_floor

        off:
          - action: homeassistant.turn_off
            target:
              area_id: main_floor
```

---

## Validation and Error Handling

Pico Link validates configuration during Home Assistant startup.

It checks for:

- Supported Pico types
- Exactly one domain for non-4B devices
- No entity domain on 4B devices
- Correct entity-ID formats
- Correct entity domains
- Valid Boolean values
- Valid action structures
- Valid 4B button names
- Nonempty 4B action lists
- `middle_button` only on 3BRL devices
- `buttons` only on 4B devices
- Duplicate Pico `device_id` entries

A malformed device entry is logged and skipped. Other valid Pico entries
continue loading.

When no valid entries remain, Home Assistant logs:

```text
pico_link is configured, but no valid Pico devices were created
```

The specific validation errors for rejected entries appear immediately before
that summary.

---

## Troubleshooting

### Pico Link loads but no buttons work

Confirm:

1. The Lutron Caséta integration is loaded.
2. The Pico emits `lutron_caseta_button_event`.
3. The configured `device_id` matches the event’s `device_id`.
4. The configured `type` matches the type reported in the event.
5. The assigned entity IDs exist and use the correct domain.

### No valid Pico devices were created

Review the Pico Link log entries immediately before the summary warning. Each
rejected device entry logs its index, configured name or ID, type, and
validation error.

### Configured and reported Pico types do not match

Pico Link treats the YAML `type` as authoritative and ignores mismatched events.

Correct the configured type to match the physical remote:

```yaml
type: P2B
```

```yaml
type: 2B
```

```yaml
type: 3BRL
```

```yaml
type: 4B
```

### Rapid cover or light taps

Pico Link retains recent requested brightness and cover-position targets so
repeated taps do not depend on immediate entity-state updates.

When behavior appears out of sync after an external change, wait briefly before
the next tap so Pico Link resynchronizes from Home Assistant.

### Fan holds do not ramp

This is intentional. Fan controls are tap-only.

---

## Updating

After installing an updated version:

1. Restart Home Assistant.
2. Review the Pico Link startup log.
3. Confirm that the expected number of controllers was initialized.
4. Test ON, OFF, RAISE, LOWER, STOP, and custom actions for each configured Pico
   type.

---

## Support Development

<a href="https://buymeacoffee.com/smartqasa" target="_blank">
  <img src="https://www.buymeacoffee.com/assets/img/custom_images/yellow_img.png" height="60" alt="Support development">
</a>
