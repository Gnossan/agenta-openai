# ─────────────────────────────────────────
# Imports
# ─────────────────────────────────────────
from flask import Flask, request
from dotenv import load_dotenv
import requests
import json
import os
import threading
import logging
import sys
from openai import OpenAI

load_dotenv()

app = Flask(__name__)

# ─────────────────────────────────────────
# Konfiguration
# ─────────────────────────────────────────
MODEL = os.getenv("MODEL", "gpt-4o-mini")
OPTIONS_FILE = "/data/options.json"
if os.path.exists(OPTIONS_FILE):
    with open(OPTIONS_FILE) as f:
        options = json.load(f)
    SECRET = options.get("secret")
    HA_URL = options.get("ha_url")
    HA_TOKEN = options.get("ha_token")
    os.environ["OPENAI_API_KEY"] = options.get("openai_api_key", "")
    MODEL = options.get("model", "gpt-4o-mini")
else:
    load_dotenv()
    SECRET = os.getenv("SECRET")
    HA_URL = os.getenv("HA_URL")
    HA_TOKEN = os.getenv("HA_TOKEN")

HA_HEADERS = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json",
}

DEVICES_FILE = "devices.json"
MEMORY_FILE = "/share/memory.json"
conversation_history = []
sessions = {}

client = OpenAI()

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
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Hemassistent</title>
    <style>
        body { font-family: sans-serif; max-width: 600px; margin: 20px auto; padding: 0 20px; }
        #chat { border: 1px solid #ccc; height: 400px; overflow-y: auto; padding: 10px; margin-bottom: 10px; }
        .user { text-align: right; color: #0066cc; margin: 5px 0; }
        .ai { text-align: left; color: #333; margin: 5px 0; }
        input { width: 80%; padding: 8px; font-size: 16px; }
        button { width: 18%; padding: 8px; }
    </style>
</head>
<body>
    <h2>Hemassistent - OpenAI</h2>
    <div id="chat"></div>
    <input type="text" id="msg" placeholder="Skriv något..." />
    <button onclick="send()">Skicka</button>
    <script>
        const sessionId = Math.random().toString(36).substring(2);
        async function send() {
            const msg = document.getElementById("msg").value;
            if (!msg) return;
            document.getElementById("chat").innerHTML += '<p class="user">' + msg + '</p>';
            document.getElementById("msg").value = "";
            const base = window.location.pathname.replace(/\/$/, '');
            const res = await fetch(base + "/chat", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({message: msg, session_id: sessionId})
            });
            const data = await res.json();
            document.getElementById("chat").innerHTML += '<p class="ai">' + data.reply + '</p>';
            document.getElementById("chat").scrollTop = document.getElementById("chat").scrollHeight;
        }
        document.getElementById("msg").addEventListener("keypress", function(e) {
            if (e.key === "Enter") send();
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

# ─────────────────────────────────────────
# Start
# ─────────────────────────────────────────
if __name__ == "__main__":
    save_device_context()
    conversation_history = []
    sessions = {}

    in_container = os.path.exists("/data/options.json")

    if in_container:
        app.run(host="0.0.0.0", port=5003, debug=False)
    else:
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        flask_thread = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5003, use_reloader=False, use_debugger=False))
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
