#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["homeassistant==2026.9.4", "freezegun==1.5.5"]
# ///
"""Behaviour matrix for the TRV External Sensor Guard.

Starts a real Home Assistant in-process, with devices and entities in the
registry, creates one automation from the blueprint and drives it: states are
set by hand, time is moved forward, and every action the automation calls
(select, number, notify, logbook, system_log, the custom action) is caught
instead of reaching a device. Then it checks what came out.

The triggers are tested too, not only the actions: most of this blueprint's
logic lives in template triggers that fire when their value turns true, and
those only show their behaviour with real state changes and a moving clock.

uv builds the environment from the header above, so nothing else is needed:

  uv run tools/test-trv-external-sensor-guard.py
"""
import asyncio
import datetime as dt
import shutil
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from freezegun import freeze_time

from homeassistant import bootstrap, config as conf_util, config_entries, loader
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

BLUEPRINT = Path(__file__).parent.parent / "trv-external-sensor-guard" / "trv_external_sensor_guard.yaml"
START = datetime(2026, 9, 29, 8, 0, 30, tzinfo=UTC)
REAL_MONOTONIC = time.monotonic  # before freezegun replaces it

OLD = ["internal", "external", "external_2", "external_3"]
NEW = ["local_temperature", "remote_temperature", "remote_source_offline"]
IN_A, IN_B = "number.trv_a_external_temperature_input", "number.trv_b_external_temperature_input"
SEL_A, SEL_B = "select.trv_a_temperature_sensor_select", "select.trv_b_temperature_sensor_select"
TEMP, SEEN = "sensor.thermometer_temperature", "sensor.thermometer_last_seen"
CUSTOM = [{"action": "test.custom", "data": {
    k: "{{ %s }}" % k for k in ("room", "source", "reason", "silence_minutes")}}]


def freeze_utcnow():
    """dt_util.utcnow is a partial bound to the real datetime.now, which
    freezegun cannot see; it is imported by name all over Home Assistant."""
    real = UTCNOW
    fake = lambda: dt.datetime.now(UTC)  # dt.datetime is freezegun's by now
    for module in list(sys.modules.values()):
        for name, value in list(vars(module).items()):
            if value is real:
                setattr(module, name, fake)


UTCNOW = dt_util.utcnow


