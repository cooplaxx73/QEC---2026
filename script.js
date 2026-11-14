// Purpose: Power the clickable visual demo, sample activity feed, and prototype dialogs.
const loginScreen = document.querySelector('#login-screen');
const appScreen = document.querySelector('#app-screen');
const toast = document.querySelector('#toast');
const sampleLogs = [
  ['Left click', 'Computer action · Button activated', '10:42:18 AM', 'Laptop', 'click-event', '↖', 'computer'],
  ['Cursor sensitivity changed', 'Setting · 65% → 68%', '10:38:04 AM', 'Phone', 'setting-event', '☷', 'settings'],
  ['Right click', 'Computer action · Context menu opened', '10:31:52 AM', 'Laptop', 'click-event', '↗', 'computer'],
  ['Camera access request approved', 'Privacy · Video call requested', '10:20:11 AM', 'Phone', 'privacy-event', '♧', 'privacy'],
  ['Cursor moved', 'Computer action · 4.2 seconds', '10:16:07 AM', 'Laptop', 'click-event', '⌁', 'computer'],
  ['Double blink', 'Gesture · Select action', '10:12:33 AM', 'Laptop', 'click-event', '◉', 'computer'],
];
const activity = [...sampleLogs];
let toastTimer;
let activeCategory = 'all';

function notify(message) {
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 2600);
}

