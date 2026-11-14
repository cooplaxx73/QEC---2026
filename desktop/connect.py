"""Pair the desktop with a website account. Integration assistance: OpenAI Codex."""
import getpass
import json
from pathlib import Path
import requests

DEVICE_FILE = Path(__file__).parent / "device.json"


def main():
    url = input("Account server [http://127.0.0.1:3000]: ").strip() or "http://127.0.0.1:3000"
    email = input("Patient email: ").strip()
    password = getpass.getpass("Patient password: ")
    with requests.Session() as session:
        response = session.post(url.rstrip("/") + "/api/login", json={"email": email, "password": password}, timeout=10)
        response.raise_for_status()
        if response.json()["role"] != "patient":
            raise ValueError("Use the patient account to pair this computer.")
        paired = session.post(url.rstrip("/") + "/api/device-pair", json={}, timeout=10)
        paired.raise_for_status()
        data = paired.json()
        data["backend_url"] = url.rstrip("/")
        DEVICE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        session.post(url.rstrip("/") + "/api/logout", json={}, timeout=10)
    print(f"Paired with {data['name']} ({data['patientId']}). Run python main.py next.")


if __name__ == "__main__":
    try:
        main()
    except (requests.RequestException, ValueError) as error:
        print(f"Pairing failed: {error}")
        raise SystemExit(1)