class Room:
    """One Home Assistant with a room thermometer, two thermostats, a phone."""

    def __init__(self, inputs=None, seen_format="iso", names=OLD, trv_b_names=None,
                 area="Living room", thermometer_extra=(), trv_b_suffixes=None,
                 thermometer_is_trv=False, sources=("external", "external"), created_later=False):
        self.inputs = inputs or {}
        self.seen_format = seen_format
        self.names = {SEL_A: names, SEL_B: trv_b_names or names}
        self.area = area
        self.thermometer_extra = thermometer_extra
        self.trv_b_suffixes = trv_b_suffixes
        self.thermometer_is_trv = thermometer_is_trv
        self.start_sources = sources
        self.created_later = created_later
        self.calls = []
        self.runs = 0
        self.heartbeat = True
        self.minute = 0

    # --- setup ---------------------------------------------------------

    async def start(self, before_start=None):
        self.clock_ctl = freeze_time(START, real_asyncio=True)
        self.clock = self.clock_ctl.start()
        self.shift = 0.0
        # The event loop schedules timers on its own clock, so it has to move too.
        loop = asyncio.get_running_loop()
        loop.time = lambda: REAL_MONOTONIC() + self.shift
        freeze_utcnow()

        self.dir = tempfile.mkdtemp()
        bp_dir = Path(self.dir, "blueprints", "automation", "test")
        bp_dir.mkdir(parents=True)
        shutil.copy(BLUEPRINT, bp_dir / BLUEPRINT.name)
        Path(self.dir, "configuration.yaml").write_text("automation: !include automations.yaml\n")

        hass = self.hass = HomeAssistant(self.dir)
        loader.async_setup(hass)
        hass.config_entries = config_entries.ConfigEntries(hass, {})
        await bootstrap.async_load_base_functionality(hass)
        self.devices = self._registry()
        self.write_automation(present=not self.created_later)
        self._initial_states()
        if before_start:
            before_start(self)

        for domain, service in [("select", "select_option"), ("number", "set_value"),
                                ("logbook", "log"), ("system_log", "write"),
                                ("notify", "mobile_app_pixel_9"), ("test", "custom")]:
            hass.services.async_register(domain, service, self._catch)
        hass.bus.async_listen("automation_triggered", self._count_run)

        conf = await conf_util.async_hass_config_yaml(hass)
        await async_setup_component(hass, "homeassistant", conf)
        await async_setup_component(hass, "automation", conf)
        await hass.async_start()
        await self.settle()
        return self

    def _registry(self):
        hass = self.hass
        devr, entr, area = dr.async_get(hass), er.async_get(hass), ar.async_get(hass)
        ids = {}

        def entry(domain):
            e = config_entries.ConfigEntry(
                domain=domain, title=domain, data={}, source="user", version=1,
                minor_version=1, options={}, unique_id=None, discovery_keys={},
                subentries_data=None)
            hass.config_entries._entries[e.entry_id] = e
            return e

        mqtt, phone = entry("mqtt"), entry("mobile_app")

        def device(name, cfg, entities, **attrs):
            d = devr.async_get_or_create(config_entry_id=cfg.entry_id,
                                         identifiers={(cfg.domain, name)}, name=name, **attrs)
            for domain, obj in entities:
                entr.async_get_or_create(domain, cfg.domain, obj, device_id=d.id,
                                         suggested_object_id=obj, config_entry=cfg)
            ids[name] = d.id
            return d

        trv = dict(manufacturer="SONOFF", model="Thermostatic radiator valve", model_id="TRVZB")
        suffixes = ("external_temperature_input", "temperature_sensor_select")
        for name, sfx in (("trv_a", suffixes), ("trv_b", self.trv_b_suffixes or suffixes)):
            device(name, mqtt, [("number", f"{name}_{sfx[0]}"), ("select", f"{name}_{sfx[1]}"),
                                ("sensor", f"{name}_local_temperature"), ("sensor", f"{name}_last_seen"),
                                ("number", f"{name}_local_temperature_calibration")], **trv)
        th = device("thermometer", mqtt, [("sensor", "thermometer_temperature"),
                                          ("sensor", "thermometer_last_seen"),
                                          ("sensor", "thermometer_humidity")]
                    + [("sensor", f"thermometer_{x}") for x in self.thermometer_extra],
                    manufacturer="SONOFF", model="Temperature and humidity sensor", model_id="SNZB-02D")
        if self.area:
            devr.async_update_device(th.id, area_id=area.async_create(self.area).id)
        device("Pixel 9", phone, [])
        return ids

    def automation_config(self):
        room = "trv_a" if self.thermometer_is_trv else "thermometer"
        inputs = {"thermostats": [self.devices["trv_a"], self.devices["trv_b"]],
                  "room_thermometer": self.devices[room]} | self.inputs
        if inputs.get("notify_device") == "PHONE":
            inputs["notify_device"] = self.devices["Pixel 9"]
        return [{"id": "guard", "alias": "Guard",
                 "use_blueprint": {"path": f"test/{BLUEPRINT.name}", "input": inputs}}]

    def write_automation(self, present=True):
        config = self.automation_config() if present else []
        Path(self.dir, "automations.yaml").write_text(yaml.safe_dump(config))

    def _initial_states(self):
        S = self.hass.states.async_set
        S(TEMP, "21.0", {"device_class": "temperature"})
        self.beat()
        for sel, inp, src in ((SEL_A, IN_A, self.start_sources[0]), (SEL_B, IN_B, self.start_sources[1])):
            S(inp, "21.0")
            S(sel, self.name(sel, src), {"options": self.names[sel]})
        S("sensor.trv_a_local_temperature", "23.5", {"device_class": "temperature"})
        S("sensor.trv_a_last_seen", self.stamp())

    # --- what the automation does -------------------------------------

    def _catch(self, call):
        d = dict(call.data)
        entity = d.pop("entity_id", None)
        if isinstance(entity, list):
            entity = entity[0]
        self.calls.append((call.domain, call.service, entity, d))
        # The thermostat confirms what it was told, as Zigbee2MQTT would.
        if call.domain == "select":
            self.hass.states.async_set(entity, d["option"], self.hass.states.get(entity).attributes)
        elif call.domain == "number":
            self.hass.states.async_set(entity, str(d["value"]))

    def _count_run(self, _event):
        self.runs += 1

    def take(self):
        calls, runs = self.calls, self.runs
        self.calls, self.runs = [], 0
        return calls, runs

    def of(self, domain, calls=None):
        return [c for c in (self.calls if calls is None else calls) if c[0] == domain]

    # --- driving it ----------------------------------------------------

    def name(self, sel, family):
        """The value of a family (internal/external/offline) this thermostat uses."""
        old = self.names[sel] == OLD
        return {"internal": "internal" if old else "local_temperature",
                "external": "external" if old else "remote_temperature",
                "offline": "external_2" if old else "remote_source_offline"}[family]

    def stamp(self, at=None):
        at = at or datetime.now(UTC)
        return {"iso": lambda: at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "local": lambda: at.astimezone(ZoneInfo("Europe/Berlin")).isoformat(),
                "epoch": lambda: str(int(at.timestamp() * 1000))}[self.seen_format]()

    def beat(self, at=None):
        self.hass.states.async_set(SEEN, self.stamp(at))

    def set(self, entity, state, **attrs):
        old = self.hass.states.get(entity)
        self.hass.states.async_set(entity, state, attrs or (old.attributes if old else {}))

    async def settle(self):
        for _ in range(3):
            await asyncio.sleep(0)
            await self.hass.async_block_till_done()

    async def advance(self, minutes):
        """Move the clock minute by minute; the thermometer reports every 5."""
        for _ in range(minutes):
            self.clock.tick(timedelta(minutes=1))
            self.shift += 60
            self.minute += 1
            if self.heartbeat and self.minute % 5 == 0:
                self.beat()
            await self.settle()

    async def service(self, domain, service, data=None):
        await self.hass.services.async_call(domain, service, data or {}, blocking=True)
        await self.settle()

    async def stop(self):
        await self.hass.async_stop(force=True)
        self.clock_ctl.stop()


