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
  - pico_device_id: f00abdc1ee0fed3b5fd56b1d800154a7
    entities:
      - light.office_desk_strip
    profile: paddle # "paddle" or "five_button"
    hold_time_ms: 250 # only for paddle
    step_pct: 5 # ramp amount per step
    step_time_ms: 200 # time between steps
    brightness_on_pct: 100 # ON button brightness

```
