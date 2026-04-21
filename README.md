# Home AI — AI-Assisted Home Automation

A personal learning project that connects Home Assistant to an AI assistant (OpenAI or Anthropic Claude) via a Flask-based add-on, enabling natural language control and awareness of smart home devices.

## What it does

Home AI lets you chat with your home in natural language. Instead of tapping buttons in an app, you can ask things like:

- *"Which lights are on right now?"*
- *"Turn off everything in the office"*
- *"Dim the floor lamp to 50%"*
- *"Set the bedroom lights to warm white"*
- *"What happened at home around 5 PM today?"*
- *"What usually happens on Friday evenings?"*

The assistant uses an AI model to reason about your devices, fetch real-time status, control lights, and — over time — recognize patterns in how your home is used.

## Architecture

```
Home Assistant OS (HAOS)
├── Home AI Add-on (Docker container)
│   ├── Flask web server (chat UI + webhook)
│   ├── HA REST API client (reads/controls devices)
│   ├── HA WebSocket client (listens for real-time state changes)
│   └── AI API (OpenAI or Anthropic, natural language reasoning)
└── Qdrant Add-on (Docker container)
    └── Vector database (stores home event history with embeddings)
```

The system is accessible via:
- Local network: `http://<ha-ip>:5003`
- Remote (via Nabu Casa): through HA's sidebar panel

## Features

- **Natural language chat** — ask questions about your home in plain language
- **Real-time device status** — uses function calling so the AI fetches live state on demand
- **Device control** — turn on/off, dim, change color temperature and RGB
- **Event history** — home events are logged to a vector database and searchable via natural language
- **Pattern recognition** — ask what usually happens at certain times or days
- **Persistent memory** — explicitly tell the assistant things to remember across sessions
- **Session management** — each browser session maintains its own conversation history
- **Web UI** — simple chat interface accessible from mobile
- **HAOS Add-on** — runs inside HAOS, starts automatically, no separate server needed
- **Nabu Casa support** — accessible remotely via ingress

## Device support

Currently supports `light` and `switch` domains from Home Assistant, plus sensors, person trackers and device trackers for event logging. Tested with:

- IKEA Dirigera (via Matter)
- Shelly switches (local WiFi)
- Tuya devices (cloud WiFi)

## Repository structure

This project consists of two repositories:

- **agenta-openai** — The Home AI add-on (OpenAI version)
- **agenta** — The Home AI add-on (Anthropic/Claude version)
- **qdrant-addon** — The Qdrant vector database add-on

## Setup

### Requirements

- Home Assistant OS (HAOS)
- Nabu Casa subscription (optional, for remote access)
- OpenAI API key (or Anthropic API key for the Claude version)

### Installation

1. In HA: **Settings → Add-ons → Add-on Store → Repositories**
2. Add `https://github.com/Gnossan/qdrant-addon` and install **Qdrant**
3. Add `https://github.com/Gnossan/agenta-openai` and install **Home AI**
4. Go to the **Configuration** tab for Home AI and fill in:
   - `secret` — your webhook token
   - `ha_url` — e.g. `http://homeassistant.local:8123`
   - `ha_token` — a Long-Lived Access Token from your HA profile
   - `openai_api_key` — your OpenAI API key
   - `qdrant_host` — IP address of your HAOS machine, e.g. `192.168.1.x`
   - `qdrant_port` — `6333` (default)
5. Start both add-ons

### Local development (Mac/Linux)

Create a `.env` file in the project folder:

```
SECRET=your_webhook_token
HA_URL=http://homeassistant.local:8123
HA_TOKEN=your_ha_token
OPENAI_API_KEY=your_openai_key
MODEL=gpt-4o-mini
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

Install dependencies and start Qdrant via Docker:

```bash
pip install -r requirements.txt
docker run -d --name qdrant -p 6333:6333 -v ~/qdrant_data:/qdrant/storage qdrant/qdrant
python ha_reader.py
```

## Motivation

This project was built primarily as a learning exercise — to understand how AI, APIs, smart home protocols, containerization, vector databases, and embeddings fit together. It is intentionally kept simple and incremental. The process of building matters as much as the outcome.

## Roadmap / known limitations

- [ ] Authentication on the `/chat` endpoint
- [ ] Support for more device types (climate, sensors, media players)
- [ ] Fuzzy matching for memory keys
- [ ] Migrate memory storage to vector database for semantic retrieval
- [ ] GitHub-based CI/CD pipeline (dev → staging → prod)
- [ ] ESPHome integration (mmWave presence detection, light sensors)
- [ ] Autonomous agent behaviors based on learned patterns