# --- the cases -------------------------------------------------------------

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f"\n       want {want!r}\n       got  {got!r}"))


def sends(calls):
    return sorted((c[2], c[3]["value"]) for c in calls if c[0] == "number")


def switches(calls):
    return sorted((c[2], c[3]["option"]) for c in calls if c[0] == "select")


def pushes(calls):
    return [c[3] for c in calls if c[0] == "notify"]


def customs(calls):
    return [c[3] for c in calls if c[0] == "test"]


def warnings(calls):
    return [c[3]["message"] for c in calls if c[0] == "system_log"]


def logbook(calls):
    return [c[3]["message"] for c in calls if c[0] == "logbook"]


async def outage(r):
    """Thermometer goes silent; returns the calls of the minute it counts as a failure."""
    r.heartbeat = False
    await r.advance(20)
    return r.take()


async def case_start_sends_once():
    r = await Room().start()
    calls, runs = r.take()
    check("HA start: one run, sends the temperature (last send unknown)", (runs, sends(calls)),
          (1, [(IN_A, 21.0), (IN_B, 21.0)]))
    check("HA start: nothing switched, no warning", (switches(calls), warnings(calls)), ([], []))
    await r.stop()


async def case_normal():
    r = await Room().start()
    r.take()
    await r.advance(45)
    check("normal operation, 45 min: no run", r.take(), ([], 0))
    await r.stop()


