// Exercise application event flows without network or a browser process.
// Layout/visual rendering must still be checked in a real mobile browser.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
class Element {
  constructor() {
    this.children = []; this.childNodes = this.children; this.listeners = {}; this.attributes = {};
    this.value = ''; this.checked = false; this.hidden = false; this.disabled = false; this.textContent = '';
    this.classes = new Set(); this.style = {};
    this.offsetLeft=0; this.offsetTop=0; this.clientWidth=600; this.clientHeight=300;
    this.classList = {add:x=>this.classes.add(x), remove:x=>this.classes.delete(x),
      toggle:x=>{ if(this.classes.has(x)){this.classes.delete(x);return false;} this.classes.add(x);return true; }};
  }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children=nodes; this.childNodes=nodes; }
  cloneNode() { const node=new Element(); node.children=[...this.children]; node.childNodes=node.children; return node; }
  addEventListener(event, callback) { this.listeners[event] = callback; }
  setAttribute(key,value) { this.attributes[key]=value; }
  removeAttribute(key) { delete this.attributes[key]; if(key==='src') delete this.src; }
  close() { this.open=false; this.listeners.close?.(); }
  showModal() { this.open=true; }
  getBoundingClientRect() { return {left:0,top:0,width:600,height:300}; }
  setPointerCapture() {}
  releasePointerCapture() {}
  focus() { this.focused=true; }
  scrollIntoView() { this.scrolled=true; }
}
const elements = {};
const html = fs.readFileSync(path.join(root,'app/static/index.html'),'utf8');
for (const match of html.matchAll(/\bid="([^"]+)"/g)) elements[match[1]]=new Element();
const requests = [];
const storage = new Map();
let remoteJob;
const settings={favorites:['a@example.com','b@example.com'],scanner_ip:'172.16.60.252',ocr_available:true,password_saved:true,username:'from@example.com'};
const context=vm.createContext({
  document:{getElementById:id=>{assert.ok(elements[id],`Missing element ${id}`); return elements[id];}, createElement:()=>new Element()},
  localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
  confirm:()=>true, setTimeout:()=>1, clearTimeout:()=>{}, console,
  fetch: async (url, options={}) => {
    const data=options.body?JSON.parse(options.body):undefined; requests.push({url,data});
    let value;
    if(url==='/api/session') value={authenticated:false,csrf:'',version:'0.3.1',demo:false};
    else if(url==='/api/settings') value=settings;
    else if(url==='/api/edit') {remoteJob={...remoteJob,revision:remoteJob.revision+1,pdf_ready:false};value=remoteJob;}
    else if(url==='/api/prepare') {remoteJob={...remoteJob,status:'processing'};value=remoteJob;}
    else if(url==='/api/send') {remoteJob={...remoteJob,status:'sending'};value=remoteJob;}
    else if(url==='/api/delete') value={ok:true};
    else if(url.startsWith('/api/jobs/')) value=remoteJob;
    else throw Error('Unexpected request '+url);
    return {ok:true,status:200,json:async()=>value};
  }
});
vm.runInContext(fs.readFileSync(path.join(root,'app/static/app.js'),'utf8'),context);
const run = code=>vm.runInContext(code,context);
const setJob = patch => {
  remoteJob={id:'a'.repeat(32),status:'ready',pages:2,revision:1,mode:'Gray',dpi:150,
    quality:'high',ocr:false,pdf_ready:true,pdf_bytes:40000,estimated_bytes:50000,sent:false,error:'',delivery_uncertain:false,...patch};
  context.fixture=remoteJob; run('job={...fixture};pending=false;render()');
};
(async()=>{
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(elements['app-view'].hidden,true);
  await run('loadSettings()');
  assert.equal(elements['favorite-buttons'].children.length,2);
  elements['favorite-buttons'].children[1].listeners.click();
  assert.equal(elements.recipient.value,'b@example.com');
  elements['remember-recipient'].checked=true; run('rememberRecipient()');
  elements.recipient.value=''; run('rememberRecipient(true)');
  assert.equal(elements.recipient.value,'b@example.com');
  elements['remember-recipient'].checked=false; run('rememberRecipient()');
  assert.equal(storage.has('scanmail-recipient'),false);
  setJob();
  assert.equal(elements.send.disabled,false);
  assert.equal(elements.preview.children.length,2);
  run('openPreview(2)');
  assert.equal(elements['preview-dialog'].open,true);
  assert.match(elements['large-page'].src,/\/preview\/2\?v=1$/);
  elements['zoom-preview'].listeners.click();
  assert.equal(elements['zoom-preview'].attributes['aria-pressed'],'true');
  elements['close-preview'].listeners.click();
  assert.equal(elements['large-page'].src,undefined);
  setJob(); run('openPreview(1)');
  elements['start-crop'].listeners.click();
  assert.match(elements['large-page'].src,/\/full\/1\?v=1$/);
  assert.equal(elements['apply-crop'].disabled,true);
  elements['large-page'].listeners.load();
  assert.equal(elements['crop-overlay'].hidden,false);
  const pointer=(x,y)=>({clientX:x,clientY:y,pointerId:7,button:0,preventDefault(){}});
  // Drag backwards to exercise normalization, then save the selection.
  elements['crop-overlay'].listeners.pointerdown(pointer(480,240));
  elements['crop-overlay'].listeners.pointermove(pointer(120,60));
  elements['crop-overlay'].listeners.pointerup(pointer(120,60));
  assert.equal(elements['crop-left'].value,'20');
  assert.equal(elements['crop-bottom'].value,'80');
  await elements['apply-crop'].listeners.click();
  const cropRequest=requests.findLast(x=>x.url==='/api/edit').data;
  assert.equal(cropRequest.action,'crop');
  assert.deepEqual(cropRequest.box,[.2,.2,.8,.8]);
  setJob({crop_boxes:[[.2,.2,.8,.8],[0,0,1,1]]});run('openPreview(1)');
  elements['start-crop'].listeners.click();elements['large-page'].listeners.load();
  assert.equal(elements['crop-left'].value,'20');
  await elements['reset-crop'].listeners.click();
  assert.equal(requests.findLast(x=>x.url==='/api/edit').data.action,'uncrop');
  setJob(); run('openPreview(1)'); elements['start-crop'].listeners.click();
  elements['large-page'].listeners.load();elements['crop-left'].value='99.99';
  elements['crop-left'].listeners.input();
  assert.equal(elements['apply-crop'].disabled,true);
  elements['cancel-crop'].listeners.click();
  assert.equal(elements['crop-overlay'].hidden,true);
  setJob();
  await run('mutate({action:"rotate",page:1})');
  assert.equal(requests.findLast(x=>x.url==='/api/edit').data.revision,1);
  assert.equal(elements.send.disabled,true);
  assert.equal(elements.new.disabled,true);
  setJob(); elements.recipient.value='a@example.com';
  const event={preventDefault(){}};
  await elements['send-form'].listeners.submit(event);
  await elements['send-form'].listeners.submit(event);
  assert.equal(requests.filter(x=>x.url==='/api/send').length,1);
  setJob({sent:true,status:'sent'});
  assert.equal(elements['sent-panel'].hidden,false);
  assert.equal(elements.send.disabled,true);
  assert.equal(elements.scan.disabled,true);
  assert.equal(elements['scan-next'].disabled,false);
  await elements['scan-next'].listeners.click();
  assert.equal(run('job'),null);
  assert.equal(elements.scan.disabled,false);
  assert.equal(elements.mode.disabled,false);
  assert.equal(elements['sent-panel'].hidden,true);
  assert.equal(requests.at(-1).url,'/api/delete');
  setJob({delivery_uncertain:true,status:'error'});
  assert.equal(elements.send.disabled,true);
  assert.equal(elements.scan.disabled,true);
  console.log('Frontend flows passed: favorites, opt-in storage, preview/zoom, drag cropping/reset/validation, edits, double-submit lock, next document, uncertain delivery.');
})().catch(error=>{console.error(error);process.exitCode=1;});
