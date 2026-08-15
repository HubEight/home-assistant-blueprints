#!/usr/bin/env python3
"""Behaviour matrix for the Radiator Fan Controller.

Runs the blueprint's real action script through Home Assistant's own script
engine with states set by hand and switch.turn_on/turn_off intercepted, then
checks what it did against what it should have done.

This is not a formality. Version 1.1.3 shipped for months unable to switch a
fan on at all unless window sensors were configured, because a template
returned the string 'false' where a boolean was meant. Reading the YAML did not
show it; running it did.

Needs Home Assistant importable, so run it inside a Home Assistant environment:

  python3 tools/test-radiator-fan-controller.py radiator-fan-controller/radiator_fan_controller.yaml
"""
import sys
import asyncio

from homeassistant.components.automation.config import (
    AUTOMATION_BLUEPRINT_SCHEMA,
    PLATFORM_SCHEMA,
)
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.core import Context, HomeAssistant, State
from homeassistant.helpers.script import Script
from homeassistant.util.yaml import loader

PATH = sys.argv[1] if len(sys.argv) > 1 else (
    "radiator-fan-controller/radiator_fan_controller.yaml")
SENSOR, SWITCH, WIN = "sensor.flow", "switch.fan", "binary_sensor.win"
SWITCH2, FAN = "switch.fan2", "fan.roof_vent"

TEMP_CHANGE = lambda a, b: {
    "platform": "state", "id": "temp_change", "entity_id": SENSOR,
    "from_state": State(SENSOR, str(a)), "to_state": State(SENSOR, str(b)),
}
HA_START = {"platform": "homeassistant", "id": "check", "event": "start"}
MANUAL = {"platform": None}
WINDOW_OPENED = {
    "platform": "state", "id": "turn_off", "entity_id": WIN,
    "from_state": State(WIN, "off"), "to_state": State(WIN, "on"),
}