async def case_temperature_change():
    r = await Room().start()
    r.take()
    r.set(TEMP, "21.43")
    await r.settle()
    calls, runs = r.take()
    check("temperature change: one run, 21.4 to both", (runs, sends(calls)), (1, [(IN_A, 21.4), (IN_B, 21.4)]))
    await r.advance(10)
    check("thermostats took the value: no further run", r.take(), ([], 0))
    r.set(TEMP, "21.44")
    await r.settle()
    check("change below 0.1 °C: no run", r.take(), ([], 0))
    await r.stop()


async def case_one_thermostat_differs():
    r = await Room().start()
    r.take()
    r.set(IN_B, "19.5")
    await r.settle()
    calls, runs = r.take()
    check("one thermostat differs: current value to all", sends(calls), [(IN_A, 21.0), (IN_B, 21.0)])
    await r.stop()


async def resend_minutes(r, minutes):
    """Advance minute by minute; the minutes (since start) at which both were sent."""
    at = []
    for m in range(1, minutes + 1):
        await r.advance(1)
        calls, _ = r.take()
        if sends(calls) == [(IN_A, 21.0), (IN_B, 21.0)]:
            at.append(m)
        elif calls:
            at.append(("unexpected", m, calls))
    return at


async def case_resend(minutes):
    r = await Room(inputs={"resend_minutes": minutes}).start()
    r.take()  # the start sends too
    at = await resend_minutes(r, 3 * minutes)
    gaps = [b - a for a, b in zip([0] + at, at)] if all(isinstance(m, int) for m in at) else at
    check(f"resend {minutes} min: three sends in three intervals, none more than {minutes} min apart",
          (len(at), max(gaps) <= minutes if gaps else False), (3, True))
    await r.stop()


async def case_offline_alive(names):
    r = await Room(names=names).start()
    r.take()
    r.set(SEL_B, r.name(SEL_B, "offline"))
    await r.settle()
    calls, runs = r.take()
    check(f"offline reported ({names[2]}), thermometer alive: temperature sent",
          (runs, sends(calls), switches(calls)), (1, [(IN_A, 21.0), (IN_B, 21.0)], []))
    check("offline: logbook note, no notification",
          (len(logbook(calls)), pushes(calls), customs(calls)), (1, [], []))
    await r.stop()


async def case_outage(names, seen_format="iso"):
    r = await Room(names=names, seen_format=seen_format,
                   inputs={"notify_device": "PHONE", "notify_action": CUSTOM}).start()
    r.take()
    r.heartbeat = False
    await r.advance(19)
    check(f"[{seen_format}/{names[0]}] silent 19 min: nothing", r.take(), ([], 0))
    await r.advance(1)
    calls, runs = r.take()
    internal = r.name(SEL_A, "internal")
    check(f"[{seen_format}/{names[0]}] silent 20 min: both to {internal}",
          (runs, switches(calls), sends(calls)), (1, [(SEL_A, internal), (SEL_B, internal)], []))
    check(f"[{seen_format}/{names[0]}] outage notified",
          customs(calls), [{"room": "Living room", "source": "internal", "reason": "outage", "silence_minutes": 20}])
    await r.advance(30)
    check(f"[{seen_format}/{names[0]}] during the outage: no run", r.take(), ([], 0))

    r.heartbeat = True
    r.beat()
    await r.settle()
    calls, runs = r.take()
    external = r.name(SEL_A, "external")
    check(f"[{seen_format}/{names[0]}] thermometer back: to {external}, temperature sent",
          (switches(calls), sends(calls)), ([(SEL_A, external), (SEL_B, external)], [(IN_A, 21.0), (IN_B, 21.0)]))
    check(f"[{seen_format}/{names[0]}] recovery notified",
          customs(calls), [{"room": "Living room", "source": "external", "reason": "recovered", "silence_minutes": 0}])
    await r.stop()


async def case_offline_during_outage():
    r = await Room().start()
    r.take()
    await outage(r)
    r.set(SEL_B, "external_2")
    await r.settle()
    calls, _ = r.take()
    check("offline reported during an outage: back to internal, nothing sent",
          (switches(calls), sends(calls)), ([(SEL_B, "internal")], []))
    await r.stop()


