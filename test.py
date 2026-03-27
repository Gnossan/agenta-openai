import requests

HA_URL = "http://192.168.86.92:8123"
HA_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI3ZTJlNzg4ODNhMDI0NDViYWJiOTQ5OTdiMGUzNjgzOSIsImlhdCI6MTc3MDk3Mzk0OCwiZXhwIjoyMDg2MzMzOTQ4fQ.JyIQ8w6j1ot4dW2AADMgldsBUF2J3RdEyR06sP7F7L0"

headers = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json",
}

r = requests.get(f"{HA_URL}/api/", headers=headers)

print("Statuskod:", r.status_code)
print("Svar:", r.text)
