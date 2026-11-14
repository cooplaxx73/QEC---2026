import { createHash, randomBytes } from 'node:crypto';
import { readFile, writeFile, rename } from 'node:fs/promises';
import path from 'node:path';
import { validateTelemetry, summarizeTelemetry } from './telemetry.mjs';

export async function createCareApi({ accounts, saveAccounts, dataDir, body, reply, error, canManagePatient }) {
  const file = path.join(dataDir, 'care.json');
  let records;
  try { records = JSON.parse(await readFile(file, 'utf8')); }
  catch (e) { if (e.code !== 'ENOENT') throw e; records = {}; }
  let queue = Promise.resolve();
  function persist() { const snapshot = JSON.stringify(records, null, 2); queue = queue.catch(() => {}).then(async () => { await writeFile(file + '.tmp', snapshot); await rename(file + '.tmp', file); }); return queue; }
  const online = new Map();
  const defaults = { cursor_sensitivity: 1, cursor_smoothing: .5, blink_threshold: .5, click_hold_seconds: .6, blink_action: 'left_click', zoom_enabled: true, zoom_lean_ratio: 1.18, zoom_factor: 2.5, low_light_enabled: true, low_light_threshold: 70, speech_rate: 160 };
  const bounds = { cursor_sensitivity: [.25, 3], cursor_smoothing: [0, .95], blink_threshold: [.1, .95], click_hold_seconds: [.3, 2], zoom_lean_ratio: [1.05, 2], zoom_factor: [1.5, 4], low_light_threshold: [0, 255], speech_rate: [80, 260] };
  const digest = value => createHash('sha256').update(value).digest('hex');
  function record(patient) {
    const r = records[patient.patientId] ||= { settings: { ...defaults }, revision: 0, events: [], logs: [], audit: [], nextId: 1 };
    if (!r.nextLogId) { r.logs.forEach((e, i) => e.id = i + 1); r.nextLogId = r.logs.length + 1; }
    return r;
  }
  function event(r, side, type, details = {}) { r.events.push({ id: r.nextId++, side, type, time: Date.now() / 1000, ...details }); r.events = r.events.slice(-1000); }
  function audit(r, actor, action, details = {}) { r.audit.push({ time: Date.now() / 1000, action, actorId: actor.id, by: actor.name, ...details }); r.audit = r.audit.slice(-2000); }
  function device(req) {
    const token = /^Bearer ([a-f0-9]{64})$/.exec(req.headers.authorization || '')?.[1];
    const patient = token && accounts.find(a => a.role === 'patient' && a.deviceHash === digest(token));
    if (!patient) throw error(401, 'Desktop not paired. Run python connect.py.');
    online.set(patient.patientId, Date.now()); return patient;
  }
  return async function care(req, res, url, actor) {
    if (url.pathname === '/api/device-pair' && req.method === 'POST') {
      if (actor.role !== 'patient') throw error(403, 'Pair the desktop using the patient account.');
      const token = randomBytes(32).toString('hex'); actor.deviceHash = digest(token); await saveAccounts();
      return reply(res, 200, { deviceToken: token, patientId: actor.patientId, name: actor.name });
    }
    const isDevice = url.pathname.startsWith('/api/device/');
    if (!isDevice && !url.pathname.startsWith('/api/care/')) return false;
    const b = req.method === 'POST' ? await body(req) : null;
    const patient = isDevice ? device(req) : accounts.find(a => a.role === 'patient' && a.patientId === (b?.patientId || url.searchParams.get('patientId')));
    if (!patient || (!isDevice && !canManagePatient(actor, patient))) throw error(403, 'Patient access is not approved.');
    const r = record(patient);
    const endpoint = url.pathname.replace(isDevice ? '/api/device/' : '/api/care/', '');
    if (req.method === 'GET' && endpoint === 'state') return reply(res, 200, { patientId: patient.patientId, name: patient.name, settings: r.settings, revision: r.revision, logging: patient.logging, connected: Date.now() - (online.get(patient.patientId) || 0) < 5000, logs: r.logs.slice(-200).reverse(), audit: r.audit.slice(-200).reverse(), telemetry: summarizeTelemetry(r.logs) });
    if (req.method === 'GET' && endpoint === 'logs' && !isDevice) {
      const before = Number(url.searchParams.get('before') || Number.MAX_SAFE_INTEGER);
      const limit = Number(url.searchParams.get('limit') || 200);
      if (!Number.isSafeInteger(before) || !Number.isInteger(limit) || limit < 1 || limit > 500) throw error(400, 'Invalid log page.');
      const all = r.logs.filter(e => e.id < before).reverse();
      const entries = all.slice(0, limit);
      return reply(res, 200, { entries, nextBefore: all.length > limit ? entries.at(-1).id : null, total: r.logs.length, retainedLimit: 20000 });
    }
    if (req.method === 'GET' && endpoint === 'export' && !isDevice) return reply(res, 200, { patientId: patient.patientId, patient: patient.name, patientActivity: r.logs, caregiverAudit: r.audit, retainedLimit: 20000 });
    if (req.method === 'POST' && endpoint === 'logging' && !isDevice) {
      if (patient.id !== actor.id) throw error(403, 'Only the patient can change logging consent.');
      if (typeof b.logging !== 'boolean') throw error(400, 'Choose whether to enable logging.');
      patient.logging = b.logging; patient.loggingConsentAt = new Date().toISOString(); patient.loggingConsentVersion = 'spatial-activity-1';
      event(r, 'patient', 'logging_changed', { logging: patient.logging });
      await saveAccounts(); await persist(); return reply(res, 200, { logging: patient.logging });
    }
    if (req.method === 'GET' && endpoint === 'bootstrap' && isDevice) return reply(res, 200, { settings: r.settings, logging: patient.logging, eventCursor: r.nextId - 1 });
    if (req.method === 'GET' && (endpoint === 'patient/events' || endpoint === 'events')) {
      const side = isDevice ? 'patient' : 'caregiver'; const after = Number(url.searchParams.get('after') || 0);
      if (!Number.isFinite(after)) throw error(400, 'Invalid event cursor.');
      return reply(res, 200, r.events.filter(e => e.side === side && e.id > after));
    }
    if (req.method === 'POST' && endpoint === 'settings' && !isDevice) {
      if (b.revision !== r.revision) throw error(409, 'Settings changed. Reload the current patient and try again.');
      const changes = b.changes;
      if (!changes || !Object.keys(changes).length) throw error(400, 'Choose a setting to update.');
      for (const [key, value] of Object.entries(changes)) {
        if (!Object.hasOwn(defaults, key)) throw error(400, 'Unsupported setting: ' + key);
        if (bounds[key] && (typeof value !== 'number' || !Number.isFinite(value) || value < bounds[key][0] || value > bounds[key][1])) throw error(400, 'Value out of range: ' + key);
        if (typeof defaults[key] === 'boolean' && typeof value !== 'boolean') throw error(400, 'Expected on/off: ' + key);
        if (key === 'blink_action' && !['left_click', 'right_click', 'double_click'].includes(value)) throw error(400, 'Unsupported blink action.');
      }
      Object.assign(r.settings, changes); r.revision++;
      audit(r, actor, 'settings changed', { changes }); event(r, 'patient', 'settings_changed', { changes, by: actor.name }); await persist();
      return reply(res, 200, { revision: r.revision, settings: r.settings, connected: Date.now() - (online.get(patient.patientId) || 0) < 5000 });
    }
    if (req.method === 'POST' && endpoint === 'patient/logs' && isDevice) {
      if (patient.logging) {
        if (typeof b.kind !== 'string' || b.kind.length > 80) throw error(400, 'Invalid activity entry.');
        let details;
        try { details = validateTelemetry(b.details); } catch (e) { throw error(400, e.message); }
        if (b.time !== undefined && (typeof b.time !== 'number' || !Number.isFinite(b.time) || b.time <= 0 || b.time > Date.now() / 1000 + 300)) throw error(400, 'Invalid activity timestamp.');
        r.logs.push({ id: r.nextLogId++, time: b.time || Date.now() / 1000, receivedAt: Date.now() / 1000, kind: b.kind, value: typeof b.value === 'number' && Number.isFinite(b.value) ? b.value : 0, note: String(b.note || '').slice(0, 500), details }); r.logs = r.logs.slice(-20000); await persist();
      }
      return reply(res, 200, { ok: true, logging: patient.logging });
    }
    if (req.method === 'POST' && endpoint === 'patient/call' && isDevice) {
      event(r, 'caregiver', 'call', { video: false }); await persist(); return reply(res, 200, { ok: true });
    }
    if (req.method === 'POST' && endpoint === 'call' && !isDevice) {
      audit(r, actor, 'call requested'); event(r, 'patient', 'caregiver_message', { message: `${actor.name} is asking to connect.`, by: actor.name }); await persist(); return reply(res, 200, { ok: true });
    }
    // Video transport is intentionally not exposed until it can enforce per-call consent.
    throw error(404, 'This integration endpoint is not available.');
  };
}
