# Home Assistant Blueprints

Collection of automation blueprints for Home Assistant.

## Radiator Fan Controller with Temperature & Window Detection

**Version:** 1.0.1

Automatically controls a radiator fan based on temperature with hysteresis and optional window contact monitoring.

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FHubEight%2Fhome-assistant-blueprints%2Fblob%2Fmain%2Fradiator_fan_controller.yaml)

### Features

✅ **Temperature-based control** with hysteresis to prevent rapid switching  
✅ **Flexible temperature settings**: Direct input or dynamic via input_number helpers  
✅ **Multi-window support**: Optional monitoring of unlimited window sensors  
✅ **Safety features**: Automatically turns off fan when sensor fails or any window opens  
✅ **Smart startup**: Checks conditions when Home Assistant starts or automation is enabled

### How it works

- **Fan turns ON** when radiator temperature reaches the set threshold (default: 30°C)
- **Fan turns OFF** when temperature drops below the lower threshold (default: 28°C)
- **Fan turns OFF** immediately if any window is opened
- **Fan evaluates** conditions when windows close or Home Assistant restarts

### Configuration

#### Required:
- **Temperature Sensor**: Sensor measuring radiator temperature
- **Fan Switch**: Switch or smart plug controlling the fan

#### Optional:
- **Temperature ON (°C)**: Set direct value or use input_number helper
- **Temperature OFF (°C)**: Set direct value or use input_number helper  
- **Window Sensors**: Select any number of window/door contact sensors

#### Temperature Control Options:

**Option 1 - Direct Input (Simple):**
- Set fixed values: e.g., ON at 30°C, OFF at 28°C
- Best for static setpoints

**Option 2 - Input Number Helpers (Advanced):**
- Use `input_number` entities for dynamic control
- Change temperatures on-the-fly via UI or other automations
- Helper values override direct input

### Example Use Cases

- **Single Room**: Control a radiator fan to improve heat distribution
- **Multiple Rooms**: Create separate automations for each room
- **Energy Saving**: Stop heating when windows are open
- **Dynamic Control**: Adjust temperatures based on time of day or other conditions

### Installation

#### Method 1: One-Click Import (Easiest)
Click the badge above or use this URL in Home Assistant:
```
Settings → Automations & Scenes → Blueprints → Import Blueprint
```
Paste: `https://github.com/HubEight/home-assistant-blueprints/blob/main/radiator_fan_controller.yaml`

#### Method 2: Manual Installation
1. Copy the blueprint code from `radiator_fan_controller.yaml`
2. In Home Assistant: `Settings → Automations & Scenes → Blueprints → Import Blueprint`
3. Paste the code in the YAML editor

### Creating an Automation

1. Go to `Settings → Automations & Scenes → Create Automation`
2. Select **"Radiator Fan Controller with Temperature & Window Detection"**
3. Configure your entities and temperature values
4. Save and enable!

### Support

Found a bug or have a suggestion? Open an issue on GitHub!

### License

MIT License - feel free to use and modify!
