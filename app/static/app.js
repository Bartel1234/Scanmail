'use strict';
const $ = id => document.getElementById(id);
const BUSY = ['scanning', 'sending', 'processing'];
let cropState = null, previewPage = 0;
let csrf = '', job = null, settings = {}, timer = null, pageKey = '', pending = false;
const emptyPreview = $('preview').cloneNode(true);
const isBusy = () => pending || !!job && BUSY.includes(job.status);
const frozen = () => !!job && (job.sent || job.delivery_uncertain);
function notice(text, error = false) {
  $('notice').textContent = text;
  $('notice').className = 'notice' + (error ? ' error' : '');
  $('notice').hidden = false;
  clearTimeout(notice.timeout);
  notice.timeout = setTimeout(() => $('notice').hidden = true, error ? 15000 : 6000);
}
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
    body: JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== '/api/login') authenticated(false);
    const error = new Error(result.error || 'Forbindelsen blev afbrudt.');
    error.status = response.status;
    throw error;
  }
  return result;
}
function authenticated(ok) {
  $('login-view').hidden = ok; $('app-view').hidden = !ok;
  $('open-settings').hidden = !ok; $('logout').hidden = !ok;
  if (!ok) {
    clearTimeout(timer); job = null; pageKey = '';
    $('settings-dialog').close(); $('preview-dialog').close();
    $('large-page').removeAttribute('src');
    $('recipient').value = ''; $('body').value = ''; render();
  }
}
function rememberRecipient(read = false) {
  try {
    if (read) {
      $('remember-recipient').checked = localStorage.getItem('scanmail-remember') === '1';
      if ($('remember-recipient').checked) $('recipient').value = localStorage.getItem('scanmail-recipient') || '';
    } else if ($('remember-recipient').checked) {
      localStorage.setItem('scanmail-remember', '1');
      localStorage.setItem('scanmail-recipient', $('recipient').value.trim());
    } else {
      localStorage.removeItem('scanmail-remember'); localStorage.removeItem('scanmail-recipient');
    }
  } catch (_) { /* Browsers may disable local storage; mail still works. */ }
}
async function loadSettings() {
  settings = await api('/api/settings');
  $('printer-ip').textContent = settings.scanner_ip + ' · Ikke testet';
  $('settings-ip').textContent = settings.scanner_ip;
  $('favorites').replaceChildren(...settings.favorites.map(address => {
    const option = document.createElement('option'); option.value = address; return option;
  }));
  $('favorite-buttons').replaceChildren(...settings.favorites.map(address => {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'favorite secondary'; button.textContent = address;
    button.addEventListener('click', () => { $('recipient').value = address; $('recipient').focus(); });
    return button;
  }));
  $('mail-hint').textContent = settings.password_saved
    ? 'Afsender: ' + (settings.sender || settings.username)
    : 'Opsæt din mailkonto under Indstillinger før første afsendelse.';
  render();
}
function fileSize(bytes) {
  return bytes >= 1048576 ? (bytes / 1048576).toLocaleString('da-DK', {maximumFractionDigits: 1}) + ' MB'
    : Math.max(1, Math.round(bytes / 1024)) + ' kB';
}
function openPreview(number) {
  previewPage = number; cropState = null;
  $('crop-tools').hidden = true; $('crop-overlay').hidden = true;
  $('zoom-preview').hidden = false; $('start-crop').hidden = false;
  $('start-crop').disabled = isBusy() || frozen();
  $('preview-title').textContent = 'Side ' + number;
  $('large-page').src = '/api/jobs/' + job.id + '/preview/' + number + '?v=' + job.revision;
  $('large-page').alt = 'Forstørret side ' + number;
  $('large-page').classList.remove('zoomed');
  $('zoom-preview').textContent = 'Zoom ind'; $('zoom-preview').setAttribute('aria-pressed', 'false');
  $('preview-dialog').showModal();
}
function renderPages() {
  const key = job ? [job.id, job.revision, job.pages, isBusy(), frozen()].join(':') : 'empty';
  if (key === pageKey) return;
  pageKey = key;
  if (!job?.pages) {
    $('preview').replaceChildren(...[...emptyPreview.childNodes].map(node => node.cloneNode(true))); return;
  }
  $('preview').replaceChildren(...Array.from({length: job.pages}, (_, i) => {
    const n = i + 1;
    const figure = document.createElement('figure'); figure.className = 'page';
    const zoom = document.createElement('button'); zoom.className = 'page-preview'; zoom.type = 'button';
    zoom.setAttribute('aria-label', 'Se side ' + n + ' større');
    const image = document.createElement('img');
    image.src = '/api/jobs/' + job.id + '/thumb/' + n + '?v=' + job.revision;
    image.alt = 'Side ' + n; zoom.append(image); zoom.addEventListener('click', () => openPreview(n));
    const caption = document.createElement('figcaption'); caption.textContent = 'Side ' + n;
    const tools = document.createElement('div'); tools.className = 'page-tools';
    const actions = [
      ['↻ Rotér', 'rotate', null, false], ['↑', 'move', n - 1, n === 1],
      ['↓', 'move', n + 1, n === job.pages], ['Slet', 'delete', null, false]
    ];
    for (const [label, action, destination, edge] of actions) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'secondary';
      button.textContent = label; button.disabled = edge || isBusy() || frozen();
      button.setAttribute('aria-label', (action === 'move' ? (destination < n ? 'Flyt op' : 'Flyt ned') : label) + ', side ' + n);
      button.addEventListener('click', () => {
        if (action === 'delete' && !confirm('Slet side ' + n + '?')) return;
        mutate({action, page: n, destination});
      });
      tools.append(button);
    }
    figure.append(zoom, caption, tools); return figure;
  }));
}
function render() {
  const busy = isBusy(), locked = frozen(), pages = job?.pages || 0;
  const tooLarge = (job?.pdf_bytes || 0) > 17 * 1024 * 1024;
  if (job) {
    $('mode').value = job.mode; $('dpi').value = String(job.dpi);
    $('pdf-quality').value = job.quality; $('ocr').checked = job.ocr;
  }
  $('scan').disabled = busy || pages >= 20 || locked;
  $('new').disabled = busy || !job;
  $('mode').disabled = !!job; $('dpi').disabled = !!job;
  $('pdf-quality').disabled = busy || locked || !pages;
  $('ocr').disabled = busy || locked || !pages || settings.ocr_available === false;
  $('scan-label').textContent = job?.status === 'scanning' ? 'Scanner siden …' : pages ? 'Tilføj side' : 'Scan første side';
  $('send').disabled = busy || !pages || locked || !job?.pdf_ready || tooLarge;
  $('send').textContent = job?.status === 'sending' ? 'Sender dokument …' : job?.sent ? 'Afleveret til mailserver ✓' : 'Send dokument ↗';
  $('sent-panel').hidden = !job?.sent;
  $('scan-next').disabled = busy;
  $('recipient').disabled = busy || locked; $('subject').disabled = busy || locked; $('body').disabled = busy || locked;
  for (const button of $('favorite-buttons').children) button.disabled = busy || locked;
  $('page-count').textContent = pages + (pages === 1 ? ' side' : ' sider');
  const size = job?.pdf_ready ? fileSize(job.pdf_bytes) : pages ? 'ca. ' + fileSize(job.estimated_bytes) : '';
  $('pdf-size').textContent = pages ? (job.pdf_ready ? 'PDF: ' : 'Anslået størrelse: ') + size + (job.ocr ? ' · Søgbar tekst' : '') + (tooLarge ? ' · For stor til mail. Vælg Lille fil, færre sider eller download PDF.' : '') : 'Vælg PDF-kvalitet og OCR efter første scanning.';
  $('attachment-info').textContent = pages ? pages + (pages === 1 ? ' side' : ' sider') + ' · ' + size : 'Scan en side for at vedhæfte';
  $('download').hidden = !pages || !job?.pdf_ready || busy;
  if (job) $('download').href = '/api/jobs/' + job.id + '/pdf';
  $('prepare').hidden = !pages || !!job?.pdf_ready || busy || locked || job?.status !== 'error';
  $('edit-hint').hidden = !pages;
  const state = $('job-state');
  state.className = 'job-state' + (busy ? ' busy' : job?.status === 'error' ? ' error' : '');
  state.textContent = job?.error || (job?.status === 'scanning' ? 'Scanner … Lad papiret ligge, indtil siden er klar.'
    : job?.status === 'processing' ? job.progress || 'Klargør PDF …'
    : job?.status === 'sending' ? 'Sender din PDF til mailserveren …'
    : job?.sent ? 'Dokumentet er afleveret til mailserveren. Vælg Scan nyt dokument for at fortsætte.'
    : pages ? 'Tilføj flere sider, redigér siderne, eller send dokumentet.' : 'Klar til første side');
  renderPages();
}
async function prepare() {
  if (!job?.pages || frozen()) return;
  const id = job.id;
  job = {...job, status:'processing', progress:'Klargør PDF …'}; render();
  try {
    const result = await api('/api/prepare', {job_id:id});
    if (job?.id !== id) return;
    job = result; render(); clearTimeout(timer); timer = setTimeout(poll, 700);
  } catch (error) {
    if (job?.id === id) { job = {...job, status:'error', error:error.message}; render(); }
    throw error;
  }
}

