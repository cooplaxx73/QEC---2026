// Integrated phone dashboard. Original visual design: app branch.
// Shared account/device API integration: OpenAI Codex. No external libraries.
const $ = selector => document.querySelector(selector);
let me = null, patients = [], selected = '', state = null, generation = 0;
let activeCategory = 'all', period = 'All activity', entries = [], eventCursor = 0, saving = false;
let lastInput = Date.now(), lastTouch = 0;
let history = [], historyExhausted = false;
const labels = { cursor_sensitivity: 'Cursor sensitivity', cursor_smoothing: 'Cursor stabilization', blink_threshold: 'Eye closure threshold', click_hold_seconds: 'Blink hold time', blink_action: 'Blink selection action', zoom_enabled: 'Lean-forward zoom', zoom_lean_ratio: 'Lean threshold', zoom_factor: 'Zoom factor', low_light_enabled: 'Low-light adaptation', low_light_threshold: 'Low-light threshold', speech_rate: 'Read-aloud speed' };
const controls = [
 ['cursor_sensitivity', .25, 3, .05, '×'], ['cursor_smoothing', 0, .95, .05, ''],
 ['click_hold_seconds', .3, 2, .1, ' sec'], ['blink_threshold', .1, .95, .05, ''],
 ['blink_action', ['left_click','right_click','double_click']], ['zoom_enabled', 'boolean'],
 ['zoom_lean_ratio', 1.05, 2, .01, '×'], ['zoom_factor', 1.5, 4, .1, '×'],
 ['low_light_enabled','boolean'], ['low_light_threshold',0,255,1,''], ['speech_rate',80,260,1,' words/min']
];
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(route, data) {
 const res = await fetch('/api/' + route, {method:data===undefined?'GET':'POST',headers:data===undefined?{}:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});
 const result = await res.json();
 if(!res.ok) { const e=new Error(result.error);e.status=res.status;if(res.status===401&&me)showLogin('Session ended. Please sign in again.');throw e; }
 return result;
}
function notify(message) { $('#toast').textContent=message;$('#toast').classList.add('show');clearTimeout(notify.timer);notify.timer=setTimeout(()=>$('#toast').classList.remove('show'),4500); }
function showLogin(message='') { me=null;selected='';state=null;generation++;$('#login-screen').hidden=false;$('#app-screen').hidden=true;$('#login-error').textContent=message;$('#login-form').reset(); }
function showView(name) { document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id==='view-'+name));$('#dashboard-back').hidden=name==='home';document.querySelectorAll('.nav-item,.bottom-item').forEach(b=>b.classList.toggle('active',b.dataset.view===name));window.scrollTo(0,0); }
async function enter(user) {
 me=user;lastInput=Date.now();patients=await api('patients');
 $('#login-screen').hidden=true;$('#app-screen').hidden=false;$('#account-menu').hidden=true;
 document.querySelectorAll('.profile-chip>span:nth-child(2),.rail-bottom strong').forEach(el=>el.textContent=me.name);
 document.querySelectorAll('.avatar').forEach(el=>el.textContent=me.name.charAt(0).toUpperCase());
 $('#account-menu>span').textContent='Signed in as '+me.name;
 $('#patient-picker').innerHTML=patients.map(p=>`<option value="${escape(p.patientId)}">${escape(p.name)} · ${escape(p.patientId)}</option>`).join('');
 if(!patients.length){selected='';$('#connection-error').textContent='No approved patients yet. Use Manage care connections to request or approve a connection on the website.';$('#desktop-status').textContent='No patient selected';$('#integrated-settings').textContent='Choose an approved patient to access controls.';entries=[];renderLogs();return;}
 await selectPatient(patients[0].patientId);
}
async function selectPatient(id) {
 generation++;selected=id;state=null;entries=[];history=[];historyExhausted=false;eventCursor=0;$('#connection-error').textContent='';$('#integrated-settings').textContent='Loading patient controls…';renderLogs();await refresh(true);
}
function renderSettings() {
 if(!state)return;
 $('#integrated-settings').innerHTML=controls.map(([key,min,max,step,unit])=>{
 const val=state.settings[key],label=labels[key];
 if(min==='boolean')return `<div class="integrated-control"><label>${label}<input type="checkbox" data-key="${key}" ${val?'checked':''}></label></div>`;
 if(Array.isArray(min))return `<div class="integrated-control"><label>${label}<select data-key="${key}">${min.map(v=>`<option ${val===v?'selected':''} value="${v}">${v.replaceAll('_',' ')}</option>`).join('')}</select></label></div>`;
 return `<div class="integrated-control"><label for="control-${key}">${label}<output>${val}${unit}</output></label><input id="control-${key}" data-key="${key}" type="range" min="${min}" max="${max}" step="${step}" value="${val}" data-unit="${unit}"></div>`;
 }).join('');
 $('#integrated-settings').querySelectorAll('[data-key]').forEach(control=>{
 control.addEventListener('input',()=>{const out=control.parentElement.querySelector('output');if(out)out.textContent=control.value+control.dataset.unit;});
 control.addEventListener('change',async()=>{
  const id=selected,epoch=generation,revision=state.revision;
  const value=control.type==='checkbox'?control.checked:control.tagName==='SELECT'?control.value:Number(control.value);
  saving=true;$('#integrated-settings').querySelectorAll('input,select').forEach(el=>el.disabled=true);
  try{await api('care/settings',{patientId:id,revision,changes:{[control.dataset.key]:value}});if(epoch===generation)notify('Setting saved. Delivery depends on the desktop connection.');}
  catch(e){if(epoch===generation)notify(e.message);}
  finally{saving=false;if(epoch===generation)await refresh(true);}
 });
 });
}
async function refresh(force=false) {
 if(!me||!selected||saving)return;
 const id=selected,epoch=generation;
 try{
 const next=await api('care/state?patientId='+encodeURIComponent(id));
 if(epoch!==generation||id!==selected)return;
 const changed=!state||state.revision!==next.revision;state=next;
 $('#connection-error').textContent='';$('#desktop-status').textContent=state.connected?'● Desktop connected':'○ Desktop offline · changes saved for next connection';$('#desktop-status').dataset.online=state.connected;
 if(force||changed)renderSettings();
 history = [...new Map([...history, ...state.logs].map(e=>[e.id,e])).values()].sort((a,b)=>b.id-a.id);
 if (history.length < 200 || history.at(-1)?.id === 1) historyExhausted = true;
 updateEntries();
 renderTelemetry();
 renderLogs();
 const events=await api('care/events?patientId='+encodeURIComponent(id)+'&after='+eventCursor);
 if(epoch!==generation)return;
 for(const e of events){eventCursor=Math.max(eventCursor,e.id);if(e.type==='call'&&Date.now()/1000-(e.time||0)<120)notify(state.name+' is asking for caregiver support.');}
 }catch(e){if(epoch!==generation)return;$('#connection-error').textContent=e.message;$('#desktop-status').textContent='Connection unavailable';if(e.status===403){state=null;history=[];renderTelemetry();$('#integrated-settings').textContent='Access is no longer approved. Return to the website to review your care connections.';entries=[];renderLogs();}}
}
function activityDetail(e) {
 const d=e.details||{}, parts=[];
 if(e.kind==='gaze'&&typeof d.gaze_x==='number')parts.push('Estimated gaze '+Math.round(d.gaze_x*100)+'% from left, '+Math.round(d.gaze_y*100)+'% from top');
 if(typeof d.cursor_x==='number')parts.push('Cursor ('+d.cursor_x+', '+d.cursor_y+') px');
 if(d.screen_width)parts.push('Screen '+d.screen_width+'×'+d.screen_height);
 if(d.action)parts.push(d.action.replaceAll('_',' '));
 if(e.kind==='click'&&e.value>0)parts.push('Blink '+Number(e.value).toFixed(2)+' sec');
 if(e.kind==='calibration')parts.push('Calibration fit error '+(e.value*100).toFixed(1)+'%');
 if(e.kind==='key')parts.push('One key action · text not recorded');
 if(e.note)parts.push(e.note);
 return parts.join(' · ')||'Patient activity';
}
function updateEntries(){
 if(!state){entries=[];return;}
 entries=[...history.map(e=>({kind:e.kind,title:e.kind.replaceAll('_',' '),detail:activityDetail(e),time:e.time,source:'Desktop',category:'computer'})),...state.audit.map(e=>({title:e.action,detail:e.by+(e.changes?' · '+Object.entries(e.changes).map(([k,v])=>(labels[k]||k)+': '+v).join(', '):''),time:e.time,source:'Phone',category:e.action==='settings changed'?'settings':'privacy'}))].sort((a,b)=>b.time-a.time);
}
function renderTelemetry(){
 const t=state?.telemetry;$('#gaze-grid').replaceChildren();$('#click-markers').replaceChildren();$('#logging-choice').replaceChildren();
 if(!state){$('#telemetry-metrics').textContent='Select an approved patient.';$('#latest-gaze').textContent='';return;}
 const owner=patients.find(p=>p.patientId===selected)?.owner;
 $('#logging-choice').innerHTML=owner?'<label class="logging-consent"><input type="checkbox" id="logging-toggle" '+(state.logging?'checked':'')+'>Record estimated gaze, cursor and click positions, and interaction events. Approved caregivers can view these logs.</label>':'<p>Patient activity logging: <strong>'+(state.logging?'On':'Off')+'</strong>. Only the patient can change this choice.</p>';
 $('#logging-toggle')?.addEventListener('change',async e=>{const toggle=e.currentTarget,id=selected;toggle.disabled=true;try{await api('care/logging',{patientId:id,logging:toggle.checked});notify('Logging preference updated. The desktop receives it on its next poll.');await refresh();}catch(e){notify(e.message);toggle.checked=!toggle.checked;toggle.disabled=false;}});
 $('#telemetry-metrics').innerHTML=[['Gaze samples',t?.gazeSamples||0],['Clicks',t?.clicks||0],['Key actions',t?.keys||0],['Tracking losses',t?.trackingLosses||0]].map(([label,count])=>'<div><strong>'+count+'</strong><span>'+label+'</span></div>').join('');
 const heat=t?.heatmap||Array(60).fill(0),max=Math.max(1,...heat);
 heat.forEach((count,i)=>{const cell=document.createElement('span');cell.style.opacity=count?String(.15+.85*count/max):'0';cell.title='Column '+(i%10+1)+', row '+(Math.floor(i/10)+1)+': '+count+' gaze samples';$('#gaze-grid').append(cell);});
 const last=t?.latestGaze;
 if(last?.screen_width)$('#gaze-screen').style.aspectRatio=last.screen_width+'/'+last.screen_height;
 for(const e of history.filter(e=>e.kind==='click'&&e.details?.screen_width).slice(0,50)){
 const d=e.details,x=(d.cursor_x-(d.screen_left||0))/d.screen_width,y=(d.cursor_y-(d.screen_top||0))/d.screen_height;
 if(x<0||x>1||y<0||y>1)continue;
 const marker=document.createElement('span');marker.className='click-marker';marker.style.left=(x*100)+'%';marker.style.top=(y*100)+'%';marker.title=(d.action||'click')+' · '+new Date(e.time*1000).toLocaleString();$('#click-markers').append(marker);
 }
 $('#latest-gaze').textContent=last?'Last estimate: '+Math.round(last.gaze_x*100)+'% from left, '+Math.round(last.gaze_y*100)+'% from top · '+new Date(last.time*1000).toLocaleString():'No gaze samples received yet. Use the updated paired desktop with patient logging enabled.';
}
function filteredEntries(){const start=new Date();start.setHours(0,0,0,0);const cutoff=period==='Today'?start.getTime()/1000:period==='Last 7 days'?Date.now()/1000-7*86400:0;return entries.filter(e=>(activeCategory==='all'||(['gaze','click'].includes(activeCategory)?e.kind===activeCategory:e.category===activeCategory))&&e.time>=cutoff);}
function renderLogs(){
 $('#load-earlier').disabled = !state || historyExhausted;
 $('#log-page-status').textContent = state ? history.length+' of '+(state.telemetry?.total ?? history.length)+' retained patient events loaded; latest 200 audit entries shown.' : '';

 const list=$('#log-entries');list.replaceChildren();
 for(const e of filteredEntries()){
 const row=document.createElement('article');row.className='log-entry';
 row.innerHTML=`<span class="log-event"><i class="event-icon ${e.category==='settings'?'setting-event':e.category==='privacy'?'privacy-event':'click-event'}">•</i><span><strong>${escape(e.title)}</strong><small>${escape(e.detail)}</small></span></span><time>${escape(new Date(e.time*1000).toLocaleString())}</time><span class="source-tag ${e.source==='Phone'?'phone-tag':''}">${e.source}</span>`;
 list.append(row);
 }
 if(!list.children.length)list.innerHTML='<p class="log-empty">No recorded activity for this selection. Patient activity appears only when logging was enabled at signup.</p>';
 const totals={computer:0,settings:0,privacy:0};entries.forEach(e=>totals[e.category]++);const total=entries.length||1,a=totals.computer/total*100,b=a+totals.settings/total*100;
 $('#category-donut').style.background=`conic-gradient(#78977d 0 ${a}%,#c9b88f ${a}% ${b}%,#a8bdba ${b}% 100%)`;
 $('#donut-total').textContent=entries.length;$('#event-count').textContent=entries.length;$('.filter[data-category=all] span').textContent=entries.length;
 for(const key of Object.keys(totals))$('#count-'+key).textContent=totals[key];
 const chart=$('.chart-days');chart.replaceChildren();
 const days=Array.from({length:7},(_,i)=>{const date=new Date();date.setHours(0,0,0,0);date.setDate(date.getDate()-6+i);return{date,count:entries.filter(e=>e.time>=date.getTime()/1000&&e.time<date.getTime()/1000+86400).length};});
 const max=Math.max(1,...days.map(d=>d.count));
 $('.y-labels').innerHTML=`<span>${max}</span><span>${Math.round(max/2)}</span><span>0</span>`;
 for(const d of days){const column=document.createElement('div');column.className='day-column';const stack=document.createElement('div');stack.className='bar-stack';const bar=document.createElement('i');bar.className='bar-click';bar.style.height=(d.count/max*100)+'%';stack.append(bar);const label=document.createElement('small');label.textContent=d.date.toLocaleDateString(undefined,{weekday:'short'});column.append(stack,label);column.title=d.count+' recorded events';chart.append(column);}
 $('.chart-legend').textContent='Loaded recorded events per day';$('.log-summary strong').textContent='Recent recorded activity';
}
$('#login-form').addEventListener('submit',async e=>{e.preventDefault();const button=e.currentTarget.querySelector('button');button.disabled=true;$('#login-error').textContent='';try{const user=await api('login',{email:$('#username').value,password:$('#password').value});$('#password').value='';await enter(user);}catch(e){$('#login-error').textContent=e.message;}finally{button.disabled=false;}});
async function signOut(){try{await api('logout',{});}catch{}showLogin();showView('home');}
$('#signout').onclick=signOut;$('#signout-menu').onclick=signOut;
$('#patient-picker').onchange=e=>selectPatient(e.target.value);
$('#profile-menu-toggle').onclick=()=>{const menu=$('#account-menu');menu.hidden=!menu.hidden;$('#profile-menu-toggle').setAttribute('aria-expanded',String(!menu.hidden));};
 document.addEventListener('click',e=>{
 const nav=e.target.closest('[data-view]');if(nav)showView(nav.dataset.view);
 const opener=e.target.closest('[data-open]');if(opener)document.getElementById(opener.dataset.open).hidden=false;
 if(e.target.matches('[data-close]'))e.target.closest('.modal-backdrop').hidden=true;
 if(e.target.classList.contains('modal-backdrop'))e.target.hidden=true;
 });
 document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelectorAll('.modal-backdrop').forEach(m=>m.hidden=true);});
 $('#send-call-request').onclick=async()=>{if(!selected)return notify('Select an approved patient first.');const b=$('#send-call-request');b.disabled=true;try{await api('care/call',{patientId:selected});$('#camera-modal').hidden=true;notify('Connection request queued for the patient’s desktop. No camera or microphone was enabled.');await refresh();}catch(e){notify(e.message);}finally{b.disabled=false;}};
 document.querySelectorAll('.filter[data-category]').forEach(f=>f.onclick=()=>{document.querySelectorAll('.filter').forEach(el=>el.classList.remove('active'));f.classList.add('active');activeCategory=f.dataset.category;renderLogs();});
 $('.log-filters select').value='All activity';$('.log-filters select').onchange=e=>{period=e.target.value;renderLogs();};
 $('#export-logs').onclick=async()=>{if(!state)return notify('Select an approved patient first.');const id=selected,button=$('#export-logs');button.disabled=true;try{const all=await api('care/export?patientId='+encodeURIComponent(id));const blob=new Blob([JSON.stringify(all,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='signalspeak-'+id+'-logs.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}catch(e){notify(e.message);}finally{button.disabled=false;}};
 $('#load-earlier').onclick=async()=>{if(!selected||!history.length)return;const id=selected,epoch=generation,button=$('#load-earlier');button.disabled=true;try{const page=await api('care/logs?patientId='+encodeURIComponent(id)+'&before='+Math.min(...history.map(e=>e.id)));if(epoch!==generation)return;history=[...new Map([...history,...page.entries].map(e=>[e.id,e])).values()].sort((a,b)=>b.id-a.id);historyExhausted=page.nextBefore===null;updateEntries();renderLogs();}catch(e){notify(e.message);}finally{button.disabled=historyExhausted;}};
 document.querySelectorAll('.guide-link').forEach(b=>b.onclick=()=>{location.href='/#instructions';});
 document.querySelector('.guide-article .button').onclick=()=>location.href='/#instructions';
 ['pointerdown','keydown','scroll'].forEach(name=>window.addEventListener(name,()=>{lastInput=Date.now();if(me&&Date.now()-lastTouch>30000){lastTouch=Date.now();api('activity',{}).catch(()=>{});}},{passive:true}));
 setInterval(()=>{if(me&&Date.now()-lastInput>=15*60000){signOut();notify('Signed out after inactivity.');}else refresh();},3000);
 try{await enter(await api('me'));}catch{showLogin();}
