# SignalSpeak · local website demo

Onboarding interface on the `web` branch. Requires Node.js 22+. No dependencies to install.

## Run

```sh
node server.mjs
```

Open http://localhost:3000. The server binds only to this computer. Stop with Ctrl+C.

## Try it

1. Get started → Patient. Create an account with fictional details and accept privacy.
2. Copy your patient ID from My account. Continue to the instructions for text and read-aloud.
3. Sign out, create a caregiver account, and enter the patient ID to request a connection.
4. Sign in as the patient and accept or decline the request. Accepted connections can be revoked.
5. Sign in as the caregiver to see the status. Refresh the care circle to retrieve changes.

General email/password login is separate from patient IDs. Caregivers can view approved connections using **View connected patients**. One caregiver can support multiple patients and multiple caregivers can support one patient. Selecting a patient never changes the logged-in identity.

**All control settings are managed in the phone app.** This website provides account setup, patient IDs, care connections, privacy acceptance, instructions with browser read-aloud, and download information. It has no editable cursor, eye-closure, binding, or desktop read-aloud controls and no control-settings API. Approving a connection grants no remote control, camera, microphone, or OS access. Patients can revoke connections. Previously saved demo settings, if any, are left in the ignored local data file but are no longer exposed or editable by this website.

## Storage

Accounts are saved in ignored `data/accounts.json`. Never commit this file. Use fictional demo identities only. Passwords are salted scrypt hashes, sessions use HTTP-only SameSite cookies, and login attempts are rate limited. Sessions expire after 15 minutes without interaction, with a warning at 14 minutes. Restarting the server ends sessions but preserves accounts.

`PORT` changes the port; `SIGNALSPEAK_DATA_DIR` changes the data directory. Keep alternate data directories outside Git. The JSON store assumes one server process. Production hosting, email verification, password recovery, account deletion UI, and a production identity system are outside this local prototype.

## Backend handoff

The UI calls same-origin JSON endpoints through `api()` in `public/app.js`. Replace the local adapter in `server.mjs` when the team's backend is ready.

| Endpoint | Request / behavior |
| --- | --- |
| POST /api/register | name, email, password, role, optional phone, consent boolean, optional logging boolean; creates and signs in |
| POST /api/login | email, password |
| GET /api/me | own public profile only |
| POST /api/logout | ends session |
| POST /api/activity | refreshes inactivity timer |
| GET /api/connections | own care circle, display names and statuses |
| POST /api/connections | caregiver submits patientId; creates pending request |
| POST /api/permission | patient submits request id and approved, declined, or revoked status |
| GET /api/patients | own profile or approved patients, with display names and patient IDs |

API errors return `{ "error": "message" }` and a non-2xx status. Sessions use cookies. The desktop backend must separately authenticate the device owner and enforce granular permissions. Website sign-out must not stop essential desktop communication.

## Pending team assets

- Installer and platform requirements: Download currently clearly shows unavailable status.
- Instruction video and captions: instructions currently show a placeholder plus working text and browser read-aloud.
- Movement detection, calibration, notifications, video calls, device control, and complete dual activity logs: separate team integrations. Optional logging saves a preference only.
- Control customization and its history: phone app responsibility. The website's instruction read-aloud buttons read this page only and do not change device preferences.

## Verification and attribution

Run `node --test`. No third-party libraries, fonts, or external assets are used. Initial website implementation used OpenAI Codex; cite AI assistance according to competition requirements. The desktop graphic is an illustrative concept.
