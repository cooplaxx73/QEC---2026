// Website-only patient connection overview. Device controls belong in the phone app.
export function patientsPage() {
  return `<section class="page"><a class="back" href="#account">← My account & care circle</a><span class="eyebrow">YOUR CARE CONNECTIONS</span><h1>Your connected patients.</h1><p class="intro">View your approved patient connections while staying signed in to your own account.</p><div class="notice"><strong>All control settings are managed in the phone app.</strong> Cursor sensitivity, eye-closure duration, control bindings, and desktop read-aloud guidance are not configured on this website.</div><div id="patients-workspace" aria-live="polite">Loading connections…</div></section>`;
}

export async function mountPatients({ api, user, escape }) {
  const workspace = document.querySelector('#patients-workspace');
  try {
    const patients = await api('patients');
    if (!workspace.isConnected) return;
    if (!patients.length) {
      workspace.innerHTML = '<section class="panel"><h2>No approved patients yet.</h2><p>Request a connection from My account. Once the patient accepts, they will appear here.</p><a class="button" href="#account">Manage connections →</a></section>';
      return;
    }
    workspace.innerHTML = `<p class="small">Signed in as ${escape(user.name)}</p><div class="patient-toolbar"><label class="field">Select patient<select id="patient-switcher">${patients.map(p => `<option value="${escape(p.patientId)}">${escape(p.name)} · ${escape(p.patientId)}</option>`).join('')}</select></label></div><section class="panel" id="patient-detail"></section>`;
    const picker = workspace.querySelector('select');
    const requestedId = new URLSearchParams(location.hash.split('?')[1] || '').get('patientId');
    if (patients.some(p => p.patientId === requestedId)) picker.value = requestedId;
    function display() {
      const patient = patients.find(p => p.patientId === picker.value);
      workspace.querySelector('#patient-detail').innerHTML = `<span class="pill">${patient.owner ? 'Your patient profile' : 'Approved care connection'}</span><h2>${escape(patient.name)}</h2><p class="small">Patient ID: ${escape(patient.patientId)}</p><p>Continue in the phone app to manage control settings. Connecting on this website does not activate computer, camera, or microphone access.</p><div class="actions"><a class="button primary" href="#instructions">Read the setup guide →</a><a class="button" href="#account">Manage connections</a></div>`;
    }
    picker.addEventListener('change', display);
    display();
  } catch (e) { if (workspace.isConnected) workspace.textContent = e.message; }
}