# label, inputs, trigger, temp, switch, window, expected
CASES = [
    # --- The default: normal hysteresis 30/28, NO window sensors ---
    ("normal 30/28, no windows: 39->40, fan off", {}, TEMP_CHANGE(39, 40), "40", "off", None, "turn_on"),
    ("normal 30/28, no windows: 29->28, fan on", {}, TEMP_CHANGE(29, 28), "28", "on", None, "turn_off"),
    ("normal 30/28, no windows: Home Assistant start at 40", {}, HA_START, "40", "off", None, "turn_on"),
    ("normal 30/28, no windows: 39->40, already running", {}, TEMP_CHANGE(39, 40), "40", "on", None, None),
    ("normal 30/28, no windows: Run button", {}, MANUAL, "40", "off", None, None),

    # --- with a window sensor ---
    ("normal, window closed: 39->40, fan off", {"window_sensors": [WIN]}, TEMP_CHANGE(39, 40), "40", "off", "off", "turn_on"),
    ("normal, window open: 39->40, fan off", {"window_sensors": [WIN]}, TEMP_CHANGE(39, 40), "40", "off", "on", None),
    ("normal, window opens, fan on", {"window_sensors": [WIN]}, WINDOW_OPENED, "40", "on", "on", "turn_off"),

    # --- equal thresholds ---
    ("equal 30/30: 29->30, fan off", {"temp_on": 30, "temp_off": 30}, TEMP_CHANGE(29, 30), "30", "off", None, "turn_on"),
    ("equal 30/30: 30->29, fan on", {"temp_on": 30, "temp_off": 30}, TEMP_CHANGE(30, 29), "29", "on", None, "turn_off"),

    # --- inverted (path dependent) ---
    ("inverted 28/32: rising 27->29, fan off", {"temp_on": 28, "temp_off": 32}, TEMP_CHANGE(27, 29), "29", "off", None, "turn_on"),
    ("inverted 28/32: falling 33->31, fan on", {"temp_on": 28, "temp_off": 32}, TEMP_CHANGE(33, 31), "31", "on", None, "turn_off"),

    # --- sensor failure ---
    ("sensor goes unavailable, fan on", {}, {"platform": "state", "id": "turn_off", "entity_id": SENSOR,
     "from_state": State(SENSOR, "40"), "to_state": State(SENSOR, "unavailable")}, "unavailable", "on", None, "turn_off"),
# --- several devices: the point is "at least one", not "all" ---
    # Without match: any a mixed pair would leave the idle one standing.
    ("two devices, both off: 39->40", {"fan_switch": [SWITCH, SWITCH2]}, TEMP_CHANGE(39, 40), "40",
     {SWITCH: "off", SWITCH2: "off"}, None, "turn_on"),
    ("two devices, one already on: 39->40", {"fan_switch": [SWITCH, SWITCH2]}, TEMP_CHANGE(39, 40), "40",
     {SWITCH: "on", SWITCH2: "off"}, None, "turn_on"),
    ("two devices, both on: 39->40", {"fan_switch": [SWITCH, SWITCH2]}, TEMP_CHANGE(39, 40), "40",
     {SWITCH: "on", SWITCH2: "on"}, None, None),
    ("two devices, one on: 29->28", {"fan_switch": [SWITCH, SWITCH2]}, TEMP_CHANGE(29, 28), "28",
     {SWITCH: "on", SWITCH2: "off"}, None, "turn_off"),
    ("two devices, both off: 29->28", {"fan_switch": [SWITCH, SWITCH2]}, TEMP_CHANGE(29, 28), "28",
     {SWITCH: "off", SWITCH2: "off"}, None, None),

    # --- a fan entity, not a switch: switch.turn_on would not reach it ---
    ("fan entity: 39->40, off", {"fan_switch": [FAN]}, TEMP_CHANGE(39, 40), "40",
     {FAN: "off"}, None, "turn_on"),
    ("fan + switch mixed: 39->40, both off", {"fan_switch": [FAN, SWITCH]}, TEMP_CHANGE(39, 40), "40",
     {FAN: "off", SWITCH: "off"}, None, "turn_on"),

    # --- a single entity as a plain string, as older automations stored it ---
    ("single entity, stored as a string", {"fan_switch": SWITCH}, TEMP_CHANGE(39, 40), "40",
     {SWITCH: "off"}, None, "turn_on"),
]


async def main():
    hass = HomeAssistant("/config")
    bp = Blueprint(loader.load_yaml(PATH), expected_domain="automation",
                   schema=AUTOMATION_BLUEPRINT_SCHEMA)

    failures = 0
    for label, extra, trigger, temp, sw, win, expected in CASES:
        hass.states.async_set(SENSOR, temp, {"device_class": "temperature"})
        # sw is either one state for the single switch, or a dict per entity
        if isinstance(sw, dict):
            for entity, value in sw.items():
                hass.states.async_set(entity, value)
        else:
            hass.states.async_set(SWITCH, sw)
        if win is not None:
            hass.states.async_set(WIN, win, {"device_class": "window"})
        await hass.async_block_till_done()

        data = {"temperature_sensor": SENSOR, "fan_switch": SWITCH}
        data.update(extra)
        inputs = BlueprintInputs(bp, {"use_blueprint": {"path": "x.yaml", "input": data}})
        inputs.validate()
        cfg = PLATFORM_SCHEMA(inputs.async_substitute())

        calls = []
        for service in ("turn_on", "turn_off"):
            hass.services.async_register("homeassistant", service,
                                         lambda call, s=service: calls.append(s))

        rendered = cfg["variables"].async_render(hass, {"trigger": trigger})
        await Script(hass, cfg["actions"], "t", "automation").async_run(rendered, Context())
        await hass.async_block_till_done()

        got = calls[0] if calls else None
        ok = got == expected
        failures += not ok
        mark = "ok  " if ok else "FEHL"
        print(f"{mark} {label:<50} want {str(expected):<9} got {got}")

    print()
    print(f"{len(CASES) - failures} of {len(CASES)} as expected")
    sys.exit(1 if failures else 0)


asyncio.run(main())
