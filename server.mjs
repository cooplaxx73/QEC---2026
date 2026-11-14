import http from 'node:http';
import { readFile, writeFile, mkdir, rename, stat } from 'node:fs/promises';
import { randomBytes, scryptSync, timingSafeEqual } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createCareApi } from './care-api.mjs';

const root = path.dirname(fileURLToPath(import.meta.url));
const dataDir = process.env.SIGNALSPEAK_DATA_DIR || path.join(root, 'data');
await mkdir(dataDir, { recursive: true });
const dbFile = path.join(dataDir, 'accounts.json');
let accounts;
try { accounts = JSON.parse(await readFile(dbFile, 'utf8')); }
catch (e) { if (e.code !== 'ENOENT') throw e; accounts = []; }
let queue = Promise.resolve();
function save() {
  const snapshot = JSON.stringify(accounts, null, 2);
  queue = queue.then(async () => { await writeFile(dbFile + '.tmp', snapshot); await rename(dbFile + '.tmp', dbFile); });
  return queue;
}
const sessions = new Map();
const failures = new Map();
const idleMs = 15 * 60 * 1000;
function canManagePatient(actor, patient) {
  return patient.id === actor.id || (actor.role === 'caregiver' && patient.requests.some(r => r.caregiverId === actor.id && r.status === 'approved'));
}
const publicUser = a => ({ id: a.id, name: a.name, email: a.email, role: a.role, phone: a.phone, patientId: a.patientId, logging: a.logging });
const reply = (res, code, value) => { res.writeHead(code, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(value)); };
const error = (status, message) => Object.assign(new Error(message), { status });
async function body(req) {
  let value = '';
  for await (const chunk of req) { value += chunk; if (value.length > 12000) throw error(413, 'Request too large.'); }
  try { return JSON.parse(value); } catch { throw error(400, 'Invalid request.'); }
}
function current(req, touch = true) {
  const token = /(?:^|;\s*)session=([a-f0-9]+)/.exec(req.headers.cookie || '')?.[1];
  const session = sessions.get(token);
  if (!session || Date.now() - session.last > idleMs) { sessions.delete(token); throw error(401, 'Please sign in to continue.'); }
  if (touch) session.last = Date.now();
  return { token, session, user: accounts.find(a => a.id === session.id) };
}
function login(res, user) {
  const token = randomBytes(32).toString('hex');
  sessions.set(token, { id: user.id, last: Date.now() });
  res.setHeader('Set-Cookie', `session=${token}; HttpOnly; SameSite=Strict; Path=/`);
}
const careApi = await createCareApi({ accounts, saveAccounts: save, dataDir, body, reply, error, canManagePatient });
const server = http.createServer(async (req, res) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'no-referrer');
  res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'");
  const url = new URL(req.url, 'http://localhost');
  try {
    if (req.method === 'GET' && url.pathname === '/api/release') {
      let available = false;
      try { available = (await stat(path.join(dataDir, 'releases', 'SignalSpeak-desktop-source.zip'))).isFile(); } catch {}
      return reply(res, 200, { available });
    }
    if (req.method === 'GET' && url.pathname === '/downloads/desktop.zip') {
      let archive;
      try { archive = await readFile(path.join(dataDir, 'releases', 'SignalSpeak-desktop-source.zip')); } catch { throw error(404, 'Desktop source package has not been built yet.'); }
      res.writeHead(200, { 'Content-Type': 'application/zip', 'Content-Disposition': 'attachment; filename="SignalSpeak-desktop-source.zip"' }); return res.end(archive);
    }
    if (url.pathname.startsWith('/api/')) {
      if (req.method === 'POST' && req.headers.origin && req.headers.origin !== `http://${req.headers.host}`) throw error(403, 'Request origin rejected.');
      if (req.method === 'POST' && url.pathname === '/api/register') {
        const b = await body(req);
        const email = String(b.email || '').trim().toLowerCase();
        const name = String(b.name || '').trim();
        if (!name || name.length > 100 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254) throw error(400, 'Enter a name and valid email address.');
        if (typeof b.password !== 'string' || b.password.length < 10 || b.password.length > 128) throw error(400, 'Use a password with 10 to 128 characters.');
        if (!['patient', 'caregiver'].includes(b.role) || b.consent !== true) throw error(400, 'Choose your role and accept the privacy notice.');
        if (accounts.some(a => a.email === email)) throw error(409, 'An account with this email already exists. Please sign in.');
        const salt = randomBytes(16).toString('hex');
        const user = { id: randomBytes(16).toString('hex'), name, email, role: b.role, phone: String(b.phone || '').slice(0, 40), salt, hash: scryptSync(b.password, salt, 64).toString('hex'), patientId: b.role === 'patient' ? 'SS-' + randomBytes(6).toString('hex').toUpperCase() : null, logging: b.logging === true, consentVersion: 'demo-1', consentAt: new Date().toISOString(), requests: [] };
        accounts.push(user); await save(); login(res, user); return reply(res, 201, publicUser(user));
      }
      if (req.method === 'POST' && url.pathname === '/api/login') {
        const key = req.socket.remoteAddress;
        let attempt = failures.get(key);
        if (!attempt || Date.now() - attempt.start > 600000) { attempt = { start: Date.now(), count: 0 }; failures.set(key, attempt); }
        if (attempt.count >= 15) throw error(429, 'Too many attempts. Try again in 10 minutes.');
        const b = await body(req); attempt.count++;
        if (typeof b.password !== 'string' || b.password.length > 128) throw error(401, 'Email or password is incorrect.');
        const user = accounts.find(a => a.email === String(b.email).trim().toLowerCase());
        const hash = scryptSync(b.password, user?.salt || 'invalid-account', 64);
        if (!user || !timingSafeEqual(hash, Buffer.from(user.hash, 'hex'))) throw error(401, 'Email or password is incorrect.');
        failures.delete(key); login(res, user); return reply(res, 200, publicUser(user));
      }
      if (url.pathname.startsWith('/api/device/')) return await careApi(req, res, url);
      const { user, token } = current(req, req.method === 'POST');
      if (url.pathname.startsWith('/api/care/') || url.pathname === '/api/device-pair') return await careApi(req, res, url, user);
      if (req.method === 'GET' && url.pathname === '/api/me') return reply(res, 200, publicUser(user));
      if (req.method === 'POST' && url.pathname === '/api/activity') return reply(res, 200, { ok: true });
      if (req.method === 'POST' && url.pathname === '/api/logout') { sessions.delete(token); res.setHeader('Set-Cookie', 'session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'); return reply(res, 200, { ok: true }); }
      if (req.method === 'GET' && url.pathname === '/api/patients') {
        return reply(res, 200, accounts.filter(a => a.role === 'patient' && canManagePatient(user, a)).map(a => ({ patientId: a.patientId, name: a.name, owner: a.id === user.id })));
      }
      if (req.method === 'GET' && url.pathname === '/api/connections') {
        const items = user.role === 'patient' ? user.requests.map(r => ({ ...r, name: accounts.find(a => a.id === r.caregiverId)?.name || 'Caregiver' })) : accounts.filter(a => a.role === 'patient').flatMap(a => a.requests.filter(r => r.caregiverId === user.id).map(r => ({ ...r, name: a.name, patientId: r.status === 'approved' ? a.patientId : undefined })));
        return reply(res, 200, items);
      }
      if (req.method === 'POST' && url.pathname === '/api/connections') {
        if (user.role !== 'caregiver') throw error(403, 'Only caregivers can request a connection.');
        const b = await body(req); const patient = accounts.find(a => a.role === 'patient' && a.patientId === String(b.patientId).trim().toUpperCase());
        if (!patient) throw error(404, 'Patient ID not found. Check the ID and try again.');
        if (patient.requests.some(r => r.caregiverId === user.id && ['pending', 'approved'].includes(r.status))) throw error(409, 'You already have a connection or pending request.');
        patient.requests = patient.requests.filter(r => r.caregiverId !== user.id);
        patient.requests.push({ id: randomBytes(12).toString('hex'), caregiverId: user.id, status: 'pending', createdAt: new Date().toISOString() });
        await save(); return reply(res, 201, { ok: true });
      }
      if (req.method === 'POST' && url.pathname === '/api/permission') {
        if (user.role !== 'patient') throw error(403, 'Only the patient can decide.');
        const b = await body(req); const request = user.requests.find(r => r.id === b.id);
        if (!request || !['approved', 'declined', 'revoked'].includes(b.status)) throw error(400, 'Invalid permission request.');
        request.status = b.status; request.updatedAt = new Date().toISOString(); await save(); return reply(res, 200, { ok: true });
      }
      throw error(404, 'Not found.');
    }
    if (req.method !== 'GET') throw error(405, 'Method not allowed.');
    const files = { '/': 'index.html', '/styles.css': 'styles.css', '/app.js': 'app.js', '/patients.js': 'patients.js', '/app/': 'companion/index.html', '/app/style.css': 'companion/style.css', '/app/script.js': 'companion/script.js' };
    if (url.pathname === '/app') { res.writeHead(302, { Location: '/app/' }); return res.end(); }
    const file = files[url.pathname];
    if (!file) throw error(404, 'Not found.');
    const content = await readFile(path.join(root, 'public', file));
    res.writeHead(200, { 'Content-Type': file.endsWith('.css') ? 'text/css' : file.endsWith('.js') ? 'text/javascript' : 'text/html', 'Cache-Control': 'no-cache' }); res.end(content);
  } catch (e) { if (!e.status) console.error(e); reply(res, e.status || 500, { error: e.status ? e.message : 'Something went wrong. Please try again.' }); }
});
server.listen(Number(process.env.PORT || 3000), '127.0.0.1', () => console.log(`SignalSpeak is ready at http://localhost:${server.address().port}`));
