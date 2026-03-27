from flask import Flask, request
import requests
import os
from openai import OpenAI

app = Flask(__name__)

SECRET = "min_hemliga_token"

HA_URL = "http://homeassistant.local:8123"
HA_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIzMmUzZmFmYTRmMDc0MTI1OTllMjBkYmFjNTI1NWEyMCIsImlhdCI6MTc3NDYxNzg5MCwiZXhwIjoyMDg5OTc3ODkwfQ.EHXmh_V7-qSyvHtvS8oERQDghkeANSC4NYZgxItW5QA"

headers = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json",
}

client = OpenAI()

def ai_should_toggle():
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Svara endast med JA eller NEJ."},
            {"role": "user", "content": "Ska lampan togglas?"}
        ],
        temperature=0
    )

    answer = response.choices[0].message.content.strip().upper()
    print("AI svar:", answer)
    return answer == "JA"


def toggle_lamp():
    entity_id = "light.golvlampa_i_kontoret"
    data = {"entity_id": entity_id}

    r = requests.post(
        f"{HA_URL}/api/services/light/toggle",
        headers=headers,
        json=data
    )

    print("Toggle status:", r.status_code)


@app.route("/webhook", methods=["POST"])
def webhook():
    token = request.headers.get("X-Webhook-Token")

    if token != SECRET:
        return "Unauthorized", 401

    print("Webhook mottagen!")

    if ai_should_toggle():
        toggle_lamp()
    else:
        print("AI valde att inte toggla.")

    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