async function poll() {
  clearTimeout(timer);
  if (!job) return;
  const id = job.id;
  try {
    const result = await api('/api/jobs/' + id);
    if (job?.id !== id) return;
    job = result; render();
    if (BUSY.includes(job.status)) timer = setTimeout(poll, 1200);
    else if (job.status === 'ready' && job.pages && !job.pdf_ready) await prepare();
  } catch (error) {
    notice(error.message, true);
    if (error.status === 404) { job = null; pageKey = ''; render(); }
    else if (job && error.status !== 401) timer = setTimeout(poll, 4000);
  }
}
async function mutate(data) {
  if (!job || isBusy() || frozen()) return;
  pending = true; render();
  try {
    job = await api('/api/edit', {job_id: job.id, revision: job.revision, ...data});
    if (job.pages) await prepare();
  } catch (error) { notice(error.message, true); if (job) await poll(); }
  finally { pending = false; render(); }
}
async function newDocument() {
  if (!job || isBusy()) return;
  if (!job.sent && !confirm('Start et nyt dokument? De nuværende sider slettes.')) return;
  pending = true; render();
  try {
    await api('/api/delete', {job_id: job.id}); clearTimeout(timer); job = null; pageKey = '';
    $('preview-dialog').close(); $('large-page').removeAttribute('src');
    $('subject').value = 'Scannet dokument'; $('body').value = '';
    if (!$('remember-recipient').checked) $('recipient').value = '';
    render(); $('scan').scrollIntoView({block: 'center'});
  } catch (error) { notice(error.message, true); }
  finally { pending = false; render(); }
}
$('new').addEventListener('click', newDocument);
$('scan-next').addEventListener('click', newDocument);
$('close-preview').addEventListener('click', () => $('preview-dialog').close());
$('preview-dialog').addEventListener('close', () => { cropState = null; $('crop-overlay').hidden = true; $('large-page').removeAttribute('src'); });
$('zoom-preview').addEventListener('click', () => {
  const zoomed = $('large-page').classList.toggle('zoomed');
  $('zoom-preview').textContent = zoomed ? 'Tilpas siden' : 'Zoom ind';
  $('zoom-preview').setAttribute('aria-pressed', String(zoomed));
});
// Crop coordinates are normalized to the full, currently rotated page.
function validCrop(box) {
  return box.every(Number.isFinite) && box[0] >= 0 && box[1] >= 0 && box[2] <= 1 && box[3] <= 1
    && box[2] - box[0] >= .001 && box[3] - box[1] >= .001;
}
function positionCropOverlay() {
  if (!cropState?.loaded) return;
  const image = $('large-page'), overlay = $('crop-overlay');
  overlay.style.left = image.offsetLeft + 'px'; overlay.style.top = image.offsetTop + 'px';
  overlay.style.width = image.clientWidth + 'px'; overlay.style.height = image.clientHeight + 'px';
}
function paintCrop(updateFields = true) {
  if (!cropState) return;
  const box = cropState.box, valid = validCrop(box);
  $('apply-crop').disabled = !valid || !cropState.loaded || isBusy() || frozen();
  $('crop-status').textContent = !cropState.loaded ? 'Henter hele siden …' : valid
    ? 'Valgt område: ' + Math.round((box[2] - box[0]) * 100) + '% bredde × ' + Math.round((box[3] - box[1]) * 100) + '% højde.'
    : 'Markér et større område inden for siden.';
  if (updateFields) ['left', 'top', 'right', 'bottom'].forEach((edge, i) => {
    $('crop-' + edge).value = String(Math.round(box[i] * 1000) / 10);
  });
  if (!valid) return;
  for (const id of ['crop-outline', 'crop-mask-hole']) {
    const rectangle = $(id);
    rectangle.setAttribute('x', String(box[0] * 1000)); rectangle.setAttribute('y', String(box[1] * 1000));
    rectangle.setAttribute('width', String((box[2] - box[0]) * 1000));
    rectangle.setAttribute('height', String((box[3] - box[1]) * 1000));
  }
}
function beginCrop() {
  if (!job || isBusy() || frozen()) return;
  cropState = {jobId:job.id, page:previewPage, revision:job.revision,
    box:[...(job.crop_boxes?.[previewPage - 1] || [0, 0, 1, 1])], loaded:false, drag:null};
  $('crop-tools').hidden = false; $('start-crop').hidden = true; $('zoom-preview').hidden = true;
  $('large-page').classList.remove('zoomed'); $('crop-overlay').hidden = true;
  $('large-page').src = '/api/jobs/' + job.id + '/full/' + previewPage + '?v=' + job.revision;
  paintCrop();
}
function cancelCrop() {
  if (!cropState) return;
  cropState = null; $('crop-tools').hidden = true; $('crop-overlay').hidden = true;
  $('start-crop').hidden = false; $('zoom-preview').hidden = false;
  $('large-page').src = '/api/jobs/' + job.id + '/preview/' + previewPage + '?v=' + job.revision;
  $('zoom-preview').textContent = 'Zoom ind'; $('zoom-preview').setAttribute('aria-pressed', 'false');
}
function cropPoint(event) {
  const rect = $('crop-overlay').getBoundingClientRect();
  return [Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
    Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height))];
}
function dragCrop(event) {
  if (!cropState?.drag || cropState.drag.pointerId !== event.pointerId) return;
  const [x, y] = cropPoint(event), {start} = cropState.drag;
  cropState.box = [Math.min(start[0], x), Math.min(start[1], y), Math.max(start[0], x), Math.max(start[1], y)];
  paintCrop();
}
$('start-crop').addEventListener('click', beginCrop);
$('cancel-crop').addEventListener('click', cancelCrop);
$('large-page').addEventListener('load', () => {
  if (!cropState) return;
  cropState.loaded = true; $('crop-overlay').hidden = false; positionCropOverlay(); paintCrop();
});
$('large-page').addEventListener('error', () => {
  if (cropState) { cropState.loaded = false; paintCrop(); notice('Siden kunne ikke hentes. Luk og åbn forhåndsvisningen igen.', true); }
});
if (typeof ResizeObserver !== 'undefined') new ResizeObserver(positionCropOverlay).observe($('large-page'));
globalThis.addEventListener?.('resize', positionCropOverlay);
$('crop-overlay').addEventListener('pointerdown', event => {
  if (!cropState?.loaded || event.isPrimary === false || event.button > 0) return;
  event.preventDefault();
  cropState.drag = {start:cropPoint(event), previous:[...cropState.box], pointerId:event.pointerId};
  $('crop-overlay').setPointerCapture(event.pointerId);
});
$('crop-overlay').addEventListener('pointermove', dragCrop);
$('crop-overlay').addEventListener('pointerup', event => {
  if (!cropState?.drag || cropState.drag.pointerId !== event.pointerId) return;
  dragCrop(event); cropState.drag = null;
  $('crop-overlay').releasePointerCapture(event.pointerId);
});
$('crop-overlay').addEventListener('pointercancel', () => {
  if (cropState?.drag) { cropState.box = cropState.drag.previous; cropState.drag = null; paintCrop(); }
});
for (const edge of ['left', 'top', 'right', 'bottom']) $('crop-' + edge).addEventListener('input', () => {
  if (!cropState) return;
  cropState.box = ['left', 'top', 'right', 'bottom'].map(name => $('crop-' + name).value.trim() === '' ? NaN : Number($('crop-' + name).value) / 100);
  paintCrop(false);
});
async function saveCrop(reset = false) {
  if (!cropState || isBusy() || frozen() || !cropState.loaded) return;
  if (!reset && !validCrop(cropState.box)) return;
  const snapshot = cropState;
  if (job.id !== snapshot.jobId || job.revision !== snapshot.revision) {
    notice('Dokumentet er ændret. Åbn siden igen før du beskærer.', true); return;
  }
  $('preview-dialog').close();
  await mutate({action:reset ? 'uncrop' : 'crop', page:snapshot.page, revision:snapshot.revision, box:snapshot.box});
}
$('apply-crop').addEventListener('click', () => saveCrop(false));
$('reset-crop').addEventListener('click', () => saveCrop(true));
$('remember-recipient').addEventListener('change', () => rememberRecipient());
$('pdf-quality').addEventListener('change', () => mutate({action:'options', quality:$('pdf-quality').value, ocr:$('ocr').checked}));
$('ocr').addEventListener('change', () => mutate({action:'options', quality:$('pdf-quality').value, ocr:$('ocr').checked}));
$('prepare').addEventListener('click', async () => { try { await prepare(); } catch (error) { notice(error.message,true); } });
$('login-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true;
  try {
    const result = await api('/api/login', {password:$('login-password').value});
    csrf = result.csrf; $('login-password').value = ''; authenticated(true);
    rememberRecipient(true); await loadSettings();
  } catch (error) { notice(error.message,true); } finally { button.disabled = false; }
});
$('logout').addEventListener('click', async () => {
  try { await api('/api/logout', {}); authenticated(false); } catch (error) { notice(error.message,true); }
});
$('scan').addEventListener('click', async () => {
  if (isBusy() || frozen()) return;
  pending = true; render();
  try {
    job = await api('/api/scan', {job_id:job?.id, dpi:Number($('dpi').value), mode:$('mode').value});
    render(); clearTimeout(timer); timer = setTimeout(poll, 700);
  } catch (error) { notice(error.message,true); } finally { pending = false; render(); }
});
$('send-form').addEventListener('submit', async event => {
  event.preventDefault(); if (!job || isBusy() || frozen() || !job.pdf_ready) return;
  pending = true; render();
  try {
    job = await api('/api/send', {job_id:job.id, revision:job.revision, recipient:$('recipient').value, subject:$('subject').value, body:$('body').value});
    rememberRecipient(); render(); clearTimeout(timer); timer = setTimeout(poll, 700);
  } catch (error) { notice(error.message,true); } finally { pending = false; render(); }
});
$('open-settings').addEventListener('click',()=>{for(const [id,key] of [['smtp-host','host'],['smtp-port','port'],['smtp-tls','tls'],['smtp-user','username'],['smtp-sender','sender']])$(id).value=settings[key]??'';$('preset').value=settings.host==='smtp.gmail.com'?'gmail':'custom';$('smtp-pass').value='';$('password-saved').textContent=settings.password_saved?'allerede gemt':'';$('favorite-list').value=(settings.favorites||[]).join('\n');$('test-result').hidden=true;$('settings-dialog').showModal();});
$('close-settings').addEventListener('click',()=>$('settings-dialog').close());
$('preset').addEventListener('change',()=>{if($('preset').value==='gmail'){$('smtp-host').value='smtp.gmail.com';$('smtp-port').value='587';$('smtp-tls').value='starttls';}});
$('settings-form').addEventListener('submit',async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;try{await api('/api/settings',{host:$('smtp-host').value,port:Number($('smtp-port').value),tls:$('smtp-tls').value,username:$('smtp-user').value,password:$('smtp-pass').value,sender:$('smtp-sender').value,favorites:$('favorite-list').value.split('\n').filter(x=>x.trim())});$('smtp-pass').value='';await loadSettings();$('settings-dialog').close();notice('Indstillingerne er gemt.');}catch(error){notice(error.message,true);}finally{button.disabled=false;}});
$('test-scanner').addEventListener('click',async()=>{const button=$('test-scanner');button.disabled=true;$('test-result').hidden=false;$('test-result').textContent='Kontakter scanneren … Det kan tage op til 45 sekunder.';try{const result=await api('/api/scanner-test',{});$('test-result').textContent=(result.ok?'Scannerdriveren kunne åbne enheden. Prøv nu en fysisk scanning.\n\n':'Forbindelsen kunne ikke bekræftes. Kontrollér HP-plugin og netværk.\n\n')+result.detail;$('printer-ip').textContent=settings.scanner_ip+(result.ok?' · Forbindelse testet':' · Test fejlede');}catch(error){$('test-result').textContent=error.message;}finally{button.disabled=false;}});

(async () => {
  try {
    const session = await api('/api/session'); csrf = session.csrf;
    $('version').textContent = session.version; $('demo-banner').hidden = !session.demo;
    authenticated(session.authenticated);
    if (session.authenticated) { job = session.job; rememberRecipient(true); await loadSettings(); if (job) await poll(); }
  } catch (error) { notice('Kunne ikke kontakte ScanMail: ' + error.message, true); }
})();
