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
SECRET   = os.getenv("SECRET")
HA_URL   = os.getenv("HA_URL")
HA_TOKEN = os.getenv("HA_TOKEN")

HA_HEADERS = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json",
}

DEVICES_FILE = "devices.json"

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
                    }
                },
                "required": ["entity_id", "state"]
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

        # Bara lampor och brytare till en början
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
    
def set_device_state(entity_id, state):
    domain = entity_id.split(".")[0]
    service = "turn_on" if state == "on" else "turn_off"
    r = requests.post(
        f"{HA_URL}/api/services/{domain}/{service}",
        headers=HA_HEADERS,
        json={"entity_id": entity_id}
    )
    return "ok" if r.status_code == 200 else "fel"

# ─────────────────────────────────────────
# AI-funktioner
# ─────────────────────────────────────────
def ask_ai(user_message, user_history=[]):
    devices = load_device_context()
    device_info = json.dumps(devices, ensure_ascii=False, indent=2)

    response = client.chat.completions.create(
        model="gpt-5.4-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Du är en hemassistent som känner till följande enheter:\n\n"
                    f"{device_info}\n\n"
                    "Du är en hemassistent som kan hämta status och styra enheter i hemmet. "
                    "När användaren ber dig tända eller släcka en enhet, använd set_device_state direkt utan att fråga om bekräftelse."
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
            #print(f"Verktyg: {tool_call.function.name}, args: {tool_call.function.arguments}")
            arguments = json.loads(tool_call.function.arguments)
        
            if tool_call.function.name == "get_device_state":
                result = get_device_state(arguments["entity_id"])
            elif tool_call.function.name == "set_device_state":
                result = set_device_state(arguments["entity_id"], arguments["state"])
            else:
                result = "okänt verktyg"
        
            tool_results.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(result)
            #print(f"tool_results längd: {len(tool_results)}")
        })

        second_response = client.chat.completions.create(
            model="gpt-4o-mini",
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
    print(f"Fråga: {user_message}")

    answer = ask_ai(user_message)
    print(f"Svar: {answer}")

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
        input { width: 80%; padding: 8px; }
        button { width: 18%; padding: 8px; }
    </style>
</head>
<body>
    <h2>Hemassistent</h2>
    <div id="chat"></div>
    <input type="text" id="msg" placeholder="Skriv något..." />
    <button onclick="send()">Skicka</button>
    <script>
        async function send() {
            const msg = document.getElementById("msg").value;
            if (!msg) return;
            document.getElementById("chat").innerHTML += '<p class="user">' + msg + '</p>';
            document.getElementById("msg").value = "";
            const res = await fetch("/chat", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({message: msg})
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
    answer = ask_ai(user_message, conversation_history)
    conversation_history.append({"role": "user", "content": user_message})
    conversation_history.append({"role": "assistant", "content": answer})
    return {"reply": answer}

# ─────────────────────────────────────────
# Start
# ─────────────────────────────────────────
if __name__ == "__main__":
    save_device_context()
    conversation_history = []

    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    
    flask_thread = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5001, use_reloader=False, use_debugger=False))
    flask_thread.daemon = True
    flask_thread.start()
    
    while True:
        user_input = input("Du: ")
        if user_input.lower() in ["exit", "quit", "arrêt"]:
            break
        conversation_history.append({"role": "user", "content": user_input})
        answer = ask_ai(user_input, conversation_history)
        conversation_history.append({"role": "assistant", "content": answer})
        print("AI:", answer, "\n")

# ─────────────────────────────────────────
# Chat-prompt
# ─────────────────────────────────────────    
if __name__ == "__main__":
    save_device_context()
    conversation_history = []
    while True:
        user_input = input("Du: ")
        if user_input.lower() in ["exit", "quit"]:
            break
        conversation_history.append({"role": "user", "content": user_input})
        answer = ask_ai(user_input, conversation_history)
        conversation_history.append({"role": "assistant", "content": answer})
        print(f"AI: {answer}\n")