async def case_manual():
    r = await Room(inputs={"notify_action": CUSTOM}).start()
    r.take()
    await r.advance(3)
    r.set(SEL_A, "internal")
    await r.settle()
    calls, runs = r.take()
    check("manual switch to internal: switched back, sent",
          (runs, switches(calls), sends(calls)), (1, [(SEL_A, "external")], [(IN_A, 21.0), (IN_B, 21.0)]))
    check("manual: reason manual", [c["reason"] for c in customs(calls)], ["manual"])
    await r.stop()


async def case_z2m_restart():
    r = await Room().start()
    r.take()
    last = datetime.now(UTC)
    r.beat(last)
    await r.settle()
    r.heartbeat = False
    await r.advance(1)
    r.set(SEEN, "unavailable")
    await r.advance(53)
    check("Zigbee2MQTT down 54 min, last seen unavailable: nothing", r.take(), ([], 0))
    r.beat(last)  # Zigbee2MQTT restores the old time stamp
    await r.advance(19)
    check("old time stamp restored: no switch for a failure limit", r.take(), ([], 0))
    await r.advance(1)
    calls, _ = r.take()
    check("still silent a failure limit after the restore: outage",
          switches(calls), [(SEL_A, "internal"), (SEL_B, "internal")])
    await r.stop()


async def case_last_seen_unavailable():
    r = await Room().start()
    r.take()
    r.heartbeat = False
    r.set(SEEN, "unavailable")
    await r.advance(120)
    check("last seen unavailable for 2 h: state unknown, nothing done", r.take(), ([], 0))
    r.set(SEL_A, "internal")
    await r.settle()
    check("unknown: not even a manual switch is undone", r.take(), ([], 0))
    await r.stop()


async def case_unreachable():
    r = await Room().start()
    r.take()
    r.set(IN_B, "unavailable")
    r.set(SEL_B, "unavailable")
    await r.settle()
    check("thermostat goes unreachable: no run", r.take(), ([], 0))
    r.set(TEMP, "22.0")
    await r.settle()
    check("temperature change: only the reachable one", sends(r.take()[0]), [(IN_A, 22.0)])
    r.set(SEL_B, "external")
    r.set(IN_B, "21.0")
    await r.settle()
    check("reachable again with the old value: caught up", sends(r.take()[0]), [(IN_A, 22.0), (IN_B, 22.0)])

    r.set(IN_B, "unavailable")
    r.set(SEL_B, "unavailable")
    await r.settle()
    calls, _ = await outage(r)
    check("outage: the unreachable one is skipped", switches(calls), [(SEL_A, "internal")])
    r.set(SEL_B, "external")
    r.set(IN_B, "22.0")
    await r.settle()
    calls, _ = r.take()
    check("reachable again during the outage: to internal, reason reconcile",
          (switches(calls), [m for m in logbook(calls) if "reconcile" in m] != []),
          ([(SEL_B, "internal")], True))
    await r.stop()


async def case_reachable_again_internal():
    r = await Room(inputs={"notify_action": CUSTOM}).start()
    r.take()
    r.set(SEL_B, "unavailable")
    await r.settle()
    r.set(SEL_B, "internal")
    await r.settle()
    calls, _ = r.take()
    check("reachable again on internal while alive: to external, reason reconcile",
          (switches(calls), [c["reason"] for c in customs(calls)]), ([(SEL_B, "external")], ["reconcile"]))
    await r.stop()


async def case_start_reconcile():
    r = await Room(sources=("internal", "external"), inputs={"notify_action": CUSTOM}).start()
    calls, runs = r.take()
    check("HA start with one on internal: one run, back to external",
          (runs, switches(calls)), (1, [(SEL_A, "external")]))
    check("HA start: reason reconcile", [c["reason"] for c in customs(calls)], ["reconcile"])
    await r.stop()


