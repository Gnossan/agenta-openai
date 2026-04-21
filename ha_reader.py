# ─────────────────────────────────────────
# Imports
# ─────────────────────────────────────────
from flask import Flask, request
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import requests
import json
import os
import threading
import logging
import sys
import asyncio
import websockets
import uuid
from datetime import datetime
from openai import OpenAI

load_dotenv()

aapp = Flask(__name__, static_folder='static')

# ─────────────────────────────────────────
# Konfiguration
# ─────────────────────────────────────────
MODEL = os.getenv("MODEL", "gpt-5.4-mini")
OPTIONS_FILE = "/data/options.json"
if os.path.exists(OPTIONS_FILE):
    with open(OPTIONS_FILE) as f:
        options = json.load(f)
    SECRET = options.get("secret")
    HA_URL = options.get("ha_url")
    HA_TOKEN = options.get("ha_token")
    os.environ["OPENAI_API_KEY"] = options.get("openai_api_key", "")
    MODEL = options.get("model", "gpt-5.4-mini")
else:
    load_dotenv()
    SECRET = os.getenv("SECRET")
    HA_URL = os.getenv("HA_URL")
    HA_TOKEN = os.getenv("HA_TOKEN")

HA_HEADERS = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json",
}

WS_URL = HA_URL.replace("http://", "ws://") + "/api/websocket"

DEVICES_FILE = "devices.json"
MEMORY_FILE = "/share/memory.json"
conversation_history = []
sessions = {}
previous_states = {}

client = OpenAI()
QDRANT_HOST = options.get("qdrant_host", "localhost") if os.path.exists(OPTIONS_FILE) else os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(options.get("qdrant_port", 6333) if os.path.exists(OPTIONS_FILE) else os.getenv("QDRANT_PORT", 6333))

qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)



TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_device_state",
            "description": "Hämtar aktuell status för en enhet i hemmet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Enhetens entity_id, t.ex. light.golvlampa_i_kontoret"
                    }
                },
                "required": ["entity_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_device_state",
            "description": "Tänder eller släcker en enhet i hemmet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Enhetens entity_id, t.ex. light.golvlampa_i_kontoret"
                    },
                    "state": {
                        "type": "string",
                        "enum": ["on", "off"],
                        "description": "Önskat tillstånd, on eller off"
                    },
                    "brightness": {
                        "type": "integer",
                        "description": "Ljusstyrka mellan 0 och 255, används bara när state är on"
                    },
                    "color_temp": {
                        "type": "integer",
                        "description": "Färgtemperatur i Kelvin. Varmt ljus ca 2700K, neutralt ca 4000K, kallt ca 6000K."
                    },
                    "rgb_color": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "RGB-färg som en lista med tre värden [röd, grön, blå], varje värde mellan 0 och 255. T.ex. [255, 0, 0] för röd."
                    }
                },
                "required": ["entity_id", "state"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Sparar information som användaren explicit bett om att komma ihåg.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "En kort beskrivande nyckel på engelska i snake_case, t.ex. 'dog_name' eller 'wake_time_weekdays'"
                    },
                    "value": {
                        "type": "string",
                        "description": "Informationen som ska sparas"
                    }
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_memory",
            "description": "Hämtar sparad information när användaren antyder att agenten ska eller kan känna till något.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Nyckeln för informationen som ska hämtas"
                    }
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_events",
            "description": "Söker i hemhändelsehistoriken efter mönster och beteenden baserat på en fråga på naturligt språk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "En fråga på naturligt språk, t.ex. 'vad händer på torsdagskvällar?' eller 'när brukar sovrumslampan tändas?'"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

