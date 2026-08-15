# Alarmo Link

Arm and disarm [Alarmo](https://github.com/nielsfaber/alarmo) from a private
link — no Home Assistant account, no app, no login.  
**Version 1.3.0 – the link can carry the name of the alarm**

For the people who live in your home but do not use Home Assistant, and for
cleaners or house sitters who should be able to set the alarm and nothing else.
They get a URL. It looks like this on their phone:

```
┌────────────────────────┐
│          Flat          │
│                        │
│   🔒      Arm          │
│                        │
│   🔓     Disarm        │
│                        │
│   Arm command sent     │
└────────────────────────┘
```

Add someone → create an automation from this blueprint.
Remove someone → delete it. Their link dies instantly, nobody else is affected.

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FHubEight%2Fhome-assistant-blueprints%2Fblob%2Fmain%2Falarmo-link%2Falarmo_link.yaml)

## Requirements

- [Alarmo](https://github.com/nielsfaber/alarmo) with at least one user who has a code
- Home Assistant 2024.10 or newer
- Home Assistant reachable from outside your network, over HTTPS

## Installation

**Two parts.** The blueprint handles the webhooks; the page is what people tap.
Neither works alone.

1. **The page** — copy `alarmo-link.html` to `config/www/alarmo-link.html`.
   Create the `www` folder if it does not exist, then restart Home Assistant
   (only needed the first time you create `www`).

2. **The blueprint** — click the badge above, or import from
   `https://github.com/HubEight/home-assistant-blueprints/blob/main/alarmo-link/alarmo_link.yaml`

## Adding a person

1. In Alarmo, create a user with their own code (**Alarmo → Users**).
   Give every person a distinct code — Alarmo's history names the user that the
   code belongs to, so a shared code names the wrong one.

2. Open `https://<your-ha-url>/local/alarmo-link.html` — with no `#` in the
   address. That is the setup screen. Name the alarm if you like, then press
   **Generate IDs**.

   ```
   ┌──────────────────────────────────────┐
   │ Alarmo Link – Setup                  │
   │                                      │
   │ NAME OF THIS ALARM (OPTIONAL)        │
   │ [ Flat                             ] │
   │                                      │
   │        [  Generate IDs  ]            │
   │                                      │
   │ WEBHOOK ID – ARM                     │
   │ nsK1FFGlxf1r9ydg0LtRn0mJv1eUOKyY     │
   │                                      │
   │ WEBHOOK ID – DISARM                  │
   │ Pcl1LYdYV4d6rwz2F9nZYflhfd7Q_uZv     │
   │                                      │
   │ LINK FOR THIS PERSON                 │
   │ https://ha.example.com/local/alarmo- │
   │ link.html#nsK1FFGl…,Pcl1LYdY…,Flat   │
   │                                      │
   │        [   Copy link    ]            │
   └──────────────────────────────────────┘
   ```

   Each ID has a small copy icon next to it, and the link has its own button.

3. **Settings → Automations → Create Automation → From blueprint → Alarmo Link.**
   Fill in the name, the Alarmo code, and paste the two generated IDs. Save.

4. Send the person the link. On iOS and Android, *Add to Home Screen* turns it
   into a full-screen icon.

To remove someone, delete their automation. To give someone a fresh link,
generate a new pair and replace both IDs in their automation.

## Security

**The link is the password.** There is no login — holding the URL is what grants
access. Treat it like a house key: send it over a channel you trust, and serve
Home Assistant over HTTPS so it is not readable in transit.

Some deliberate choices behind that:

- **The IDs live in the URL fragment** (after `#`). Browsers never send the
  fragment to the server, so the IDs stay out of access logs and proxy logs.
- **The IDs are generated in your browser** with `crypto.getRandomValues`, a
  cryptographic random source. 32 characters from a 64-character alphabet —
  192 bits. Nothing is transmitted while you generate them.
- **The webhooks accept POST only.** Messengers fetch URLs to build link
  previews; a GET webhook would trip the alarm the moment you sent the link.
- **No API token in the page.** That is why it reports *"Arm command sent"*
  rather than the alarm's real state — showing real state would need a token,
  which is full access to Home Assistant. Use the blueprint's notification
  instead: it reports what the panel actually did, two seconds later.

The page never learns your codes, and it holds no credentials.

## Options

The first six inputs are grouped into three sections; the notification field
sits below them.

| Section | Input | | |
|---|---|---|---|
| **Person** | Name | required | Shown in the notification, so you can tell who switched the alarm |
| | Alarmo code | required | The code of the Alarmo user these actions are booked under |
| **Link** | Webhook ID – arm | required | From the setup screen, or your own random string |
| | Webhook ID – disarm | required | Must differ from the one above |
| **Alarm** | Alarm panel | required | Your Alarmo `alarm_control_panel` entity |
| | Arm mode | optional | Away, Home or Night — default Away |
| _(no section)_ | Notification | optional | Reports the real state two seconds after the command |

Leave a required field empty and Home Assistant refuses to save with
`Message malformed: Missing input …`. Home Assistant has no way to mark fields
as required in the form itself, so the blueprint says so in each label.

## Language

The page follows the browser's language setting. English and German ship with
it; anything else gets English.

To add a language, copy the `en` block in `alarmo-link.html` and translate the
values — the keys are what the markup refers to:

```js
var STRINGS = {
  en: { … },
  de: { … },
  nl: { arm: '🔒 Inschakelen', … }
};
```

Two things stay untranslated on purpose: the heading of the button page, which
is a name you supply, and the blueprint itself, since Home Assistant has no way
for a blueprint to ship translations.

## Troubleshooting

**"Did not work – please call"** — the automation is disabled or deleted, or the
webhook ID does not match. Check that the automation exists and is on.

**Nothing happens, no error** — the Alarmo code is wrong, or that user is not
allowed to arm or disarm. Alarmo logs the rejection in its own history.

**The alarm switches but no notification arrives** — check the log for
`Can't parse entities`. A Telegram bot set to a Markdown parser chokes on
formatting characters in the message; this blueprint avoids them, but the name
you enter is passed through as you type it, so avoid `_`, `*` and `` ` `` in it.

**The link works at home but not outside** — Home Assistant is not reachable
from the internet, or a reverse proxy is blocking `/api/webhook/`.

**Setup screen instead of the buttons** — the `#` part of the link is missing or
truncated. Messengers sometimes cut long URLs; send it as plain text.

## Changelog

### 1.3.0

- The setup screen has an optional **Name of this alarm** field. It becomes a
  third value in the link, and the button page shows it as its heading and its
  tab title. One copy of the page now serves any number of alarms — previously
  the heading had to be edited in the file, so a second alarm meant a second
  copy. Links without a name keep working

### 1.2.0

- **Fixed: no notification when arming, if the target was a Telegram bot.**
  Alarm states contain an underscore (`armed_home`), Telegram's default
  Markdown parser read it as an unclosed italic marker and rejected the whole
  message with `Can't parse entities`. `notify.send_message` passes only
  message and title, so the parser cannot be switched off from a blueprint —
  the message now strips underscores instead: `armed home`
- The page follows the browser language. English and German are included;
  anything else falls back to English

### 1.1.1

- The blueprint is now called `🔒 Alarmo Link`. Blueprints have no icon field —
  an emoji at the start of the name is how it is done
- The notification field is no longer inside a section. Home Assistant renders
  every section as an expansion panel whose header can always be clicked shut,
  and `collapsed` only sets the initial state — so the one option most people
  should set could be hidden by accident. It is now a plain field below the
  sections
- Dropped the note about naming the automation. Whether Home Assistant asks for
  a name depends on where you start from, so the note was wrong as often as it
  was right

### 1.1.0

- Each webhook ID on the setup screen has its own copy icon — previously only
  the finished link could be copied, the IDs had to be selected by hand
- The fallback for browsers without the clipboard API (plain HTTP, `file://`)
  now covers all three copy actions instead of only the link
- The Notification section is shown expanded like the other three. It was the
  only collapsed one, which hid the option most people should set

### 1.0.0

- First release

## Support

Bug? Idea? → [Open an issue on GitHub](https://github.com/HubEight/home-assistant-blueprints/issues)
