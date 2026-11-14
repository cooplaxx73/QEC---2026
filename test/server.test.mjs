import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { once } from 'node:events';

test('accounts, private storage, and patient-owned connection decisions', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'signalspeak-test-'));
  const child = spawn(process.execPath, ['server.mjs'], { env: { ...process.env, PORT: '0', SIGNALSPEAK_DATA_DIR: dir }, stdio: ['ignore', 'pipe', 'pipe'] });
  try {
    const output = await Promise.race([once(child.stdout, 'data'), once(child, 'exit').then(() => { throw new Error('Server exited'); }), new Promise((_, reject) => setTimeout(() => reject(new Error('Startup timeout')), 10000).unref())]);
    const base = String(output[0]).match(/http:\/\/localhost:\d+/)[0];
    async function call(route, data, cookie) {
      const res = await fetch(base + route, { method: data === undefined ? 'GET' : 'POST', headers: { ...(data === undefined ? {} : { 'Content-Type': 'application/json' }), ...(cookie ? { Cookie: cookie } : {}) }, body: data === undefined ? undefined : JSON.stringify(data) });
      return { status: res.status, body: await res.json(), cookie: res.headers.get('set-cookie')?.split(';')[0] };
    }
    const profile = { name: 'Demo Patient', email: 'patient@example.test', password: 'demo-password-123', role: 'patient', consent: true };
    assert.equal((await call('/api/register', { ...profile, consent: false })).status, 400);
    const patient = await call('/api/register', profile);
    assert.equal(patient.status, 201); assert.match(patient.body.patientId, /^SS-/); assert.equal(patient.body.hash, undefined);
    assert.equal((await call('/api/register', profile)).status, 409);
    assert.equal((await call('/api/me')).status, 401);
    assert.equal((await call('/api/login', { email: profile.email, password: 'wrong' })).status, 401);
    const caregiver = await call('/api/register', { ...profile, role: 'caregiver', name: '<Caregiver>', email: 'care@example.test' });
    assert.equal((await call('/api/connections', { patientId: patient.body.patientId }, caregiver.cookie)).status, 201);
    assert.equal((await call('/api/connections', { patientId: patient.body.patientId }, caregiver.cookie)).status, 409);
    const requests = await call('/api/connections', undefined, patient.cookie);
    assert.equal(requests.body[0].status, 'pending');
    const id = requests.body[0].id;
    assert.deepEqual((await call('/api/patients', undefined, caregiver.cookie)).body, []);
    assert.equal((await call('/api/permission', { id, status: 'approved' }, caregiver.cookie)).status, 403);
    const stranger = await call('/api/register', { ...profile, email: 'other@example.test' });
    assert.equal((await call('/api/permission', { id, status: 'approved' }, stranger.cookie)).status, 400);
    assert.equal((await call('/api/permission', { id, status: 'approved' }, patient.cookie)).status, 200);
    const approved = await call('/api/connections', undefined, caregiver.cookie);
    assert.equal(approved.body[0].status, 'approved'); assert.equal(approved.body[0].email, undefined);
    assert.equal((await call('/api/patients', undefined, caregiver.cookie)).body.length, 1);
    // Patient switching lists approved connections only; no website control settings.
    assert.equal((await call('/api/patient-settings?patientId=' + patient.body.patientId, undefined, patient.cookie)).status, 404);
    assert.equal((await call('/api/patient-settings', { patientId: patient.body.patientId, settings: {} }, patient.cookie)).status, 404);
    await call('/api/connections', { patientId: stranger.body.patientId }, caregiver.cookie);
    const otherRequests = await call('/api/connections', undefined, stranger.cookie);
    await call('/api/permission', { id: otherRequests.body[0].id, status: 'approved' }, stranger.cookie);
    assert.equal((await call('/api/patients', undefined, caregiver.cookie)).body.length, 2);
    const secondCaregiver = await call('/api/register', { ...profile, name: 'Second Caregiver', role: 'caregiver', email: 'second-care@example.test' });
    await call('/api/connections', { patientId: patient.body.patientId }, secondCaregiver.cookie);
    const secondRequest = (await call('/api/connections', undefined, patient.cookie)).body.find(r => r.caregiverId === secondCaregiver.body.id);
    await call('/api/permission', { id: secondRequest.id, status: 'approved' }, patient.cookie);
    assert.equal((await call('/api/permission', { id, status: 'revoked' }, patient.cookie)).status, 200);
    assert.equal((await call('/api/connections', undefined, caregiver.cookie)).body[0].status, 'revoked');
    assert.equal((await call('/api/patients', undefined, caregiver.cookie)).body.length, 1);
    const disk = await readFile(path.join(dir, 'accounts.json'), 'utf8');
    assert.ok(!disk.includes(profile.password)); assert.ok(JSON.parse(disk)[0].hash);
    assert.equal((await fetch(base + '/data/accounts.json')).status, 404);
    assert.equal((await fetch(base + '/')).status, 200);
    assert.equal((await fetch(base + '/app.js')).status, 200);
    assert.equal((await fetch(base + '/api/logout', { method: 'POST', headers: { Origin: 'https://untrusted.example', Cookie: patient.cookie } })).status, 403);
    await call('/api/logout', {}, patient.cookie);
    assert.equal((await call('/api/me', undefined, patient.cookie)).status, 401);
    assert.equal((await call('/api/login', { email: profile.email, password: profile.password })).status, 200);
  } finally { child.kill(); await once(child, 'exit'); await rm(dir, { recursive: true, force: true }); }
});