function showView(name) {
  document.querySelectorAll('.view').forEach(view => view.classList.toggle('active', view.id === `view-${name}`));
  document.querySelector('#dashboard-back').hidden = name === 'home';
  document.querySelectorAll('[data-view]').forEach(button => {
    const active = button.dataset.view === name;
    if (button.classList.contains('nav-item') || button.classList.contains('bottom-item')) button.classList.toggle('active', active);
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

document.querySelector('#login-form').addEventListener('submit', event => {
  event.preventDefault();
  loginScreen.hidden = true;
  appScreen.hidden = false;
  notify('Welcome to your shared care space.');
});

function signOut() {
  appScreen.hidden = true;
  loginScreen.hidden = false;
  document.querySelector('#login-form').reset();
  document.querySelector('#account-menu').hidden = true;
  document.querySelector('#profile-menu-toggle').setAttribute('aria-expanded', 'false');
  showView('home');
}
document.querySelector('#signout').addEventListener('click', signOut);
document.querySelector('#signout-menu').addEventListener('click', signOut);
document.querySelector('#profile-menu-toggle').addEventListener('click', event => {
  event.stopPropagation();
  const menu = document.querySelector('#account-menu');
  menu.hidden = !menu.hidden;
  event.currentTarget.setAttribute('aria-expanded', String(!menu.hidden));
});
document.addEventListener('click', event => {
  if (!event.target.closest('.account-area')) {
    document.querySelector('#account-menu').hidden = true;
    document.querySelector('#profile-menu-toggle').setAttribute('aria-expanded', 'false');
  }
});

document.addEventListener('click', event => {
  const nav = event.target.closest('[data-view]');
  if (nav) {
    showView(nav.dataset.view);
    if (nav.dataset.view === 'settings') notify('Settings changes are recorded in the activity log.');
  }
  const opener = event.target.closest('[data-open]');
  if (opener) document.getElementById(opener.dataset.open).hidden = false;
  if (event.target.matches('[data-close]')) event.target.closest('.modal-backdrop').hidden = true;
  if (event.target.classList.contains('modal-backdrop')) event.target.hidden = true;
});

document.addEventListener('keydown', event => {
  if (event.key === 'Escape') document.querySelectorAll('.modal-backdrop:not([hidden])').forEach(modal => { modal.hidden = true; });
});

function renderLogs() {
  const rows = activeCategory === 'all' ? activity : activity.filter(entry => entry[6] === activeCategory);
  const container = document.querySelector('#log-entries');
  container.replaceChildren();
  rows.forEach(([title, detail, time, source, iconClass, glyph]) => {
    const row = document.createElement('article');
    row.className = 'log-entry';
    row.innerHTML = `<span class="log-event"><i class="event-icon ${iconClass}"></i><span><strong></strong><small></small></span></span><time></time><span class="source-tag"></span>`;
    row.querySelector('.event-icon').textContent = glyph;
    row.querySelector('strong').textContent = title;
    row.querySelector('small').textContent = detail;
    row.querySelector('time').textContent = time;
    row.querySelector('.source-tag').textContent = source;
    if (source === 'Phone') row.querySelector('.source-tag').classList.add('phone-tag');
    container.append(row);
  });
  if (!rows.length) {
    const empty = document.createElement('p');
    empty.className = 'log-empty';
    empty.textContent = 'No activity in this category yet.';
    container.append(empty);
  }
}

function appendActivity(title, detail, source = 'Phone', iconClass = 'setting-event', glyph = '•') {
  const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const category = iconClass === 'setting-event' ? 'settings' : iconClass === 'privacy-event' ? 'privacy' : 'computer';
  activity.unshift([title, detail, time, source, iconClass, glyph, category]);
  document.querySelector('#event-count').textContent = String(activity.length);
  document.querySelector('.filter[data-category="all"] span').textContent = String(activity.length);
  renderLogs();
}

document.querySelectorAll('[data-setting]').forEach(control => {
  control.addEventListener('input', () => {
    const output = control.parentElement.querySelector('output');
    output.value = control.dataset.setting === 'blink' ? `${(Number(control.value) / 10).toFixed(1)} sec` : `${control.value}%`;
    const label = control.dataset.setting === 'blink' ? 'Blink hold time' : 'Cursor sensitivity';
    appendActivity(`${label} changed`, `New value · ${output.value}`, 'Phone', 'setting-event', '☷');
    notify(`${label} updated and added to the activity log.`);
  });
});

document.querySelectorAll('.switch input, .setting-row select').forEach(control => {
  control.addEventListener('change', () => {
    const label = control.closest('.setting-row, .setting-heading')?.querySelector('strong, h2')?.textContent || control.getAttribute('aria-label') || 'Control setting';
    const value = control.type === 'checkbox' ? (control.checked ? 'on' : 'off') : control.value;
    appendActivity(`${label} changed`, `New value · ${value}`, 'Phone', 'setting-event', '☷');
    notify('Setting updated and recorded.');
  });
});

document.querySelector('#send-call-request').addEventListener('click', () => {
  document.querySelector('#camera-modal').hidden = true;
  appendActivity('Video call requested', 'Waiting for camera and microphone approval', 'Phone', 'privacy-event', '♧');
  notify('Request shown. Your calling software would open after approval.');
});

document.querySelector('#export-logs').addEventListener('click', () => {
  const json = activity.map(([action, details, time, source]) => ({ action, details, time, source }));
  const file = new Blob([JSON.stringify(json, null, 2)], { type: 'application/json' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(file);
  link.download = 'signalspeak-activity-demo.json';
  link.click();
  URL.revokeObjectURL(link.href);
  appendActivity('Activity log exported', 'JSON file downloaded', 'Phone', 'privacy-event', '↓');
  notify('Demo activity exported as JSON.');
});

document.querySelector('#confirm-delete').addEventListener('click', () => {
  if (!document.querySelector('#delete-password').value) {
    notify('Enter the account password to continue.');
    return;
  }
  document.querySelector('#delete-modal').hidden = true;
  document.querySelector('#delete-password').value = '';
  notify('Password accepted in demo. No log data was deleted.');
});

document.querySelector('#show-more').addEventListener('click', () => notify('Earlier activity will appear here in the full app.'));
document.querySelectorAll('.filter[data-category]').forEach(filter => filter.addEventListener('click', () => {
  document.querySelectorAll('.filter').forEach(item => item.classList.remove('active'));
  filter.classList.add('active');
  activeCategory = filter.dataset.category;
  renderLogs();
}));
document.querySelectorAll('.guide-link').forEach(item => item.addEventListener('click', () => {
  document.querySelectorAll('.guide-link').forEach(link => link.classList.remove('selected'));
  item.classList.add('selected');
  notify(`${item.querySelector('strong').textContent} guide selected.`);
}));

renderLogs();