async def case_start_during_outage():
    def silent(r):
        r.heartbeat = False
        r.beat(START - timedelta(minutes=30))
    r = await Room().start(before_start=silent)
    calls, _ = r.take()
    check("HA start, thermometer silent 30 min but just restored: nothing",
          (switches(calls), sends(calls)), ([], []))
    await r.advance(20)
    check("... a failure limit later: outage", switches(r.take()[0]), [(SEL_A, "internal"), (SEL_B, "internal")])
    await r.stop()


async def case_enable():
    r = await Room(inputs={"notify_action": CUSTOM}).start()
    r.take()
    await r.service("automation", "turn_off", {"entity_id": "automation.guard"})
    r.set(SEL_B, "internal")
    await r.settle()
    check("automation off: nothing happens", r.take(), ([], 0))
    await r.service("automation", "turn_on", {"entity_id": "automation.guard"})
    calls, runs = r.take()
    check("turned on: one run, back to external, reason reconcile",
          (runs, switches(calls), [c["reason"] for c in customs(calls)]),
          (1, [(SEL_B, "external")], ["reconcile"]))
    await r.stop()


async def case_reload():
    r = await Room(inputs={"suffix_sensor_source": "_wrong"}).start()
    calls, _ = r.take()
    check("wrong suffix: warning per thermostat, nothing switched",
          (len(warnings(calls)), switches(calls), sends(calls)), (2, [], []))
    r.set(SEL_A, "internal")
    r.set(TEMP, "23.0")
    await r.settle()
    check("wrong suffix: no run on changes", r.take(), ([], 0))
    r.inputs = {}
    r.write_automation()
    await r.service("automation", "reload")
    calls, runs = r.take()
    check("fixed and saved: one run, switched and sent",
          (runs, switches(calls), sends(calls)), (1, [(SEL_A, "external")], [(IN_A, 23.0), (IN_B, 23.0)]))
    await r.service("automation", "reload")
    check("reloaded again unchanged: no run", r.take(), ([], 0))
    await r.stop()


async def case_created():
    r = await Room(created_later=True, sources=("internal", "external")).start()
    check("no automation yet: nothing", r.take(), ([], 0))
    r.write_automation()
    await r.service("automation", "reload")
    calls, runs = r.take()
    check("automation created: one run, switched and sent",
          (runs, switches(calls), sends(calls)), (1, [(SEL_A, "external")], [(IN_A, 21.0), (IN_B, 21.0)]))
    at = await resend_minutes(r, 60)
    check("created: resend works without a restart", len(at), 1)
    await r.stop()


async def case_mixed_names():
    r = await Room(names=OLD, trv_b_names=NEW, sources=("internal", "external")).start()
    calls, _ = r.take()
    check("old and new names in one room: each gets its own", switches(calls), [(SEL_A, "external")])
    r.set(SEL_B, "local_temperature")
    await r.settle()
    check("new name local_temperature counts as internal", switches(r.take()[0]), [(SEL_B, "remote_temperature")])
    calls, _ = await outage(r)
    check("outage: internal / local_temperature", switches(calls), [(SEL_A, "internal"), (SEL_B, "local_temperature")])
    await r.stop()


async def case_missing_and_duplicate():
    r = await Room(trv_b_suffixes=("external_temperature_input", "sensor_choice")).start()
    calls, _ = r.take()
    w = warnings(calls)
    check("thermostat without a source entity: one warning naming it",
          (len(w), "trv_b" in w[0] and "_temperature_sensor_select" in w[0] if w else False), (1, True))
    check("... and nothing done", (switches(calls), sends(calls)), ([], []))
    await r.stop()

    r = await Room(thermometer_extra=["device_temperature"]).start()
    calls, _ = r.take()
    w = warnings(calls)
    check("thermometer with two temperature sensors: one warning naming both",
          (len(w), "thermometer_device_temperature" in w[0] if w else False), (1, True))
    await outage(r)
    check("... and no outage switch either", switches(r.take()[0]), [])
    await r.stop()