# Loggning
logging.basicConfig(
    filename="ha_reader.log",
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def handle_exception(exc_type, exc_value, exc_traceback):
    logging.error("Okantad krasch", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception

# ─────────────────────────────────────────
# HA-funktioner
# ─────────────────────────────────────────
def get_device_context():
    r = requests.get(
        f"{HA_URL}/api/states",
        headers=HA_HEADERS
    )
    all_states = r.json()
    devices = []
    for entity in all_states:
        entity_id = entity["entity_id"]
        domain = entity_id.split(".")[0]
        if domain not in ["light", "switch"]:
            continue
        devices.append({
            "name": entity["attributes"].get("friendly_name", entity_id),
            "entity_id": entity_id,
            "last_changed": entity["last_changed"]
        })
    return devices

def get_device_state(entity_id):
    r = requests.get(
        f"{HA_URL}/api/states/{entity_id}",
        headers=HA_HEADERS
    )
    data = r.json()
    return data.get("state", "okänd")

def save_device_context():
    devices = get_device_context()
    with open(DEVICES_FILE, "w", encoding="utf-8") as f:
        json.dump(devices, f, indent=2, ensure_ascii=False)
    print(f"Sparade {len(devices)} enheter till {DEVICES_FILE}")

def load_device_context():
    with open(DEVICES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def set_device_state(entity_id, state, brightness=None, color_temp=None, rgb_color=None):
    domain = entity_id.split(".")[0]
    service = "turn_on" if state == "on" else "turn_off"
    payload = {"entity_id": entity_id}
    if brightness is not None:
        payload["brightness"] = brightness
    if color_temp is not None:
        payload["color_temp_kelvin"] = color_temp
    if rgb_color is not None:
        payload["rgb_color"] = rgb_color
    r = requests.post(
        f"{HA_URL}/api/services/{domain}/{service}",
        headers=HA_HEADERS,
        json=payload
    )
    return "ok" if r.status_code == 200 else "fel"

# ─────────────────────────────────────────
# Minnesfunktioner
# ─────────────────────────────────────────
def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {}
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_memory(key, value):
    memory = load_memory()
    memory[key] = value
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2, ensure_ascii=False)
    return "ok"

def get_memory(key):
    memory = load_memory()
    return memory.get(key, "ingen information hittades")

def search_events(query):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=query
    )
    vector = response.data[0].embedding

    resultat = qdrant.query_points(
        collection_name="home_events",
        query=vector,
        limit=25
    )

    if not resultat.points:
        return "Inga relevanta händelser hittades."

    texter = [p.payload["text"] for p in resultat.points]
    return "\n".join(texter)

# ─────────────────────────────────────────
# Qdrant-funktioner
# ─────────────────────────────────────────
def ensure_collection():
    if not qdrant.collection_exists("home_events"):
        qdrant.create_collection(
            collection_name="home_events",
            vectors_config=VectorParams(size=1536, distance=Distance.COSINE)
        )

def log_event(entity_id, state):
    now = datetime.now()
    text = f"{now.strftime('%Y-%m-%d %A %H:%M')} — {entity_id} ändrades till {state}"

    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    vector = response.data[0].embedding

    qdrant.upsert(
        collection_name="home_events",
        points=[
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "text": text,
                    "entity_id": entity_id,
                    "state": state,
                    "timestamp": now.isoformat()
                }
            )
        ]
    )
    #print(f"Loggad: {text}")

# ─────────────────────────────────────────
# WebSocket-lyssnare
# ─────────────────────────────────────────
async def listen():
    async with websockets.connect(WS_URL) as ws:
        msg = await ws.recv()
        print("HA säger:", json.loads(msg)["type"])

        await ws.send(json.dumps({
            "type": "auth",
            "access_token": HA_TOKEN
        }))

        msg = await ws.recv()
        print("Auth:", json.loads(msg)["type"])

        await ws.send(json.dumps({
            "id": 1,
            "type": "subscribe_events",
            "event_type": "state_changed"
        }))

        msg = await ws.recv()
        print("Prenumeration:", json.loads(msg)["type"])

        print("Lyssnar på state-ändringar...")
        while True:
            msg = await ws.recv()
            data = json.loads(msg)

            if data.get("type") == "event":
                entity_id = data["event"]["data"]["entity_id"]
                new_state_obj = data["event"]["data"]["new_state"]
                if new_state_obj is None:
                    continue
                new_state = new_state_obj["state"]
                domain = entity_id.split(".")[0]

                if domain == "sensor" and (
                    "_power" in entity_id or
                    "_total_energy" in entity_id
                ):
                    continue

                if domain in ["light", "switch"]:
                    if previous_states.get(entity_id) == new_state:
                        continue
                    previous_states[entity_id] = new_state

                if domain in ["light", "switch", "sensor", "person", "device_tracker"]:
                    log_event(entity_id, new_state)

