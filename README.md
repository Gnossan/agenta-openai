# Home AI — AI-Assisted Home Automation

A personal learning project that connects Home Assistant to Claude (Anthropic) via a Flask-based add-on, enabling natural language control of smart home devices.

## What it does

Home AI lets you chat with your home in natural language. Instead of tapping buttons in an app, you can ask things like:

- *"Which lights are on right now?"*
- *"Turn off everything in the office"*
- *"Dim the floor lamp to 50%"*
- *"Set the bedroom lights to warm white"*
- *"Which devices haven't been used in a while?"*

The assistant uses Claude to reason about your devices and can fetch real-time status, turn devices on/off, adjust brightness, color temperature, and RGB color.

## Architecture

```
Home Assistant OS (HAOS)
└── Home AI Add-on (Docker container)
    ├── Flask web server (chat UI + webhook)
    ├── HA REST API client (reads/controls devices)
    └── Anthropic API (Claude, natural language reasoning)
```

The add-on runs natively inside HAOS and is accessible via:
- Local network: `http://<ha-ip>:5001`
- Remote (via Nabu Casa): through HA's sidebar panel

## Features

- **Natural language chat** — ask questions about your home in plain language
- **Real-time device status** — uses function calling so Claude fetches live state on demand
- **Device control** — turn on/off, dim, change color temperature and RGB
- **Web UI** — simple chat interface accessible from mobile
- **HA Add-on** — runs inside HAOS, starts automatically, no separate server needed
- **Nabu Casa support** — accessible remotely via ingress

## Device support

Currently supports `light` and `switch` domains from Home Assistant. Tested with:
- IKEA Dirigera (via Matter)
- Shelly switches (local WiFi)
- Tuya devices (cloud WiFi)

## Setup

### Requirements

- Home Assistant OS (HAOS)
- Nabu Casa subscription (optional, for remote access)
- Anthropic API key

### Installation

1. Copy the add-on folder to `/addons/homeai` via Samba
2. In HA: **Settings → Add-ons → Add-on Store → Reload**
3. Install **Home AI** from the local add-ons section
4. Go to the **Configuration** tab and fill in:
   - `secret` — your webhook token
   - `ha_url` — e.g. `http://homeassistant.local:8123`
   - `ha_token` — a Long-Lived Access Token from your HA profile
   - `anthropic_api_key` — your Anthropic API key
5. Start the add-on

### Local development (Mac/Linux)

Create a `.env` file in the project folder:

```
SECRET=your_webhook_token
HA_URL=http://homeassistant.local:8123
HA_TOKEN=your_ha_token
ANTHROPIC_API_KEY=your_anthropic_key
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run:

```bash
python ha_reader.py
```

This starts both a terminal chat loop and a Flask server on port 5001.

## Project structure

```
homeai/
├── ha_reader.py       # Main application
├── config.json        # HAOS add-on configuration
├── Dockerfile         # Container definition
└── requirements.txt   # Python dependencies
```

## Motivation

This project was built primarily as a learning exercise — to understand how AI, APIs, smart home protocols, and containerization fit together. It is intentionally kept simple and incremental.

## Roadmap / known limitations

- [ ] Session management (currently all users share the same conversation history)
- [ ] Authentication on the `/chat` endpoint
- [ ] Support for more device types (climate, sensors, media players)
- [x] Persistent conversation history across restarts
- [ ] GitHub-based add-on repository (instead of manual Samba copy)
