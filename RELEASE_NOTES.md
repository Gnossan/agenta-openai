# Release Notes
## v0.5.3 — Preparation for PWA - "app"
*2026-04-21*
## v0.5.2 — New chat layout
*2026-04-21*
## v0.5.1 — Change of port to 5002
*2026-04-21*
## v0.5.0 — Vector Database & Event History
*2026-04-21*

### What's new
- Home events are now logged in real-time to a Qdrant vector database via Home Assistant's WebSocket API
- The assistant can answer natural language questions about what has happened in the home — e.g. "what happened around 5 PM today?" or "what usually happens on Friday evenings?"
- Qdrant runs as a separate, dedicated HAOS add-on (`qdrant-addon`)
- WebSocket listener runs in a background thread alongside Flask, so a single add-on handles both chat and event logging
- Event descriptions include full date, weekday and time for meaningful pattern recognition over time

### Technical details
- Events are embedded using `text-embedding-3-small` and stored in Qdrant with metadata (entity_id, state, timestamp)
- `search_events` tool added to the AI function-calling toolset
- `ensure_collection()` initializes the Qdrant collection at startup
- Qdrant host and port are configurable via `config.json` options
- State change deduplication prevents redundant logging of repeated states for lights and switches
- Power and energy sensors filtered out to reduce noise

---

## v0.4.0 — Change to OpenAI platform for lower costs
*2026-04-06*

### What's new
- The AI model can now be selected from the add-on's configuration page without requiring a code change or version update.

### Technical details
- Model is read from `/data/options.json` at startup (HAOS) or from the `MODEL` environment variable (local development)
- Falls back to the default model if not configured

---

## v0.3.2 — Model update
*2026-04-06*

- Switched to `claude-haiku-4-5-20251001`

---

## v0.3.0 — Session Management
*2026-04-06*

### What's new
- Each user now gets their own conversation history. Opening the chat in multiple browser windows or devices no longer results in shared context.

### Technical details
- Session IDs are generated client-side using `Math.random()` and sent with each `/chat` request
- Flask maintains a `sessions` dictionary mapping session IDs to individual conversation histories

---

## v0.2.0 — HAOS Add-on & Remote Access
*2026-04-06*

### What's new
- Packaged as a native Home Assistant OS add-on (Docker container)
- Accessible via Nabu Casa remote URL through HA ingress
- Add-on available as a custom GitHub repository — update directly from HA's add-on store
- Switched AI backend from OpenAI to Anthropic (Claude)
- Web chat interface accessible from mobile browser
- Add-on panel added to HA sidebar

### Technical details
- HAOS secrets managed via `config.json` options instead of `.env`
- Ingress support added with `panel_icon` and `panel_title`
- Flask runs in main thread when inside container, with terminal chat loop for local development
- Relative fetch path (`chat` instead of `/chat`) required for ingress routing

---

## v0.1.0 — Foundation
*2026-03-28*

### What's new
- Flask webhook server receiving button triggers
- OpenAI integration with basic yes/no toggle logic
- Home Assistant REST API integration for reading device states
- Devices filtered to `light` and `switch` domains
- Device context (name, entity_id, last_changed) saved to `devices.json` at startup
- Terminal chat loop for local testing
- Secrets managed via `.env` file
- Function calling for real-time device state (`get_device_state`)
- Device control (`set_device_state`) with support for:
  - on/off
  - brightness (0–255)
  - color temperature (Kelvin)
  - RGB color
