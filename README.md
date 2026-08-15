# Home Assistant Blueprints

Collection of automation blueprints for Home Assistant.
One folder per blueprint — each has its own README.

| Blueprint | What it does | |
|---|---|---|
| [Alarmo Link](alarmo-link/) | Arm and disarm Alarmo from a private link — no HA account, no app | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FHubEight%2Fhome-assistant-blueprints%2Fblob%2Fmain%2Falarmo-link%2Falarmo_link.yaml) |
| [Radiator Fan Controller](radiator-fan-controller/) | Temperature-driven radiator fan with hysteresis and window contacts | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FHubEight%2Fhome-assistant-blueprints%2Fblob%2Fmain%2Fradiator-fan-controller%2Fradiator_fan_controller.yaml) |

## Checks

Run before committing, or let the `checks` workflow do it on push:

```bash
node tools/check-version.js       # each blueprint's files agree on a version
node tools/test-alarmo-link.js    # logic inside alarmo-link.html
```

Plain Node, no dependencies, no `package.json` — clone and run.

One more needs Home Assistant itself, so run it wherever Home Assistant is
importable rather than on a bare machine:

```bash
python3 tools/test-radiator-fan-controller.py
```

It runs the blueprint's action script through Home Assistant's script engine
and checks what it switches. That is how the 1.1.4 bug was found — reading the
YAML did not show it.

## Support

Bug? Idea? → [Open an issue](https://github.com/HubEight/home-assistant-blueprints/issues)

## License

MIT License – use and modify freely!
