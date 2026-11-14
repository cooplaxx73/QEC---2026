# SignalSpeak — integrated local demo

Combines website `web` (52f549c), phone UI `app` (612755c), and desktop `action-implementation` (7d01be3) on `codex/integrated-demo`. Teammates' branches remain unchanged.

## Start the account server and browser phone dashboard

Requires Node.js 22+. No Node packages to install.

```sh
node scripts/package-desktop.mjs
node server.mjs
```

- Website: http://localhost:3000
- Phone dashboard (browser demo): http://localhost:3000/app/

The server binds to this computer only. This is the laptop-browser phone demo; a physical phone cannot reach the laptop through localhost. Do not expose this local HTTP prototype as a public account service.

## End-to-end demo

1. On the website, create a patient account using fictional information. Accept privacy. Choose whether to enable optional patient activity logging.
2. Copy the patient ID. Sign out, create a separate caregiver account, and request a connection using the patient ID.
3. Sign back in as the patient and accept the connection in My account.
4. For simultaneous patient and caregiver sessions, use separate browser profiles or an incognito window. Tabs in one browser profile share the same login cookie.
5. Open `/app/` as the caregiver. Select an approved patient. Change a supported setting and inspect its real audit entry. All control customization is in this phone dashboard, not the onboarding website.
6. Prepare and pair the desktop below. It appears connected in the phone dashboard while polling the server. Offline settings are loaded at the next connection.
7. Change blink hold time in the dashboard. The paired desktop receives the update and notifies the patient. Call Caregiver on the desktop sends a notification to the phone dashboard. Request a connection from the phone to send a desktop notification.
8. Patient action logs appear only if the patient enabled logging at signup. Audit logs record settings changes and connection requests under the authenticated actor's identity.
9. Revoke a caregiver connection on the website to block further access to that patient's settings, logs and events.

## Desktop setup

Python 3.11 is recommended. See `desktop/README.md`. From the desktop folder:

```sh
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python connect.py
python main.py
```

`connect.py` asks for the server address (default http://127.0.0.1:3000), patient email and password before the hands-free demo. It saves a device token in ignored `desktop/device.json`, not the password. Pairing again replaces the previous device token. Website sign-out does not stop the paired desktop. The face model is downloaded on first launch.

The Download page provides a source ZIP after running the packaging command. It is **not a standalone installer** and still requires Python/dependencies. Packaging includes source only, excluding device credentials, settings, patient logs and the face model. The legacy unauthenticated stub server is not used or included in that ZIP.

## Data and permissions

One account store: ignored `data/accounts.json`. Website and phone use the same login API. Desktop requests authenticate with a separate paired token whose hash is stored on the patient account. Patient IDs identify profiles; they never act as credentials.

Ignored `data/care.json` stores per-patient settings, event queues, patient logs and caregiver audit entries separately from account credentials. The backend derives actor identity from the session and checks the approved relationship on every phone request. Settings writes use revision checks to prevent silent concurrent overwrites. Phone polling does not extend an idle browser session.

Passwords use salted scrypt. Browser sessions are HTTP-only SameSite cookies with a 15-minute inactivity expiry. Restarting the server ends browser sessions; accounts, care data and paired device identity persist. JSON storage assumes one server process. Use fictional data only.

## Implemented and remaining

Implemented: account creation/sign-in, consent, linking and revocation, patient switching, desktop pairing, supported remote settings, offline settings persistence, patient logging consent, actual charts/log export, support notifications, source download.

Remaining: video/audio transport (explicitly disabled), instruction video, packaged executable, real-phone networking/HTTPS, production identity, self-service deletion and preference editing. Camera accuracy, OS permissions and eye-only use must be tested on the actual demo laptop. No hardware behavior is implied by API tests.

## Checks

```sh
node --test
python -m unittest discover -s desktop/tests -p test_adapter.py -v
```

The adapter tests need only Python's standard library and don't access the camera or mouse. With all desktop dependencies installed, run `python -m unittest discover -s tests -v` from `desktop` for the original tracking tests too.

## Attribution

Original phone interface: teammate's `app` branch. Original eye tracking/desktop: teammate's `action-implementation` branch. Website and integration use OpenAI Codex assistance. Preserve the desktop's dependency and Claude Code attribution in its source/README. No presentation content is generated here.
