# TRV External Sensor Guard

Lets Sonoff TRVZB radiator thermostats regulate by the thermometer in the room
instead of the sensor sitting on the hot radiator — and keeps that safe when the
room thermometer goes silent.
**Version 1.1.0**

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FHubEight%2Fhome-assistant-blueprints%2Fblob%2Fmain%2Ftrv-external-sensor-guard%2Ftrv_external_sensor_guard.yaml)

One automation per room does three things:

- **Sends the room temperature** to every thermostat of the room — on every
  change, and again after the resend interval even if nothing changed.
- **Switches the thermostats to their internal sensor** when the room
  thermometer has been silent longer than the failure limit.
- **Switches them back to external** as soon as it reports again, and undoes a
  manual switch to internal while the room thermometer is fine.

It runs only when something is off. A room where everything is as it should be
produces no runs at all, apart from the resend.

## Requirements

- Home Assistant 2025.4 or later
- Zigbee2MQTT with Home Assistant discovery (not ZHA)
- **`last_seen` enabled in Zigbee2MQTT** (Settings → Advanced → Last seen). Any
  of its three formats works: ISO, ISO local, epoch
- Sonoff **TRVZB** thermostats (tested). The **TRV-ZBT** is selectable but
  untested

## Inputs

Grouped in four sections: Room, Timing, Notifications, and Entity suffixes
(collapsed, rarely needed).

| Input | Default | |
|---|---|---|
| Thermostats | – | Devices, several allowed. Only Sonoff TRVZB / TRV-ZBT are listed |
| Room thermometer | – | A Zigbee2MQTT device with a temperature sensor. Thermostats appear in this list too — do not pick one |
| Room name | empty | Empty = the room thermometer's area, or its device name without an area |
| Failure limit | 20 min | Silence after which the thermostats go to internal |
| Resend interval | 60 min | Longest time between two sends of the temperature, at least 2 |
| Four suffixes | `_temperature`, `_last_seen`, `_external_temperature_input`, `_temperature_sensor_select` | How the entities are found on each device. Change them only if your entity IDs end differently |
| Notify device | – | A phone with the Companion app |
| Title, two messages | English texts | For the notify device |
| Custom notification action | – | Any action, see below |
| Notification switch | – | An `input_boolean`. If set, notifications only go out while it is on |

### Why both minute fields should stay below 120

The thermostat has its own fallback: after **2 hours** without an external value
it switches to its own sensor and reports the external one as offline.

- A **failure limit** of 120 or more means the thermostat always gets there first.
- A **resend interval** of 120 or more lets the thermostat fall back between two
  sends whenever the temperature did not change.

Both are accepted, but log a warning when the automation starts.

## How it works

### The room thermometer has three states

| State | When | What the guard does |
|---|---|---|
| **alive** | `last_seen` is younger than the failure limit | Sends, keeps thermostats on external |
| **outage** | `last_seen` is older than the failure limit, **and** it has not changed in Home Assistant for that long either | Thermostats to internal |
| **unknown** | Anything else: `unavailable`, unreadable, or an old time stamp just restored after a restart | Nothing |

The second condition of *outage* matters: after a long Zigbee2MQTT or Home
Assistant restart, Zigbee2MQTT restores the old `last_seen`. Without it, every
room would switch to internal the moment Zigbee2MQTT comes back, and back again
a minute later. Only time in which the thermometer could have reported counts.

### Rules

| Trigger | Only while | Action | `reason` |
|---|---|---|---|
| Outage begins, or a thermostat is not on internal during one | outage | Thermostats to internal, notify | `outage` |
| Thermometer alive again, a thermostat on internal | alive | To external, send, notify | `recovered` |
| A thermostat is switched to internal | alive | Back to external, send, notify | `manual` |
| A thermostat's value differs from the thermometer (0.1 °C) | alive | Send to all | – |
| A thermostat reports the external sensor offline | alive | Send (the thermostat returns to external by itself), logbook note | – |
| Resend interval reached, on the clock (on the hour for 60) | alive | Send | – |
| Home Assistant start, automation created, switched on or saved with changes | – | Check the configuration, then all of the above once | `reconcile` |

Every run while the room thermometer is alive sends the temperature.

A thermostat that comes back after being unreachable is caught by the same
rules; a switch it missed is made up with `reason: reconcile`. Unreachable
thermostats are skipped. Every switch of the sensor source is written to the
logbook, whether or not notifications are on.

### Old and new option names

Zigbee2MQTT renamed the options of the sensor source in
zigbee-herdsman-converters 26.113.0. Both are understood, and the guard writes
whichever name the thermostat offers:

| | before | from 26.113.0 |
|---|---|---|
| internal | `internal` | `local_temperature` |
| external | `external`, `external_3` | `remote_temperature` |
| offline | `external_2` | `remote_source_offline` |

### Configuration check

When Home Assistant starts or the automation is switched on or saved, it checks
that each device has **exactly one** entity per suffix, and that the room
thermometer is not a thermostat. If not, it writes a warning to the system log
naming the device and suffix, and switches nothing.

## Notifications

Two independent ways, both optional; if both are set, both run:

1. **Notify device** — pick a phone, adjust title and messages
2. **Custom notification action** — anything you like

Notifications go out only when a thermostat was actually switched. These
variables are available in the texts and in the custom action:

| Variable | Values |
|---|---|
| `room` | Room name |
| `source` | `internal` / `external` |
| `reason` | `outage` / `recovered` / `manual` / `reconcile` |
| `silence_minutes` | Minutes since the last `last_seen`, empty if unknown |

Example custom action with iOS extras:

```yaml
- action: notify.mobile_app_my_iphone
  data:
    title: "🌡️ {{ room }}"
    message: >-
      {% if source == 'internal' %}
        Room thermometer silent for {{ silence_minutes }} min, using the thermostat's own sensor.
      {% else %}
        Room thermometer in use again ({{ reason }}).
      {% endif %}
    data:
      subtitle: TRV External Sensor Guard
      group: trv-guard
      push:
        interruption-level: time-sensitive
```

## Known limitations

- A thermometer that also has a `…_device_temperature` sensor matches the
  `_temperature` suffix twice: warning, nothing switched. Change the suffix.
- Outages are detected up to a minute late: time-based templates are evaluated
  once a minute.
- If Zigbee2MQTT or Home Assistant restarts while the thermometer is already
  silent, the outage is detected up to one failure limit later.
- Each trigger fires when its gap opens, not again while it stays open. If the
  temperature changes twice before a thermostat confirmed the first value, or a
  second thermostat reports offline while the first still does, the next resend
  catches it at the latest.
- Reloading automations without changing this one does not re-check it. Switch
  it off and on to force a check.
- Zigbee2MQTT only, not ZHA.

## Changelog

### 1.1.0

- **Fixed: a newly created automation did not check itself and did not
  resend until the next restart.** Home Assistant attaches the triggers of a
  new automation before it has a state, and two triggers looked at that
  state. The first check now runs on the reload that follows the creation,
  and the resend no longer depends on the automation's own state: it runs on
  the clock, every resend interval (on the hour for 60). The temperature was
  still sent on every change in 1.0.0
- The resend interval is at least 2 minutes now; at 1 the clock-based
  trigger could never fire again
- The form is grouped into sections: Room, Timing, Notifications, and the
  entity suffixes, which start collapsed. Existing automations keep their
  settings

### 1.0.0

- First release

## Support

Bug? Idea? → [Open an issue on GitHub](https://github.com/HubEight/home-assistant-blueprints/issues)
