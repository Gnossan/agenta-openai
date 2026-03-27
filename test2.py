import requests

HA_URL = "http://homeassistant.local:8123"
HA_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIzMmUzZmFmYTRmMDc0MTI1OTllMjBkYmFjNTI1NWEyMCIsImlhdCI6MTc3NDYxNzg5MCwiZXhwIjoyMDg5OTc3ODkwfQ.EHXmh_V7-qSyvHtvS8oERQDghkeANSC4NYZgxItW5QA"

headers = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json",
}

entity_id = "light.golvlampa_i_kontoret"

data = {
    "entity_id": entity_id
}

r = requests.post(
    f"{HA_URL}/api/services/light/toggle",
    headers=headers,
    json=data
)

print("Statuskod:", r.status_code)
print("Svar:", r.text)
