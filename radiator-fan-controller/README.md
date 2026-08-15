# Radiator Fan Controller

Automatically controls a radiator fan based on temperature with hysteresis and optional window contact monitoring.  
**Version 1.1.3 – enhanced hysteresis logic with three configurable cases**

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FHubEight%2Fhome-assistant-blueprints%2Fblob%2Fmain%2Fradiator-fan-controller%2Fradiator_fan_controller.yaml)

## Features
✅ **Three hysteresis modes** based on `temp_on` vs `temp_off`  
✅ **Flexible temperature settings**: Direct input or dynamic via `input_number` helpers  
✅ **Multi-window support**: Fan turns OFF when any window opens  
✅ **Safety features**: Immediate OFF on sensor failure or open window  
✅ **Smart startup**: Re-evaluates on HA start or window close  

## How it works
| Mode | Condition | ON when | OFF when |
|------|-----------|---------|----------|
| **Normal** | `temp_on > temp_off` | `≥ temp_on` | `≤ temp_off` |
| **Equal** | `temp_on = temp_off` | `≥ temp_on` | `< temp_on` |
| **Inverted** | `temp_on < temp_off` | Rising **and** crosses **either** threshold | Falling **and** crosses **either** threshold |

- **Helper changes** (`temp_on_helper`, `temp_off_helper`) **do not trigger fan changes** – only temperature changes do  
- **Path-dependent** in inverted mode: state persists between thresholds  
- **No helper required** for internal state – uses `trigger.from_state`  

## Configuration
### Required:
- **Temperature Sensor**  
- **Fan Switch**  

### Optional:
- **Temperature ON (°C)** – direct or via helper  
- **Temperature OFF (°C)** – direct or via helper  
- **Window Sensors** – any number  

> **Helper values override direct input**  
> Changing helpers updates thresholds **without switching the fan** – next temperature change applies new logic.

## Example Use Cases
- **Classic heating**: `ON=30`, `OFF=28`  
- **Sharp threshold**: `ON=30`, `OFF=30` → ON at ≥30°C  
- **Early ON, late OFF**: `ON=28`, `OFF=32` → path-dependent hysteresis  

## Installation
### One-Click Import
Click the badge above or paste in HA:  

https://github.com/HubEight/home-assistant-blueprints/blob/main/radiator-fan-controller/radiator_fan_controller.yaml

### Manual
1. Copy `radiator_fan_controller.yaml`  
2. HA → **Blueprints → Import Blueprint** → Paste YAML  

## Creating an Automation
1. **Automations & Scenes → Create Automation**  
2. Select **Radiator Fan Controller**  
3. Fill in entities and thresholds  
4. Save & enable  

## Support
Bug? Idea? → [Open an issue on GitHub](https://github.com/HubEight/home-assistant-blueprints/issues)