# ─────────────────────────────────────────
# AI-funktioner
# ─────────────────────────────────────────
def ask_ai(user_message, user_history=[], session_id="okänd"):
    devices = load_device_context()
    device_info = json.dumps(devices, ensure_ascii=False, indent=2)
    memory_keys = list(load_memory().keys())

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Du är en hemassistent som känner till följande enheter:\n\n"
                    f"{device_info}\n\n"
                    f"Tillgängliga nycklar i minnet: {memory_keys}\n\n"
                    "Du kan hämta status och styra enheter i hemmet. "
                    "Du kan tända, släcka, dimma, ändra färgtemperatur och RGB-färg på lampor. "
                    "Använd verktygen för att utföra det användaren ber om. "
                    "Använd verktygen direkt utan att be om bekräftelse. "
                    "Använd save_memory när användaren explicit ber dig komma ihåg något. "
                    "Använd snake_case på engelska för minnesnycklar, t.ex. 'dog_name'. "
                    "Om användaren frågar om något du ska eller kan känna till, använd get_memory med relevant nyckel från listan ovan."
                )
            },
            *user_history,
            {"role": "user", "content": user_message}
        ],
        tools=TOOLS,
        temperature=0.5
    )

    message = response.choices[0].message

    if message.tool_calls:
        tool_results = []
        for tool_call in message.tool_calls:
            arguments = json.loads(tool_call.function.arguments)

            if tool_call.function.name == "get_device_state":
                result = get_device_state(arguments["entity_id"])
            elif tool_call.function.name == "set_device_state":
                brightness = arguments.get("brightness", None)
                color_temp = arguments.get("color_temp", None)
                rgb_color = arguments.get("rgb_color", None)
                result = set_device_state(arguments["entity_id"], arguments["state"], brightness, color_temp, rgb_color)
            elif tool_call.function.name == "save_memory":
                result = save_memory(arguments["key"], arguments["value"])
            elif tool_call.function.name == "get_memory":
                result = get_memory(arguments["key"])
            elif tool_call.function.name == "search_events":
                result = search_events(arguments["query"])
            else:
                result = "okänt verktyg"

            tool_results.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(result)
            })

        second_response = client.chat.completions.create(
            model=MODEL,
            messages=[
                *user_history,
                {"role": "user", "content": user_message},
                message,
                *tool_results
            ]
        )
        return second_response.choices[0].message.content.strip()

    return message.content.strip()

# ─────────────────────────────────────────
# Flask-routes
# ─────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    token = request.headers.get("X-Webhook-Token")
    if token != SECRET:
        return "Unauthorized", 401
    data = request.get_json()
    user_message = data.get("message", "")
    answer = ask_ai(user_message)
    return answer, 200