async def case_thermometer_is_trv():
    r = await Room(thermometer_is_trv=True).start()
    calls, _ = r.take()
    w = warnings(calls)
    check("thermostat picked as thermometer: warning, nothing done",
          (len(w), "TRVZB" in w[0] if w else False, switches(calls), sends(calls)), (1, True, [], []))
    r.set(SEL_A, "internal")
    await r.settle()
    check("... and no run afterwards", r.take(), ([], 0))
    await r.stop()


async def case_long_limits():
    r = await Room(inputs={"failure_minutes": 120, "resend_minutes": 150}).start()
    calls, _ = r.take()
    w = warnings(calls)
    check("120 / 150 min: two warnings", (len(w), "120" in w[0], "150" in w[1]), (2, True, True))
    r.heartbeat = False
    await r.advance(119)
    check("... but the values are used: nothing at 119 min", switches(r.take()[0]), [])
    await r.advance(1)
    check("... outage at 120 min", switches(r.take()[0]), [(SEL_A, "internal"), (SEL_B, "internal")])
    await r.stop()


async def case_notifications():
    both = {"notify_device": "PHONE", "notify_action": CUSTOM}
    for label, inputs, switch, want_push, want_custom in [
        ("device only", {"notify_device": "PHONE"}, None, 1, 0),
        ("custom action only", {"notify_action": CUSTOM}, None, 0, 1),
        ("both", both, None, 1, 1),
        ("both, switch on", both | {"notify_switch": "input_boolean.push"}, "on", 1, 1),
        ("both, switch off", both | {"notify_switch": "input_boolean.push"}, "off", 0, 0),
        ("none", {}, None, 0, 0),
    ]:
        r = await Room(inputs=inputs).start(
            before_start=lambda r: switch and r.hass.states.async_set("input_boolean.push", switch))
        r.take()
        calls, _ = await outage(r)
        check(f"notify {label}: push {want_push}, custom {want_custom}, logbook always",
              (len(pushes(calls)), len(customs(calls)), len(logbook(calls)), len(switches(calls))),
              (want_push, want_custom, 1, 2))
        await r.stop()


async def case_notify_texts():
    r = await Room(inputs={"notify_device": "PHONE"}).start()
    r.take()
    calls, _ = await outage(r)
    check("device push: default English texts with room and minutes", pushes(calls), [{
        "title": "Living room: thermostat sensor",
        "message": "Room thermometer silent for 20 min. The thermostats now use their own sensor."}])
    await r.stop()

    r = await Room(inputs={"notify_device": "PHONE", "room_name": "Lounge",
                           "notify_title": "{{ room }} / {{ reason }}",
                           "notify_message_internal": "{{ source }} after {{ silence_minutes }}"}).start()
    r.take()
    calls, _ = await outage(r)
    check("own texts and room name", pushes(calls), [{"title": "Lounge / outage", "message": "internal after 20"}])
    await r.stop()

    r = await Room(area=None, inputs={"notify_action": CUSTOM}).start()
    r.take()
    calls, _ = await outage(r)
    check("no area: device name as room", [c["room"] for c in customs(calls)], ["thermometer"])
    await r.stop()


async def main():
    await case_start_sends_once()
    await case_normal()
    await case_temperature_change()
    await case_one_thermostat_differs()
    await case_resend(60)
    await case_resend(90)
    await case_offline_alive(OLD)
    await case_offline_alive(NEW)
    await case_outage(OLD)
    await case_outage(NEW)
    await case_outage(OLD, "local")
    await case_outage(OLD, "epoch")
    await case_offline_during_outage()
    await case_manual()
    await case_z2m_restart()
    await case_last_seen_unavailable()
    await case_unreachable()
    await case_reachable_again_internal()
    await case_start_reconcile()
    await case_start_during_outage()
    await case_enable()
    await case_reload()
    await case_created()
    await case_mixed_names()
    await case_missing_and_duplicate()
    await case_thermometer_is_trv()
    await case_long_limits()
    await case_notifications()
    await case_notify_texts()
    print()
    print(f"{len(FAILS)} failed" if FAILS else "all as expected")
    sys.exit(1 if FAILS else 0)


asyncio.run(main())