@app.route("/")
def index():
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
    <title>Hemassistent</title>
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta name="apple-mobile-web-app-title" content="Hemassistent">
    <link rel="manifest" href="/manifest.json">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #f0f0f5;
            display: flex;
            flex-direction: column;
            height: 100vh;
            max-width: 480px;
            margin: 0 auto;
        }

        .header {
            background: #fff;
            border-bottom: 0.5px solid rgba(0,0,0,0.12);
            padding: 14px 16px;
            display: flex;
            align-items: center;
            gap: 10px;
            flex-shrink: 0;
        }

        .header-avatar {
            width: 38px;
            height: 38px;
            border-radius: 50%;
            background: #185FA5;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #E6F1FB;
            font-size: 13px;
            font-weight: 500;
            flex-shrink: 0;
        }

        .header-title {
            font-size: 15px;
            font-weight: 600;
            color: #000;
        }

        .header-subtitle {
            font-size: 12px;
            color: #888;
        }

        .chat-area {
            flex: 1;
            overflow-y: auto;
            padding: 16px 12px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            background: #f0f0f5;
        }

        .bubble-row {
            display: flex;
            flex-direction: column;
        }

        .bubble-row.user { align-items: flex-end; }
        .bubble-row.ai { align-items: flex-start; }

        .bubble {
            max-width: 78%;
            padding: 9px 13px;
            font-size: 15px;
            line-height: 1.5;
        }

        .bubble.user {
            background: #185FA5;
            color: #fff;
            border-radius: 18px 18px 4px 18px;
        }

        .bubble.ai {
            background: #fff;
            color: #000;
            border-radius: 18px 18px 18px 4px;
            border: 0.5px solid rgba(0,0,0,0.1);
        }

        .timestamp {
            font-size: 11px;
            color: #aaa;
            margin-top: 3px;
            padding: 0 4px;
        }

        .typing {
            display: flex;
            gap: 4px;
            padding: 10px 14px;
            background: #fff;
            border: 0.5px solid rgba(0,0,0,0.1);
            border-radius: 18px 18px 18px 4px;
            width: fit-content;
        }

        .dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #aaa;
            animation: bounce 1.2s infinite;
        }

        .dot:nth-child(2) { animation-delay: 0.2s; }
        .dot:nth-child(3) { animation-delay: 0.4s; }

        @keyframes bounce {
            0%, 60%, 100% { transform: translateY(0); }
            30% { transform: translateY(-5px); }
        }

        .input-area {
            background: #fff;
            border-top: 0.5px solid rgba(0,0,0,0.12);
            padding: 10px 12px;
            display: flex;
            gap: 8px;
            align-items: center;
            flex-shrink: 0;
        }

        .msg-input {
            flex: 1;
            border: 0.5px solid rgba(0,0,0,0.2);
            border-radius: 20px;
            padding: 9px 14px;
            font-size: 15px;
            background: #f0f0f5;
            color: #000;
            outline: none;
            font-family: inherit;
        }

        .msg-input:focus {
            border-color: #185FA5;
        }

        .send-btn {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            background: #185FA5;
            border: none;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }

        .send-btn:active { transform: scale(0.93); }

        @media (prefers-color-scheme: dark) {
            body { background: #1c1c1e; }
            .header { background: #2c2c2e; border-color: rgba(255,255,255,0.1); }
            .header-title { color: #fff; }
            .header-subtitle { color: #888; }
            .chat-area { background: #1c1c1e; }
            .bubble.ai { background: #2c2c2e; color: #fff; border-color: rgba(255,255,255,0.08); }
            .input-area { background: #2c2c2e; border-color: rgba(255,255,255,0.1); }
            .msg-input { background: #1c1c1e; color: #fff; border-color: rgba(255,255,255,0.2); }
            .timestamp { color: #666; }
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-avatar">AI</div>
        <div>
            <div class="header-title">Hemassistent</div>
            <div class="header-subtitle">Online</div>
        </div>
    </div>

    <div class="chat-area" id="chat"></div>

    <div class="input-area">
        <input class="msg-input" id="msg" placeholder="Skriv något..." autocomplete="off" />
        <button class="send-btn" onclick="send()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
            </svg>
        </button>
    </div>

    <script>
        const sessionId = Math.random().toString(36).substring(2);

        function now() {
            return new Date().toLocaleTimeString('sv-SE', {hour: '2-digit', minute: '2-digit'});
        }

        function addBubble(text, role) {
            const chat = document.getElementById('chat');
            const row = document.createElement('div');
            row.className = 'bubble-row ' + role;
            row.innerHTML = '<div class="bubble ' + role + '">' + text + '</div><div class="timestamp">' + now() + '</div>';
            chat.appendChild(row);
            chat.scrollTop = chat.scrollHeight;
        }

        function addTyping() {
            const chat = document.getElementById('chat');
            const row = document.createElement('div');
            row.className = 'bubble-row ai';
            row.id = 'typing';
            row.innerHTML = '<div class="typing"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>';
            chat.appendChild(row);
            chat.scrollTop = chat.scrollHeight;
        }

        function removeTyping() {
            const t = document.getElementById('typing');
            if (t) t.remove();
        }

        async function send() {
            const input = document.getElementById('msg');
            const msg = input.value.trim();
            if (!msg) return;
            input.value = '';
            addBubble(msg, 'user');
            addTyping();
            const base = window.location.pathname.replace(/\\/$/, '');
            try {
                const res = await fetch(base + '/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: msg, session_id: sessionId})
                });
                const data = await res.json();
                removeTyping();
                addBubble(data.reply, 'ai');
            } catch (e) {
                removeTyping();
                addBubble('Något gick fel. Försök igen.', 'ai');
            }
        }

        document.getElementById('msg').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') send();
        });
    </script>
</body>
</html>
"""


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
    session_id = data.get("session_id", "default")
    try:
        if session_id not in sessions:
            sessions[session_id] = []
        session_history = sessions[session_id]
        answer = ask_ai(user_message, session_history, session_id)
        session_history.append({"role": "user", "content": user_message})
        session_history.append({"role": "assistant", "content": answer})
        return {"reply": answer}
    except Exception as e:
        logging.error(f"Fel i chat: {e}", exc_info=True)
        return {"reply": "Ett fel uppstod"}, 500

@app.route("/manifest.json")
def manifest():
    return {
        "name": "Hemassistent",
        "short_name": "Hemassistent",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#f0f0f5",
        "theme_color": "#185FA5",
        "icons": [
            {
                "src": "/icon.png",
                "sizes": "192x192",
                "type": "image/png"
            }
        ]
    }
# ─────────────────────────────────────────
# Start
# ─────────────────────────────────────────
if __name__ == "__main__":
    try:
        save_device_context()
    except Exception as e:
        print(f"kunde inte spara enheter:{e}", flush=True    
        ensure_collection()
        conversation_history = []
        sessions = {}

    # Starta WebSocket-lyssnaren i egen tråd
    ws_thread = threading.Thread(target=lambda: asyncio.run(listen()))
    ws_thread.daemon = True
    ws_thread.start()

    in_container = os.path.exists("/data/options.json")

    if in_container:
        app.run(host="0.0.0.0", port=5001, debug=False)
    else:
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        flask_thread = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5001, use_reloader=False, use_debugger=False))
        flask_thread.daemon = True
        flask_thread.start()

        while True:
            user_input = input("Du: ")
            if user_input.lower() in ["exit", "quit"]:
                break
            conversation_history.append({"role": "user", "content": user_input})
            answer = ask_ai(user_input, conversation_history)
            conversation_history.append({"role": "assistant", "content": answer})
            print("AI:", answer, "\n")
