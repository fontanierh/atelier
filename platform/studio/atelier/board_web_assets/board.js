"use strict";
const $ = id => document.getElementById(id);
const icons = {
  messages:'<path d="M21 11a8 8 0 0 1-8 8H7l-4 3V11a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8Z"/><path d="M8 9h8M8 13h5"/>',
  agents:'<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6M21 20v-2a6 6 0 0 0-4-5"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  send:'<path d="M21.5 2.5 10.5 13.5M21.5 2.5l-7 19-4-8-8-4 19-7Z"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  back:'<path d="m15 5-7 7 7 7"/>',
  chevron:'<path d="m6 9 6 6 6-6"/>',
  right:'<path d="m9 5 7 7-7 7"/>',
  down:'<path d="M12 5v14M5 12l7 7 7-7"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  close:'<path d="M6 6l12 12M18 6 6 18"/>',
  file:'<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z"/><path d="M14 3v5h5"/>',
  play:'<path d="M8 5v14l11-7L8 5Z"/>',
  thread:'<path d="M7 8h10M7 12h6"/><path d="M21 12a8 8 0 0 1-8 8H5l-2 2V12a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8Z"/>',
  reply:'<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 6 6v5"/>',
  board:'<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
  render:'<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
};
function node(tag, cls, text) { const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=text; return n; }
function icon(name) { const n=node("span","icon"); n.innerHTML=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]||icons.messages}</svg>`; return n; }
document.querySelectorAll("[data-icon]").forEach(n=>n.append(icon(n.dataset.icon)));
const names={info:"Info",request:"Request",handoff:"Handoff",blocked:"Blocked",release:"Release",evidence:"Evidence",ack:"Ack",alert:"Alert"};
const VIEWS=["messages","agents","render"];
const desktop=matchMedia("(min-width:1100px)"), touch=matchMedia("(hover:none)");
let state=null, selectedAgent="", records=new Map(), expanded=new Set(), deliveryOpen=new Set(), logShown=12;
let loading=false, requestNumber=0, controller=null, historyComplete=false, sending=false, failed=false;
let feedSignature="", agentsSignature="", scheduleSignature="", contextSignature="";
let draftKey=null, draftBody="", draftTopic="", draftRecipient="*", recipientSignature="", previewRequest=0;
let stickToBottom=true, prepending=false, lastSeenId=0, newestShown=0, statusTimer=0, feedPainted=false;
let showSystem=true, uploads=[], thread=null;
try { showSystem=localStorage.getItem("atelier.board.notices")!=="hidden"; } catch {}
$("showSystem").checked=showSystem;

// The app shell follows the visual viewport so the composer stays above the on-screen keyboard.
let fullHeight=0, viewportWidth=0, keyboardOpen=false;
function fitViewport() {
  const vv=window.visualViewport, root=document.documentElement.style, height=vv?vv.height:innerHeight;
  root.setProperty("--app-height",`${height}px`);root.setProperty("--app-top",`${vv?vv.offsetTop:0}px`);
  if(innerWidth!==viewportWidth){viewportWidth=innerWidth;fullHeight=height;}
  fullHeight=Math.max(fullHeight,height);
  // A keyboard dismissed without leaving the field (Android back, iOS "Done") should bring the tab bar back.
  const open=fullHeight-height>120;
  if(keyboardOpen&&!open&&touch.matches&&document.activeElement===$("message"))$("message").blur();
  keyboardOpen=open;
}
window.visualViewport?.addEventListener("resize",fitViewport);window.visualViewport?.addEventListener("scroll",fitViewport);
addEventListener("resize",fitViewport);fitViewport();

function persistDraft() {
  try { localStorage.setItem("atelier.board.draft",JSON.stringify({body:$("message").value,topic:$("broadcastTopic").value,recipient:$("recipient").value||draftRecipient,key:draftKey,
    files:uploads.filter(u=>u.id).map(({id,name,mime,size})=>({id,name,mime,size}))})); } catch {}
}
try {
  const draft=JSON.parse(localStorage.getItem("atelier.board.draft")||"null");
  if(draft) {
    $("message").value=draft.body||""; if([...$("broadcastTopic").options].some(o=>o.value===draft.topic))$("broadcastTopic").value=draft.topic;
    draftKey=draft.key; draftBody=$("message").value; draftTopic=$("broadcastTopic").value;draftRecipient=draft.recipient||"*";
    uploads=(draft.files||[]).map(f=>({...f,key:f.id,status:"done",progress:100,preview:`/api/attachment/${f.id}/${encodeURIComponent(f.name)}`}));
  }
} catch {}

function markdown(container, html, raw="") {
  container.classList.add("markdown");
  if(typeof html!=="string") {container.textContent=raw;return;}
  // HTML comes exclusively from the server's HTML-disabled Markdown renderer.
  const template=document.createElement("template");template.innerHTML=html;container.replaceChildren(template.content);
  container.querySelectorAll("table").forEach(table=>{const wrap=node("div","table-scroll");table.replaceWith(wrap);wrap.append(table);});
}
// Ledger text is plain; only `code` spans are styled, everything else stays text.
function inline(text) { const span=node("span"); text.split("`").forEach((part,i)=>span.append(i%2?node("code","",part):document.createTextNode(part))); return span; }
function hue(name) { let h=0; for(const c of name)h=(h*31+c.charCodeAt(0))%360; return h; }
function initials(name) { return name.replace(/[^a-z0-9]/gi," ").trim().split(/\s+/).slice(0,2).map(w=>w[0]).join("").toUpperCase()||"?"; }
function statusOf(agent) { return !agent?"":agent.delivery_error?"error":agent.listening?"live":"idle"; }
function orb(name, agent) {
  const o=node("span","orb");
  if(name==="*"||!name){o.classList.add("everyone");o.append(icon("agents"));return o;}
  o.textContent=initials(name).slice(0,1);o.style.setProperty("--hue",hue(name));
  if(agent&&!agent.stop){const badge=node("span","badge "+statusOf(agent));badge.style.setProperty("--delay",`${(hue(name)%9)*.29}s`);o.append(badge);}
  return o;
}
function clock(timestamp) { return new Date(timestamp*1000).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}); }
function dayLabel(timestamp) {
  const date=new Date(timestamp*1000), today=new Date(), yesterday=new Date(Date.now()-864e5);
  if(date.toDateString()===today.toDateString())return "Today";
  if(date.toDateString()===yesterday.toDateString())return "Yesterday";
  return date.toLocaleDateString([], {weekday:"short",month:"short",day:"numeric"});
}
function sizeText(size) { return size<1024?`${size} bytes`:size<1048576?`${(size/1024).toFixed(0)} KB`:size<1073741824?`${(size/1048576).toFixed(1)} MB`:`${(size/1073741824).toFixed(1)} GB`; }
function kindOf(mime) { return /^image\//.test(mime)?"image":/^video\//.test(mime)?"video":/^audio\//.test(mime)?"audio":"file"; }
function agentStatus(a) { return a.stop?"Retired":a.delivery_error?"Delivery retrying":a.listening?"Listening":"Offline"; }
function isSystem(m) { return /(^|-)watch$/.test(m.sender); }
function liveAgents() { return state?state.agents.filter(a=>!a.stop):[]; }
function snippetless(text) { return text.replace(/(^|\n\n)Attachments \(files on this machine\):[\s\S]*$/,""); }
function snippet(text) { return text.replace(/\n\nAttachments \(files on this machine\):[\s\S]*$/,"").replace(/^Attachments \(files on this machine\):[\s\S]*$/,"Attachment").replace(/[*_`#>]+/g,"").replace(/\s+/g," ").trim().slice(0,140); }

/* Views: one pane at a time on phones, all three side by side on wide screens. */
function setView(next, animate=true) {
  const app=$("app"), from=VIEWS.indexOf(app.dataset.view), to=VIEWS.indexOf(next);
  app.dataset.view=next;$("tabbar").style.setProperty("--tab",to);
  document.querySelectorAll(".tab").forEach(tab=>{if(tab.dataset.view===next)tab.setAttribute("aria-current","page");else tab.removeAttribute("aria-current");});
  if(from!==to&&animate&&!desktop.matches) {
    const pane=$({messages:"chatPane",agents:"agentsPane",render:"renderPane"}[next]);
    pane.style.setProperty("--dir",to>from?1:-1);pane.classList.remove("entering");void pane.offsetWidth;pane.classList.add("entering");
    setTimeout(()=>pane.classList.remove("entering"),900);
  }
  // Coming back to the conversation lands on its latest message and keeps following new ones.
  if(next==="messages"){stickToBottom=true;requestAnimationFrame(()=>{scrollToLatest();markSeen();});}
}
document.querySelectorAll(".tab").forEach(tab=>tab.addEventListener("click",()=>{
  if(tab.dataset.view==="messages"&&$("app").dataset.view==="messages"){if(thread)navBack();else scrollToLatest(true);}
  setView(tab.dataset.view);
}));
document.querySelectorAll(".render-pane .card, .render-pane .stack > .eyebrow").forEach((n,i)=>n.style.setProperty("--i",i));
let conversationMode="dm";
function selectAgent(name, mode="dm", view="messages", animate=true) {
  if(thread)closeThread();
  if(!name)navForget("dm");
  selectedAgent=name;conversationMode=mode;
  const agent=state?.agents.find(a=>a.agent===name&&!a.stop);
  const target=name===""?"*":agent?name:null;
  if(target&&$("recipient").value!==target&&[...$("recipient").options].some(o=>o.value===target&&!o.disabled)){$("recipient").value=target;draftChanged();}
  setView(view,animate);agentsSignature="";renderAgents();renderHeader();refreshFilters();
}
$("backButton").addEventListener("click",()=>nav.length?navBack():selectAgent(""));
document.querySelectorAll("#modeSwitch button").forEach(b=>b.addEventListener("click",()=>{if(selectedAgent&&b.dataset.mode!==conversationMode)selectAgent(selectedAgent,b.dataset.mode);}));

/* Search and filters */
$("searchToggle").addEventListener("click",()=>{
  const show=$("searchBar").hidden;$("searchBar").hidden=!show;$("searchToggle").setAttribute("aria-expanded",String(show));
  if(show&&!touch.matches)$("search").focus();
  else if($("search").value||$("topicFilter").value){$("search").value="";$("topicFilter").value="";syncPills();refreshFilters();}
  $("searchToggle").classList.toggle("active",show);
});
function query(before=0) { const q=new URLSearchParams(); if(selectedAgent)q.set(conversationMode==="dm"?"dm":"agent",selectedAgent); if($("search").value.trim())q.set("q",$("search").value.trim()); if($("topicFilter").value)q.set("topic",$("topicFilter").value); if(before)q.set("before",before); return q.toString(); }
function refreshFilters() { settle(1500); records.clear(); feedSignature=""; historyComplete=false; stickToBottom=true; prepending=false; lastSeenId=0; feedPainted=false; load(true); }
let searchTimer;
$("search").addEventListener("input",()=>{clearTimeout(searchTimer);searchTimer=setTimeout(refreshFilters,250);});
$("topicFilter").addEventListener("change",()=>{syncPills();refreshFilters();});
$("showSystem").addEventListener("change",()=>{showSystem=$("showSystem").checked;try{localStorage.setItem("atelier.board.notices",showSystem?"shown":"hidden");}catch{}feedSignature="";renderFeed();});

/* Composer */
function renderRecipients() {
  const available=liveAgents(), signature=JSON.stringify(available.map(a=>[a.agent,a.listening,a.delivery_error]));
  if(signature===recipientSignature)return;recipientSignature=signature;
  const selected=$("recipient").value!=="*"?$("recipient").value:draftRecipient;
  $("recipient").replaceChildren(new Option(`Everyone (${available.length})`,"*"));
  for(const a of available)$("recipient").add(new Option(a.agent+(!a.listening?" · offline":a.delivery_error?" · retrying":""),a.agent));
  if(selected!=="*"&&!available.some(a=>a.agent===selected)){const option=new Option(selected+" · retired",selected);option.disabled=true;$("recipient").add(option);}
  $("recipient").value=selected;
}
let previewTimer;
function draftChanged() { if($("message").value!==draftBody || $("broadcastTopic").value!==draftTopic || $("recipient").value!==draftRecipient)draftKey=null;draftRecipient=$("recipient").value;persistDraft();formState();if(!$("messagePreview").hidden){clearTimeout(previewTimer);previewTimer=setTimeout(preview,250);} }
function grow() { const box=$("message"); box.style.height="auto"; box.style.height=`${box.scrollHeight}px`; }
function syncPills() { document.querySelectorAll(".select-pill").forEach(pill=>{const option=pill.querySelector("select").selectedOptions[0];pill.querySelector(".pill-value").textContent=option?option.textContent.replace(/ · .*/,""):"";}); }
function formState() {
  syncPills();
  const target=$("recipient").value, count=liveAgents().length, length=$("message").value.length;
  const ready=uploads.filter(u=>u.status==="done").length, busy=uploads.some(u=>u.status!=="done");
  $("characterCount").textContent=length>6000?`${length.toLocaleString()} / 8,000`:"";
  $("sendButton").setAttribute("aria-label",busy?"Waiting for uploads":target==="*"?`Send to all ${count} agents`:`Send to ${target}`);
  $("sendButton").disabled=sending||busy||!state||!count||!($("message").value.trim()||ready)||(target!=="*"&&!state.agents.some(a=>a.agent===target&&!a.stop));
  $("broadcastForm").classList.toggle("has-text",Boolean(length));
  const form=$("broadcastForm"), focused=form.contains(document.activeElement);
  form.classList.toggle("expanded",Boolean(length||uploads.length||focused||thread||!$("messagePreview").hidden));
  $("message").placeholder=thread?"Reply in thread…":target==="*"?"Message everyone…":`Message ${target}…`;
}
$("message").addEventListener("input",()=>{grow();draftChanged();}); $("broadcastTopic").addEventListener("change",draftChanged);$("recipient").addEventListener("change",draftChanged);
async function preview() {
  if(!state)return;const number=++previewRequest, abort=new AbortController(), timer=setTimeout(()=>abort.abort(),5000);
  try {const response=await fetch("/api/preview",{method:"POST",headers:{"Content-Type":"application/json","X-Board-CSRF":state.csrf},body:JSON.stringify({body:$("message").value}),signal:abort.signal});const result=await response.json();if(!response.ok)throw Error();if(number===previewRequest)markdown($("messagePreview"),result.html);}
  catch {if(number===previewRequest)$("messagePreview").textContent="Preview unavailable. Your draft is saved.";}
  finally {clearTimeout(timer);}
}
$("previewButton").addEventListener("click",()=>{const show=$("messagePreview").hidden;$("messagePreview").hidden=!show;$("previewButton").textContent=show?"Edit":"Preview";$("previewButton").setAttribute("aria-expanded",String(show));if(show)preview();});
$("message").addEventListener("keydown",event=>{
  if(event.key!=="Enter"||event.isComposing)return;
  const send=event.metaKey||event.ctrlKey||(!touch.matches&&!event.shiftKey&&!event.altKey);
  if(send&&!$("sendButton").disabled){event.preventDefault();$("broadcastForm").requestSubmit();}
});
// Keep the keyboard up when tapping send, so the button doesn't move under the finger.
$("sendButton").addEventListener("pointerdown",event=>{if(document.activeElement===$("message"))event.preventDefault();});
let blurTimer, composerTimer;
$("broadcastForm").addEventListener("focusin",()=>{clearTimeout(composerTimer);formState();});
$("broadcastForm").addEventListener("focusout",()=>{composerTimer=setTimeout(formState,180);});
$("message").addEventListener("focus",()=>{clearTimeout(blurTimer);if(touch.matches)$("app").classList.add("typing");if(stickToBottom)setTimeout(scrollToLatest,250);});
$("message").addEventListener("blur",()=>{blurTimer=setTimeout(()=>$("app").classList.remove("typing"),120);});
function composerStatus(text, error=false) {
  clearTimeout(statusTimer);$("composerStatus").textContent=text;$("composerStatus").className="composer-status"+(error?" error":"");
  if(text&&!error)statusTimer=setTimeout(()=>composerStatus(""),4000);
}

/* Attachments: files upload as soon as they are picked; the message only refers to them. */
$("attachButton").addEventListener("click",()=>$("fileInput").click());
$("fileInput").addEventListener("change",()=>{addFiles($("fileInput").files);$("fileInput").value="";});
$("message").addEventListener("paste",event=>{const files=[...(event.clipboardData?.files||[])];if(files.length){event.preventDefault();addFiles(files);}});
let dragDepth=0;
addEventListener("dragenter",event=>{if([...(event.dataTransfer?.types||[])].includes("Files")){dragDepth++;$("dropHint").hidden=false;}});
addEventListener("dragleave",()=>{if(--dragDepth<=0){dragDepth=0;$("dropHint").hidden=true;}});
addEventListener("dragover",event=>{if([...(event.dataTransfer?.types||[])].includes("Files"))event.preventDefault();});
addEventListener("drop",event=>{if(!event.dataTransfer?.files?.length)return;event.preventDefault();dragDepth=0;$("dropHint").hidden=true;setView("messages");addFiles(event.dataTransfer.files);});
function addFiles(list) {
  for(const file of [...list]) {
    if(uploads.length>=10){composerStatus("You can attach up to 10 files to one message.",true);break;}
    if(file.size>512*1048576){composerStatus(`${file.name} is larger than 512 MB.`,true);continue;}
    const item={key:crypto.randomUUID(),file,name:file.name||"file",mime:file.type||"application/octet-stream",size:file.size,status:"uploading",progress:0,preview:URL.createObjectURL(file)};
    uploads.push(item);upload(item);
  }
  draftKey=null;renderTray();formState();
}
// A photo's or video's pixel size, so the feed can reserve its space before it loads. Unknown (null) is fine.
async function mediaSize(file) {
  const kind=kindOf(file.type||"");
  try {
    if(kind==="image"&&window.createImageBitmap){const bitmap=await createImageBitmap(file);const size=[bitmap.width,bitmap.height];bitmap.close?.();return size;}
    if(kind==="video")return await new Promise(resolve=>{const v=document.createElement("video");const url=URL.createObjectURL(file);
      const done=size=>{URL.revokeObjectURL(url);resolve(size);};v.preload="metadata";v.muted=true;
      v.onloadedmetadata=()=>done([v.videoWidth,v.videoHeight]);v.onerror=()=>done(null);setTimeout(()=>done(null),3000);v.src=url;});
  } catch {}
  return null;
}
async function upload(item) {
  item.status="uploading";item.progress=0;renderTray();
  if(item.size2===undefined&&item.file)item.size2=await mediaSize(item.file);
  const xhr=new XMLHttpRequest();item.xhr=xhr;
  xhr.open("POST","/api/upload");xhr.setRequestHeader("Content-Type",item.mime);xhr.setRequestHeader("X-Board-CSRF",state?.csrf||"");xhr.setRequestHeader("X-File-Name",encodeURIComponent(item.name));
  if(item.size2?.[0]&&item.size2?.[1]){xhr.setRequestHeader("X-Media-Width",String(item.size2[0]));xhr.setRequestHeader("X-Media-Height",String(item.size2[1]));}
  xhr.upload.onprogress=event=>{if(event.lengthComputable){item.progress=Math.round(event.loaded/event.total*100);item.tile?.style.setProperty("--p",item.progress);}};
  xhr.onload=()=>{let result={};try{result=JSON.parse(xhr.responseText);}catch{}
    if(xhr.status===200&&result.id){Object.assign(item,{id:result.id,name:result.name,status:"done",progress:100});}
    else {item.status="error";composerStatus(result.error||`${item.name} could not be uploaded. Tap it to retry.`,true);}
    persistDraft();renderTray();formState();};
  xhr.onerror=()=>{item.status="error";renderTray();formState();composerStatus(`${item.name} could not be uploaded. Tap it to retry.`,true);};
  xhr.send(item.file);
}
function removeUpload(item) { item.xhr?.abort();if(item.preview?.startsWith("blob:"))URL.revokeObjectURL(item.preview);uploads=uploads.filter(u=>u!==item);draftKey=null;persistDraft();renderTray();formState(); }
function renderTray() {
  const tray=$("tray");tray.hidden=!uploads.length;
  const existing=new Map([...tray.children].map(tile=>[tile.dataset.key,tile]));
  for(const item of uploads) {
    let tile=existing.get(item.key);existing.delete(item.key);
    if(!tile) {
      const kind=kindOf(item.mime);tile=node("div","tile "+kind);tile.dataset.key=item.key;item.tile=tile;
      if(kind==="image"){const img=node("img");img.src=item.preview;img.alt=item.name;tile.append(img);}
      else if(kind==="video"){const video=node("video");video.src=item.preview+"#t=0.1";video.muted=true;video.playsInline=true;video.preload="metadata";tile.append(video,node("span","tile-kind","▶ Video"));}
      else {tile.classList.add("file");tile.append(icon("file"),node("span","tile-name",item.name));}
      const progress=node("div","tile-progress");const retry=node("button","tile-retry","Retry");retry.type="button";retry.addEventListener("click",()=>upload(item));progress.append(retry);
      const remove=node("button","tile-remove");remove.type="button";remove.setAttribute("aria-label",`Remove ${item.name}`);remove.append(icon("close"));remove.addEventListener("click",()=>removeUpload(item));
      tile.append(progress,remove);tray.append(tile);
    }
    tile.classList.toggle("error",item.status==="error");tile.querySelector(".tile-progress").hidden=item.status==="done";
    tile.querySelector(".tile-retry").hidden=item.status!=="error";tile.style.setProperty("--p",item.progress);tile.title=`${item.name} · ${sizeText(item.size)}`;
  }
  for(const tile of existing.values())tile.remove();
}
function attachmentNodes(files, many) {
  const wrap=node("div","attachments"), images=files.filter(f=>!f.missing&&kindOf(f.mime)==="image");
  for(const f of files) {
    if(f.missing){wrap.append(node("p","att-missing",`${f.name} is no longer available`));continue;}
    const kind=kindOf(f.mime);
    const ratio=f.width&&f.height?`${f.width} / ${f.height}`:null;
    if(kind==="image"){const b=node("button","att-image"+(images.length===1?" single":""));b.type="button";if(ratio)b.style.setProperty("--ratio",ratio);
      const img=node("img");img.src=f.url;img.alt=f.name;img.loading="lazy";if(f.width){img.width=f.width;img.height=f.height;}b.append(img);b.addEventListener("click",()=>openLightbox(f));wrap.append(b);}
    else if(kind==="video"){const v=node("video","att-video");if(ratio)v.style.setProperty("--ratio",ratio);v.src=f.url;v.controls=true;v.playsInline=true;v.preload="metadata";wrap.append(v);}
    else if(kind==="audio"){const a=node("audio","att-audio");a.src=f.url;a.controls=true;a.preload="none";wrap.append(a);}
    else {const a=node("a","att-file");a.href=f.url;a.target="_blank";a.rel="noopener noreferrer";const text=node("span");text.append(node("b","",f.name),node("small","",`${sizeText(f.size)} · ${(f.name.split(".").pop()||"file").toUpperCase()}`));a.append(icon("file"),text);wrap.append(a);}
  }
  return wrap;
}
function openLightbox(f) { $("lightboxImage").src=f.url;$("lightboxImage").alt=f.name;$("lightboxName").textContent=f.name;$("lightboxOpen").href=f.url;$("lightbox").hidden=false;$("lightboxClose").focus(); }
function closeLightbox() { $("lightbox").hidden=true;$("lightboxImage").removeAttribute("src"); }
$("lightbox").addEventListener("click",event=>{if(event.target!==$("lightboxOpen"))closeLightbox();});
addEventListener("keydown",event=>{if(event.key==="Escape"){if(!$("lightbox").hidden)closeLightbox();else if(thread)navBack();}});

/* Agents: the list pane and the orb row share one render. */
let seen={};
try { seen=JSON.parse(localStorage.getItem("atelier.board.seen")||"{}")||{}; } catch {}
function saveSeen() { try { localStorage.setItem("atelier.board.seen",JSON.stringify(seen)); } catch {} }
function unreadFrom(agent) { return (agent.last_to_me||0)>(seen[agent.agent]??Infinity); }
// What has been read: a first visit starts with nothing unread; a conversation (or the whole feed) read to its end
// marks its agents' newest direct messages seen.
function markRead(names) {
  let changed=false;
  for(const a of state.agents){
    if(seen[a.agent]===undefined||names===true||names.includes(a.agent)){
      if((seen[a.agent]??-1)<(a.last_to_me||0)){seen[a.agent]=a.last_to_me||0;changed=true;}
    }
  }
  if(changed){saveSeen();agentsSignature="";}
}
function renderAgents() {
  markRead([]);
  const agents=state.agents, signature=JSON.stringify([selectedAgent,agents.map(a=>[a.agent,a.listening,a.stop,a.pending,a.supervised,a.delivery_error,a.checkout,unreadFrom(a)])]);
  if(signature===agentsSignature)return; agentsSignature=signature;
  const live=liveAgents(), listening=live.filter(a=>a.listening).length, errors=live.filter(a=>a.delivery_error).length;
  $("agentsSummary").textContent=`${listening} of ${live.length} listening${errors?` · ${errors} retrying delivery`:""}`;
  $("agentsBadge").hidden=!errors;$("agentsBadge").textContent=errors;
  const list=$("agents"), orbs=$("agentChips");list.replaceChildren();orbs.replaceChildren();
  let index=0;
  function row(name, agent) {
    const chosen=selectedAgent===name;
    const b=node("button","agent-row"+(agent?.stop?" retired":""));b.type="button";b.setAttribute("role","listitem");if(chosen)b.setAttribute("aria-current","true");
    b.style.setProperty("--i",index++);
    const text=node("span","agent-text"), detail=node("span","agent-detail");text.append(node("span","agent-name",name||"Everyone"));if(agent&&unreadFrom(agent))b.classList.add("unread");
    if(agent){detail.append(node("span","state "+statusOf(agent),agentStatus(agent)));for(const part of [agent.supervised&&!agent.stop?"auto-recovery":"",agent.checkout||""].filter(Boolean))detail.append(document.createTextNode(" · "+part));}
    else detail.textContent=`Broadcasts and every conversation`;
    text.append(detail);b.append(orb(name||"*",agent),text);
    if(agent?.pending)b.append(node("span","count",`${agent.pending} queued`));
    b.append(icon("right"));b.addEventListener("click",()=>openAgent(name));list.append(b);
    if(agent?.stop)return;
    const o=node("button","orb-button");o.type="button";if(chosen)o.setAttribute("aria-current","true");
    // The orb marks new direct messages from the agent; what is still queued for it lives in the Agents list.
    const face=orb(name||"*",agent);if(agent&&unreadFrom(agent))face.append(node("span","unread-dot"));
    o.append(face,node("span","orb-name",name||"Everyone"));
    o.title=agent?`${name} · ${agentStatus(agent)}`:"All conversations";o.setAttribute("aria-label",o.title);
    o.addEventListener("click",()=>openAgent(name));orbs.append(o);
  }
  row("");
  for(const agent of [...agents].sort((a,b)=>a.stop-b.stop||b.listening-a.listening||a.agent.localeCompare(b.agent)))row(agent.agent,agent);
  const current=orbs.querySelector('[aria-current="true"]');
  if(current&&(current.offsetLeft<orbs.scrollLeft||current.offsetLeft+current.offsetWidth>orbs.scrollLeft+orbs.clientWidth))orbs.scrollLeft=current.offsetLeft-14;
}
function renderHeader() {
  const agent=state?.agents.find(a=>a.agent===selectedAgent), live=liveAgents(), listening=live.filter(a=>a.listening).length;
  $("chatTitle").textContent=selectedAgent||"Everyone";
  $("backButton").hidden=!selectedAgent;$("app").classList.toggle("in-conversation",Boolean(selectedAgent));
  $("modeSwitch").hidden=!selectedAgent;
  document.querySelectorAll("#modeSwitch button").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.mode===conversationMode)));
  const subtitle=$("chatSubtitle"), dot=node("span","dot");
  let text;
  if(failed){dot.classList.add("error");text="Reconnecting…";}
  else if(!state){text="Connecting…";}
  else if(agent){dot.classList.add(statusOf(agent));text=agentStatus(agent)+(agent.pending?` · ${agent.pending} queued`:"");}
  else {dot.classList.add(listening?"live":"idle");text=`${listening} of ${live.length} agents listening`;}
  subtitle.replaceChildren(dot,node("span","",text));
}

/* Feed: oldest at the top, newest by the composer, like a chat. */
function feedNearBottom() { const f=$("feed"); return f.scrollHeight-f.scrollTop-f.clientHeight<96; }
function scrollToLatest(smooth=false) { $("app").classList.remove("reading"); const f=$("feed"); f.scrollTo({top:f.scrollHeight,behavior:smooth?"smooth":"auto"}); stickToBottom=true; markSeen(); }
function markSeen() {
  if($("app").dataset.view!=="messages"&&!desktop.matches)return;
  if(feedNearBottom()||stickToBottom){lastSeenId=Math.max(lastSeenId,newestShown);$("jumpLatest").hidden=true;updateBadges();}
}
function updateBadges(unread=0) {
  const away=$("app").dataset.view!=="messages"&&!desktop.matches;
  $("messagesBadge").hidden=!(away&&unread);$("messagesBadge").textContent=unread>99?"99+":unread;
  $("jumpLabel").textContent=unread?`${unread} new`:"Latest";
}
// Our own re-renders and filter switches move the scroll position too; those are not the reader scrolling, so they
// must not unpin the feed or pull in older history (which used to leave a new conversation stuck at its top).
let settleUntil=0;
function settle(ms=500) { settleUntil=performance.now()+ms; }
$("feed").addEventListener("scroll",()=>{
  if(performance.now()<settleUntil){if(stickToBottom)$("feed").scrollTop=$("feed").scrollHeight;return;}
  stickToBottom=feedNearBottom();
  const f=$("feed"), gap=f.scrollHeight-f.scrollTop-f.clientHeight, app=$("app");
  if(gap>320)app.classList.add("reading");else if(gap<60)app.classList.remove("reading");
  if(stickToBottom)markSeen();else $("jumpLatest").hidden=false;
  if($("feed").scrollTop<120&&!historyComplete&&records.size&&!loading)loadOlder();
},{passive:true});
$("jumpLatest").addEventListener("click",()=>scrollToLatest(true));
// Opening search, a growing draft or the keyboard shrinks the feed: stay pinned to the latest message.
const pin=new ResizeObserver(()=>{$("app").style.setProperty("--dock-h",`${$("broadcastForm").offsetHeight}px`);if(stickToBottom)$("feed").scrollTop=$("feed").scrollHeight;if(thread?.stick)$("threadFeed").scrollTop=$("threadFeed").scrollHeight;});
pin.observe($("feed"));pin.observe($("broadcastForm"));pin.observe($("messages"));
// The floating agent row's height is the feed's fixed top inset (0 where the row is not shown, e.g. wide screens).
new ResizeObserver(()=>$("app").style.setProperty("--orbs-h",`${$("agentChips").offsetHeight}px`)).observe($("agentChips"));
function loadOlder() { if(loading||!records.size)return; prepending=true; load(false,Math.min(...records.keys())); }
$("loadOlder").addEventListener("click",loadOlder);
function groupsFrom(messages) {
  const groups=new Map(), loops=new Map();
  for(const m of [...messages].sort((a,b)=>a.id-b.id)) {
    const broadcast=(m.dedup||"").match(/^web-broadcast:([a-f0-9-]+):/);
    let key=broadcast?broadcast[1]:String(m.id), merged=false;
    // The same text sent to several agents one by one (a loop of direct posts) reads as one message to them all.
    if(!broadcast&&m.recipient!=="*"&&!isSystem(m)) {
      const same=`${m.sender}\u0000${m.topic}\u0000${m.reply_to||""}\u0000${m.body}`, open=loops.get(same);
      if(open&&m.created-open.created<15&&!open.recipients.has(m.recipient)){key=open.key;merged=true;open.recipients.add(m.recipient);}
      else loops.set(same,{key,created:m.created,recipients:new Set([m.recipient])});
    }
    if(!groups.has(key))groups.set(key,{key,broadcast:Boolean(broadcast),messages:[]});
    const group=groups.get(key);group.messages.push(m);
    if(merged){group.broadcast=true;group.merged=true;}
  }
  for(const g of groups.values()){g.messages.sort((a,b)=>a.id-b.id);g.first=g.messages[0];}
  return [...groups.values()].sort((a,b)=>a.first.id-b.first.id);
}
function receipt(group, agents) {
  const wrap=node("details","receipt");wrap.open=deliveryOpen.has(group.key);
  wrap.addEventListener("toggle",()=>{wrap.open?deliveryOpen.add(group.key):deliveryOpen.delete(group.key);});
  const summary=node("summary");
  const picked=group.messages.filter(item=>(agents.get(item.recipient)?.cursor||0)>=item.id), acked=group.messages.filter(item=>item.acknowledged);
  const retrying=group.messages.some(item=>!((agents.get(item.recipient)?.cursor||0)>=item.id)&&agents.get(item.recipient)?.delivery_error);
  let text, done=false;
  if(group.broadcast){done=acked.length===group.messages.length;text=`Delivered ${picked.length}/${group.messages.length} · ${acked.length} acknowledged`;}
  else if(group.first.recipient==="*"){summary.append(icon("check"),node("span","","Posted to the board"));wrap.append(summary);return wrap;}
  else {done=acked.length>0;text=done?"Acknowledged":picked.length?"Delivered · awaiting ack":retrying?"Retrying delivery":"Queued";}
  summary.className=done?"done":retrying?"warn":"";summary.append(icon("check"),node("span","",text));wrap.append(summary);
  const list=node("div","receipt-list");
  for(const item of group.messages) {
    const agent=agents.get(item.recipient), got=(agent?.cursor||0)>=item.id, row=node("div","receipt-row");
    const status=item.acknowledged?"Acknowledged":got?"Delivered":agent?.delivery_error?"Retrying":"Queued";
    row.append(node("span","",item.recipient),node("span","receipt-state "+status.toLowerCase(),status));list.append(row);
  }
  wrap.append(list);return wrap;
}
/* Threads: a reply whose original is on the board folds under it, Slack style. */
function threadIndex(groups) {
  const groupOf=new Map(), replies=new Map();
  for(const g of groups)for(const m of g.messages)groupOf.set(m.id,g);
  function rootOf(g) {
    let current=g, seen=new Set();
    while(current.first.reply_to&&groupOf.has(current.first.reply_to)&&!seen.has(current.key)){seen.add(current.key);current=groupOf.get(current.first.reply_to);}
    return current;
  }
  for(const g of groups) {
    if(!g.first.reply_to||!groupOf.has(g.first.reply_to)||isSystem(g.first))continue;
    const root=rootOf(g);if(root===g)continue;
    if(!replies.has(root.key))replies.set(root.key,[]);replies.get(root.key).push(g);g.threaded=true;
  }
  return replies;
}
function threadBar(root, replies, open) {
  const bar=node("button","thread-bar");bar.type="button";
  const faces=node("span","thread-faces");
  for(const sender of [...new Set(replies.map(r=>r.first.sender))].slice(0,3))faces.append(orb(sender===state.sender?"*":sender));
  const last=replies.at(-1).first;
  bar.append(faces,node("span","thread-count",`${replies.length} ${replies.length===1?"reply":"replies"}`),node("span","thread-last",`Last ${clock(last.created)}`),icon("right"));
  bar.addEventListener("click",open);return bar;
}
function messageNode(group, ctx) {
  const m=group.first, agents=ctx.agents, mine=m.sender===state.sender;
  const article=node("article","message"+(mine?" mine":"")+(ctx.continued?" continued":"")+(m.topic==="alert"||m.topic==="blocked"?" urgent":"")+(ctx.enter?" enter":""));
  article.dataset.ids=group.messages.map(item=>item.id).join(" ");
  if(!mine)article.append(ctx.continued?node("span","orb-space"):whoButton(m.sender,"orb-link",orb(m.sender)));
  const column=node("div","message-column"), bubble=node("div","card bubble");
  if(!ctx.continued) {
    const meta=node("div","meta");
    meta.append(mine||isSystem(m)?node("span","sender",mine?"You":m.sender):whoButton(m.sender,"sender who",document.createTextNode(m.sender)));
    const to=group.broadcast||m.recipient==="*"?"everyone":m.recipient===state.sender?"you":m.recipient;
    const people=group.messages.map(x=>x.recipient===state.sender?"you":x.recipient);
    meta.append(node("span","route",group.merged?`to ${people.length>3?`${people.length} agents`:people.join(", ")}`
      :`to ${to==="everyone"&&group.broadcast?`everyone (${group.messages.length})`:to}`));
    if(m.topic!=="info")meta.append(node("span","topic "+m.topic,names[m.topic]||m.topic));
    const time=node("time","time",clock(m.created));time.dateTime=new Date(m.created*1000).toISOString();time.title=`${new Date(m.created*1000).toLocaleString()} · #${m.id}`;meta.append(time);
    if(!ctx.inThread&&!ctx.replies?.length)meta.append(replyButton(m));
    bubble.append(meta);
  }
  if(m.reply_to&&!ctx.inThread) {
    // The original is not loaded here: show what it was and open the whole thread.
    const original=records.get(m.reply_to), quote=node("button","quote"+(original?"":" quote-away"));quote.type="button";
    if(original){quote.append(node("span","quote-who",original.sender===state.sender?"You":original.sender),node("span","quote-text",snippet(original.body)));}
    else quote.append(icon("reply"),node("span","","In reply to an earlier message · open thread"));
    quote.addEventListener("click",()=>openThread(m.id));bubble.append(quote);
  }
  const hasText=Boolean(m.body_html&&m.body_html.trim());
  if(hasText) {
    // Long messages start folded to about six lines; "Read more" opens them in place.
    const text=snippetless(m.body), long=text.length>280||text.split("\n").length>5, collapsed=long&&!expanded.has(group.key);
    const body=node("div","body"+(collapsed?" collapsed":""));markdown(body,m.body_html,m.body);bubble.append(body);
    if(long){const more=node("button","more",collapsed?"Read more":"Show less");more.type="button";more.addEventListener("click",()=>{collapsed?expanded.add(group.key):expanded.delete(group.key);ctx.inThread?renderThread(true):(feedSignature="",renderFeed());});bubble.append(more);}
  }
  if(m.attachments?.length)bubble.append(attachmentNodes(m.attachments));
  if(ctx.continued){const line=node("div","bubble-time"), time=node("time","",clock(m.created));time.title=`#${m.id}`;line.append(time);if(!ctx.inThread&&!ctx.replies?.length)line.append(replyButton(m));bubble.append(line);}
  if(!ctx.inThread&&!isSystem(m)){
    bubble.classList.add("tappable");
    bubble.addEventListener("click",event=>{
      if(event.target.closest("a,button,video,audio,summary,details,input,select,textarea"))return;
      if(String(window.getSelection?.()||""))return;
      openThread(m.id,!ctx.replies?.length);
    });
  }
  column.append(bubble);
  if(mine)column.append(receipt(group,agents));
  if(ctx.replies?.length)column.append(threadBar(group,ctx.replies,()=>openThread(m.id)));
  article.append(column);return article;
}
// Tapping an agent's name or face opens your direct conversation with them.
function whoButton(name, cls, content) {
  const b=node("button",cls);b.type="button";b.title=`Message ${name} directly`;b.setAttribute("aria-label",`Open your direct messages with ${name}`);
  b.append(content);b.addEventListener("click",event=>{event.stopPropagation();openAgent(name);});return b;
}
function replyButton(m) {
  const b=node("button","reply-button");b.type="button";b.setAttribute("aria-label","Reply in thread");b.title="Reply in thread";b.append(icon("reply"));
  b.addEventListener("click",event=>{event.stopPropagation();openThread(m.id,true);});return b;
}
function continues(previous, group) {
  const m=group.first;
  return previous&&previous.sender===m.sender&&previous.recipient===m.recipient&&previous.topic===m.topic&&m.created-previous.created<300&&!group.broadcast&&!previous.broadcast;
}
const feedNodes=new Map();
// Put `nodes` in `parent` in order, touching only what changed: existing nodes in the right place are left alone.
function reconcile(parent, nodes) {
  let cursor=parent.firstChild;
  for(const n of nodes){ if(n===cursor){cursor=cursor.nextSibling;continue;} parent.insertBefore(n,cursor); }
  while(cursor){const next=cursor.nextSibling;cursor.remove();cursor=next;}
}
function noticeNode(list, enter) {
  const last=list.at(-1), sections=new Set();
  for(const m of list)((m.body.match(/changed \(([^)]*)\)/)||[])[1]||"").split(/,\s*/).filter(Boolean).forEach(x=>sections.add(x));
  const what=/render scheduling board changed/i.test(last.body)?`Render schedule updated${sections.size?` · ${[...sections].join(", ")}`:""}`:`${last.sender}: ${last.body.slice(0,80)}`;
  const line=node("details","notice"+(enter?" enter":""));line.dataset.ids=list.map(m=>m.id).join(" ");
  const summary=node("summary"), when=node("time","",clock(last.created));
  summary.append(icon("board"),node("span","notice-text",`${what}${list.length>1?` · ${list.length}×`:""}`),when);
  line.append(summary,node("p","",last.body));return line;
}
function renderFeed() {
  const agents=new Map(state.agents.map(a=>[a.agent,a]));
  const signature=JSON.stringify([[...records.keys()],state.agents.map(a=>[a.agent,a.cursor,a.delivery_error]),[...records.values()].map(m=>m.acknowledged),[...expanded],[...deliveryOpen],showSystem,historyComplete]);
  if(signature===feedSignature)return; feedSignature=signature;
  const feed=$("feed"), top=feed.scrollTop, fromBottom=feed.scrollHeight-feed.scrollTop, stick=stickToBottom;
  const groups=groupsFrom([...records.values()]), threads=threadIndex(groups);
  const visible=groups.filter(g=>(showSystem||!isSystem(g.first))&&!g.threaded);
  // Only messages that arrive after the first paint animate in; history and filter changes appear at rest.
  const animateAbove=feedPainted?newestShown:Infinity;
  // Items first, then nodes: an unchanged item keeps its node, so photos and videos never reload or pause and nothing
  // above the newest message moves when it arrives.
  const items=[];
  let day="", previous=null, run=null;
  const filtered=Boolean(selectedAgent||$("search").value.trim()||$("topicFilter").value);
  if(!visible.length)items.push({key:`empty:${selectedAgent}:${conversationMode}:${filtered}`,sig:"",build:()=>{
    const empty=node("div","empty");empty.append(icon("messages"),node("h2","",filtered?"No matching messages":"A quiet board, for now"),
      node("p","",selectedAgent?(conversationMode==="dm"?`Nothing between you and ${selectedAgent} yet. Say hello below.`:`Say hello to ${selectedAgent} below.`):filtered?"Try a different search or topic.":"Send a message to start the conversation."));return empty;}});
  for(const group of visible) {
    const m=group.first, label=dayLabel(m.created), enter=m.id>animateAbove;
    if(label!==day){day=label;previous=null;run=null;items.push({key:`d:${label}`,sig:"",build:()=>{const sep=node("div","day"+(enter?" enter":""));sep.append(node("span","",label));return sep;}});}
    if(isSystem(m)) {
      // Consecutive automatic notices collapse into one quiet line.
      if(run){run.list.push(m);continue;}
      run={list:[m],enter};items.push({notices:run});previous=null;continue;
    }
    run=null;
    const replies=threads.get(group.key), continued=continues(previous,group)&&!threads.get(previous.key)?.length, mine=m.sender===state.sender;
    const sig=JSON.stringify([group.messages.map(x=>[x.id,x.acknowledged,mine?[(agents.get(x.recipient)?.cursor||0)>=x.id,Boolean(agents.get(x.recipient)?.delivery_error)]:0]),
      continued,(replies||[]).map(r=>r.first.id),expanded.has(group.key),deliveryOpen.has(group.key),m.reply_to?records.has(m.reply_to):0]);
    items.push({key:`m:${group.key}`,sig,build:()=>messageNode(group,{agents,continued,enter,replies})});
    previous={key:group.key,sender:m.sender,recipient:m.recipient,topic:m.topic,created:m.created,broadcast:group.broadcast};
  }
  const wanted=items.map(item=>{
    if(item.notices){
      const list=item.notices.list, first=list[0];
      return {key:`n:${first.id}`,sig:list.map(x=>x.id).join(","),build:()=>noticeNode(list,item.notices.enter)};
    }
    return item;
  });
  const used=new Set(), nodes=wanted.map(item=>{
    used.add(item.key);
    const cached=feedNodes.get(item.key);
    if(cached&&cached.sig===item.sig)return cached.node;
    const built=item.build();feedNodes.set(item.key,{sig:item.sig,node:built});return built;
  });
  for(const key of [...feedNodes.keys()])if(!used.has(key))feedNodes.delete(key);
  settle();reconcile($("messages"),nodes);feedPainted=true;
  $("loadOlder").hidden=historyComplete||!records.size;
  const newest=records.size?Math.max(...records.keys()):0;
  const unread=groups.filter(g=>!isSystem(g.first)&&g.first.id>lastSeenId&&g.first.sender!==state.sender).length;
  newestShown=newest;
  if(prepending){feed.scrollTop=feed.scrollHeight-fromBottom;prepending=false;}
  else if(stick){feed.scrollTop=feed.scrollHeight;}
  else {feed.scrollTop=top;}
  const viewing=$("app").dataset.view==="messages"||desktop.matches;
  if(!lastSeenId||(stick&&viewing))lastSeenId=newest;
  if(stick&&viewing&&!document.hidden)markRead(selectedAgent?[selectedAgent]:true);
  $("jumpLatest").hidden=feedNearBottom();
  updateBadges(stick&&viewing?0:unread);
}

/* Navigation, as in a native iOS app. A conversation or a thread pushes in from the right over the screen it came
   from, which drifts a third of the way left under a dim. The back button, a swipe right from anywhere on the screen
   and the browser's own back all pop it. A swipe follows the finger and is released onto a spring that keeps the
   flick's speed, so a quick flick finishes fast and a slow drag that stops short settles back. */
const motion=matchMedia("(prefers-reduced-motion: reduce)");
const standalone=matchMedia("(display-mode: standalone)").matches||navigator.standalone===true;
document.documentElement.classList.toggle("standalone",standalone);
const PARALLAX=.3, DIM=.24, springs=CSS.supports?.("animation-timing-function","linear(0, 1)");
let nav=[], moving=null, backEntry=false, ignorePops=0, historyTimer=0;
// A critically damped spring, sampled into a CSS linear() easing so the compositor runs it. Its starting velocity is
// in fractions of the remaining distance per second, and it never overshoots: a screen can't bounce past the edge.
function spring(velocity=0) {
  if(!springs)return {easing:"cubic-bezier(.32, .72, 0, 1)",duration:500};
  const w=2*Math.PI/.42, at=t=>Math.min(1,1+(-1+(velocity-w)*t)*Math.exp(-w*t));
  let end=1/60;while(end<1&&at(end)<.999)end+=1/120;
  const points=[];for(let i=0;i<=40;i++)points.push(i===40?1:+at(end*i/40).toFixed(4));
  return {easing:`linear(${points.join(", ")})`,duration:Math.round(end*1000)};
}
// What moves: the pushed screen on top, what it covers underneath, and the dim between them.
function scene(entry) {
  const s=entry.kind==="thread"?{entry,top:$("threadView"),under:[$("topbar"),$("feed"),$("errorBanner")],scrim:$("threadScrim")}:{entry,top:$("chatPane"),under:[entry.underlay],scrim:$("navScrim")};
  s.width=s.top.offsetWidth;return s;
}
// p is how far the top screen has gone: 0 covers everything, 1 is off to the right.
const frame=(s,p)=>({top:{transform:`translate3d(${p*s.width}px,0,0)`},under:{transform:`translate3d(${-(1-p)*PARALLAX*s.width}px,0,0)`},scrim:{opacity:(1-p)*DIM}});
function paint(s,p) { const f=frame(s,p); s.top.style.transform=f.top.transform; for(const n of s.under)n.style.transform=f.under.transform; s.scrim.style.opacity=f.scrim.opacity; }
function begin(s) { $("app").classList.add("navigating");s.top.classList.add("nav-top");s.scrim.hidden=false; }
function end(s) {
  $("app").classList.remove("navigating");s.top.classList.remove("nav-top");s.scrim.hidden=true;
  for(const n of [s.top,...s.under,s.scrim])n.style.transform=n.style.opacity="";
}
function glide(s,from,to,velocity=0) {
  const {easing,duration}=motion.matches?{easing:"linear",duration:1}:spring(velocity), a=frame(s,from), b=frame(s,to);
  paint(s,to);
  const runs=[s.top.animate([a.top,b.top],{duration,easing}),...s.under.map(n=>n.animate([a.under,b.under],{duration,easing})),s.scrim.animate([a.scrim,b.scrim],{duration,easing})];
  moving=Promise.all(runs.map(r=>r.finished.catch(()=>{}))).then(()=>{moving=null;});
  return moving;
}
const waitFor=(ready,ms)=>new Promise(done=>{const start=performance.now();(function check(){if(ready()||performance.now()-start>ms)done();else requestAnimationFrame(check);})();});
// A still copy of the screen a conversation was opened from. It sits underneath while the conversation is open and is
// what a swipe back reveals, so the live pane can switch to the conversation without losing the screen behind it.
function snapshot(pane) {
  const copy=pane.cloneNode(true), selector=".feed, .pane-body, .orbs", scrollers=[...pane.querySelectorAll(selector)], drafts=[...pane.querySelectorAll("textarea")];
  copy.removeAttribute("id");copy.querySelectorAll("[id]").forEach(n=>n.removeAttribute("id"));
  copy.classList.remove("entering");copy.classList.add("nav-underlay");copy.inert=true;copy.setAttribute("aria-hidden","true");
  copy.querySelectorAll("textarea").forEach((n,i)=>{n.value=drafts[i]?.value||"";});
  $("navScrim").before(copy);
  copy.querySelectorAll(selector).forEach((n,i)=>{n.scrollTop=scrollers[i]?.scrollTop||0;n.scrollLeft=scrollers[i]?.scrollLeft||0;});
  return copy;
}
// The browser keeps one history entry while anything is pushed, so the system back (Android, a desktop browser, or
// Safari's own edge swipe in a tab) pops the board instead of leaving it.
function syncHistory() {
  clearTimeout(historyTimer);
  historyTimer=setTimeout(()=>{
    if(nav.length&&!backEntry){history.pushState({board:"pushed"},"");backEntry=true;}
    else if(!nav.length&&backEntry){backEntry=false;ignorePops++;history.back();}
  });
}
addEventListener("popstate",()=>{
  if(ignorePops){ignorePops--;return;}
  if(!backEntry)return;
  backEntry=false;
  // Safari in a tab has already animated its own snapshot of the previous screen; animating again would play it twice.
  navBack({instant:!standalone||desktop.matches});
});
function navPush(entry) { nav.push(entry);syncHistory(); }
// The app closed a screen itself: drop it (and anything above it) from the stack.
function navForget(kind) {
  const index=nav.findLastIndex(e=>e.kind===kind);if(index<0)return;
  for(const e of nav.splice(index))e.underlay?.remove();
  syncHistory();
}
function openAgent(name) {
  if(name===selectedAgent){if(thread)navBack();setView("messages");return;}
  if(!name){const entry=nav.at(-1);if(entry?.kind==="dm"&&entry.from==="messages")navBack();else selectAgent("");return;}
  if(selectedAgent){selectAgent(name);return;}
  pushConversation(name);
}
async function pushConversation(name) {
  if(thread)closeThread();
  const from=$("app").dataset.view, animate=!desktop.matches&&!motion.matches;
  const entry={kind:"dm",from,underlay:animate?snapshot(from==="agents"?$("agentsPane"):$("chatPane")):null};
  navPush(entry);
  selectAgent(name,"dm","messages",!animate);
  if(!animate)return;
  const s=scene(entry);begin(s);paint(s,1);
  // Push once the conversation has painted, as a native app pushes a ready screen, but never keep a tap waiting long.
  await waitFor(()=>feedPainted,260);
  if(nav.at(-1)!==entry){end(s);return;}
  await glide(s,1,0);end(s);
}
// Pop the top screen. A swipe hands over its scene, position and speed; the browser's back asks for no animation.
async function navBack({scene:given=null,from=0,velocity=0,instant=false}={}) {
  const entry=nav.at(-1);if(!entry){if(given)end(given);return;}
  const animate=!instant&&!motion.matches&&(entry.kind==="thread"||!desktop.matches);
  let s=given;
  if(animate){if(!s){if(moving)return;s=scene(entry);begin(s);}await glide(s,from,1,velocity);}
  if(entry.kind==="thread"){closeThread();if(s)end(s);return;}
  const underlay=entry.underlay;entry.underlay=null;
  selectAgent("","dm",entry.from,false);
  // The live pane stays off to the right, behind the still copy, until the full conversation has painted again.
  if(entry.from==="messages"&&s)await waitFor(()=>feedPainted,1200);
  if(s)end(s);underlay?.remove();
}

/* Thread view: the original and every reply, with the composer replying in the thread. */
async function openThread(id, focus=false) {
  const nested=!!thread;
  thread={id,data:null,signature:"",newest:Infinity,stick:true,savedRecipient:nested?thread.savedRecipient:$("recipient").value};
  $("threadView").hidden=false;$("app").classList.add("in-thread");
  $("threadTitle").textContent="Thread";$("threadSubtitle").textContent="Loading…";$("threadFeed").replaceChildren();
  const loaded=loadThread();
  if(!nested){
    const entry={kind:"thread"};navPush(entry);
    if(!motion.matches&&!moving){
      const s=scene(entry);begin(s);paint(s,1);
      await waitFor(()=>thread?.data,220);
      if(thread&&nav.at(-1)===entry){
        await glide(s,1,0);
        // The feed behind is out of sight now, so it can settle on the latest message without anyone seeing it move.
        stickToBottom=true;scrollToLatest();
      }
      end(s);
    }
  }
  await loaded;
  if(focus&&thread)$("message").focus();
}
function closeThread() {
  if(!thread)return;
  const saved=thread.savedRecipient;thread=null;navForget("thread");
  $("threadView").hidden=true;$("app").classList.remove("in-thread");$("replyChip").hidden=true;
  if([...$("recipient").options].some(o=>o.value===saved&&!o.disabled)&&$("recipient").value!==saved){$("recipient").value=saved;draftChanged();}
  formState();
  stickToBottom=true;requestAnimationFrame(()=>scrollToLatest());
}
$("threadBack").addEventListener("click",()=>navBack());$("replyChipClose").addEventListener("click",()=>navBack());
// Swipe back: from the left edge, or (as on iOS 26) a rightward drag anywhere that isn't on something that scrolls
// sideways or takes text. A mostly vertical drag stays a scroll.
let swipe=null;
$("chatPane").addEventListener("touchstart",event=>{
  const entry=nav.at(-1);
  if(event.touches.length!==1||!entry||moving||desktop.matches||(entry.kind==="dm"&&!entry.underlay))return;
  const t=event.touches[0];
  if(t.clientX>24&&event.target.closest("textarea, input, select, pre, table, video, audio, .orbs, .dock, .attachments"))return;
  swipe={entry,x:t.clientX,y:t.clientY,axis:null,samples:[[t.clientX,event.timeStamp]],scene:null};
},{passive:true});
$("chatPane").addEventListener("touchmove",event=>{
  if(!swipe)return;
  const t=event.touches[0], dx=t.clientX-swipe.x, dy=t.clientY-swipe.y;
  if(!swipe.axis){
    if(Math.hypot(dx,dy)<10)return;
    swipe.axis=dx>0&&Math.abs(dx)>Math.abs(dy)*1.2?"x":"y";
    if(swipe.axis==="y"||nav.at(-1)!==swipe.entry||moving){swipe=null;return;}
    swipe.scene=scene(swipe.entry);begin(swipe.scene);
  }
  event.preventDefault();
  swipe.samples.push([t.clientX,event.timeStamp]);if(swipe.samples.length>8)swipe.samples.shift();
  paint(swipe.scene,Math.max(0,Math.min(1,dx/swipe.scene.width)));
},{passive:false});
function endSwipe(event) {
  const s=swipe;swipe=null;if(!s?.scene)return;
  const last=s.samples.at(-1), recent=s.samples.filter(([,at])=>at>=last[1]-100), [x0,t0]=recent[0];
  const speed=last[1]>t0?(last[0]-x0)/(last[1]-t0)*1000:0, p=Math.max(0,Math.min(1,(last[0]-s.x)/s.scene.width));
  const done=event.type==="touchend"&&(speed>350||(speed>-350&&p>.5));
  const remaining=(done?1-p:p)*s.scene.width, velocity=remaining>1?(done?speed:-speed)/remaining:0;
  if(done)navBack({scene:s.scene,from:p,velocity});
  else glide(s.scene,p,0,velocity).then(()=>end(s.scene));
}
$("chatPane").addEventListener("touchend",endSwipe);$("chatPane").addEventListener("touchcancel",endSwipe);
async function loadThread() {
  const current=thread;if(!current)return;
  try {
    const response=await fetch(`/api/thread?id=${current.id}`,{cache:"no-store"});const result=await response.json();
    if(thread!==current)return;
    if(!response.ok){$("threadSubtitle").textContent=result.error||"This conversation could not be loaded.";return;}
    current.data=result;renderThread();
  } catch { if(thread===current)$("threadSubtitle").textContent="Reconnecting…"; }
}
function renderThread(force=false) {
  const current=thread;if(!current?.data||!state)return;
  const signature=JSON.stringify([current.data,state.agents.map(a=>[a.agent,a.cursor]),[...expanded],[...deliveryOpen]]);
  if(signature===current.signature&&!force)return;current.signature=signature;
  const agents=new Map(state.agents.map(a=>[a.agent,a])), feed=$("threadFeed"), stick=current.stick;
  const [root]=groupsFrom(current.data.root), replies=groupsFrom(current.data.replies);
  const people=[...new Set([root,...replies].map(g=>g.first.sender===state.sender?"you":g.first.sender))];
  $("threadSubtitle").textContent=`${replies.length} ${replies.length===1?"reply":"replies"} · ${people.join(", ")}`;
  // Same in-place update as the feed: unchanged messages keep their nodes (and their playing videos).
  const cache=current.nodes||(current.nodes=new Map()), used=new Set();
  const keep=(key,sig,build)=>{used.add(key);const hit=cache.get(key);if(hit&&hit.sig===sig)return hit.node;const n=build();cache.set(key,{sig,node:n});return n;};
  const stateOf=g=>JSON.stringify(g.messages.map(x=>[x.id,x.acknowledged,(agents.get(x.recipient)?.cursor||0)>=x.id]));
  const nodes=[keep(`r:${root.key}`,stateOf(root)+expanded.has(root.key)+deliveryOpen.has(root.key),()=>messageNode(root,{agents,inThread:true}))];
  const label=replies.length?`${replies.length} ${replies.length===1?"reply":"replies"}`:"No replies yet";
  nodes.push(keep("divider",label,()=>{const divider=node("div","thread-divider");divider.append(node("span","",label));return divider;}));
  let previous=null;
  const newest=Math.max(0,...current.data.replies.map(r=>r.id));
  for(const g of replies){
    const continued=continues(previous,g), enter=g.first.id>current.newest;
    nodes.push(keep(`m:${g.key}`,stateOf(g)+continued+expanded.has(g.key)+deliveryOpen.has(g.key),()=>messageNode(g,{agents,inThread:true,continued,enter})));
    previous={key:g.key,sender:g.first.sender,recipient:g.first.recipient,topic:g.first.topic,created:g.first.created,broadcast:g.broadcast};
  }
  for(const key of [...cache.keys()])if(!used.has(key))cache.delete(key);
  current.newest=newest;
  reconcile(feed,nodes);if(stick)feed.scrollTop=feed.scrollHeight;
  // Replies go to the agent who wrote the original, or back to everyone a broadcast reached.
  const m=root.first, target=m.sender===state.sender?(root.broadcast||m.recipient==="*"?"*":m.recipient):m.sender;
  const usable=[...$("recipient").options].some(o=>o.value===target&&!o.disabled);
  if(usable&&$("recipient").value!==target&&!current.recipientSet){$("recipient").value=target;draftChanged();}
  current.recipientSet=true;current.replyTo=m.id;
  $("replyChip").hidden=false;$("replyChipText").textContent=`Replying in thread · ${m.sender===state.sender?"your message":m.sender}`;
  formState();
}
$("threadFeed").addEventListener("scroll",()=>{if(thread){const f=$("threadFeed");thread.stick=f.scrollHeight-f.scrollTop-f.clientHeight<96;}},{passive:true});

/* Render floor */
function entries(text) {
  const items=[];
  for(const line of (text||"").split("\n")) {
    if(!line.trim())continue;
    const item=line.match(/^\s*[-*]\s+(.*)$/);
    if(item||!items.length)items.push(item?item[1]:line.trim());else items[items.length-1]+=" "+line.trim();
  }
  return items;
}
function renderSchedule() {
  const signature=JSON.stringify([state.schedule,logShown]);if(signature===scheduleSignature)return;scheduleSignature=signature;
  const view=$("scheduleView");view.replaceChildren();
  const blurbs={Holding:"Nobody is holding a render slot.",Waiting:"Nobody is waiting for a slot.",Handoffs:"No handoffs recorded.",Log:"No log entries yet."};
  for(const [i,title] of ["Holding","Waiting","Handoffs","Log"].entries()) {
    let items=entries(state.schedule[title]);
    if(title==="Log")items=items.reverse();
    const card=node("details","card schedule-card");card.open=title!=="Handoffs";card.style.setProperty("--i",i+3);
    const summary=node("summary");summary.append(node("span","",title),node("span","count-pill",String(items.length)),icon("chevron"));card.append(summary);
    if(!items.length){card.append(node("p","quiet",blurbs[title]));view.append(card);continue;}
    const list=node("ul","entries");
    for(const item of title==="Log"?items.slice(0,logShown):items){const li=node("li");li.append(inline(item));list.append(li);}
    card.append(list);
    if(title==="Log"&&items.length>logShown){const more=node("button","text-button",`Show ${Math.min(30,items.length-logShown)} older entries`);more.type="button";more.addEventListener("click",()=>{logShown+=30;renderSchedule();});card.append(more);}
    view.append(card);
  }
}
function renderContext() {
  const jobs=Object.entries(state.holders);
  $("renderSummary").textContent=jobs.length?`${jobs.map(([slot])=>slot).join(" + ")} slot busy`:"Both slots free";
  $("renderBadge").hidden=!jobs.length;
  const signature=JSON.stringify([state.holders,state.resources,state.sessions]);
  if(signature===contextSignature)return; contextSignature=signature;
  $("liveJobs").replaceChildren();
  for(const [slot,holder] of jobs) {
    const job=node("div","job"), label=node("div","job-label");
    label.append(node("span","dot live"),node("span","",`${slot} slot`),node("span","job-since",holder.time?`since ${clock(holder.time)}`:""));
    job.append(label,node("div","job-purpose",holder.purpose),node("div","job-checkout",holder.checkout));$("liveJobs").append(job);
  }
  if(!jobs.length)$("liveJobs").append(node("p","quiet","The render floor is clear."));
  const r=state.resources;
  $("resourceLine").replaceChildren(node("span","",r.fresh&&r.cpu!=null?`CPU ${Math.round(r.cpu)}%`:"CPU · no telemetry"),node("span","",r.fresh&&r.available_gib!=null?`${r.available_gib.toFixed(1)} GiB free`:"Memory · no telemetry"));
  $("sessions").replaceChildren();
  for(const [i,s] of state.sessions.entries()) {
    const a=node("a","session");a.href=s.url;a.target="_blank";a.rel="noopener noreferrer";
    const online=s.fresh&&s.connection==="connected"&&s.health==="healthy";
    const name=node("span","session-name");name.append(node("span","dot"+(online?" live":"")),node("span","",s.name||`Session ${i+1}`));
    a.append(name,node("span","session-state",!s.fresh?"Status stale":online?"Online":s.health?.startsWith("recovery_deferred")?"Recovery waiting":"Reconnecting"),icon("right"));$("sessions").append(a);
  }
  if(!state.sessions.length)$("sessions").append(node("p","quiet","No remote session monitor configured."));
}
function render() {
  $("lastUpdated").textContent=`Live · last synced ${clock(state.time)} · updates every 3 seconds`;
  renderRecipients();formState();renderAgents();renderHeader();renderFeed();renderContext();renderSchedule();
  if(thread)loadThread();
}
async function load(reset=false,before=0) {
  if(loading&&!reset)return;if(reset)controller?.abort();
  const number=++requestNumber;const activeController=new AbortController();controller=activeController;loading=true;
  const timer=setTimeout(()=>activeController.abort(),12000);
  try {
    const response=await fetch("/api/state?"+query(before),{signal:activeController.signal,cache:"no-store"});
    const result=await response.json();if(!response.ok)throw Error(result.error||"Could not load the board.");
    if(number!==requestNumber)return;
    const initial=!records.size;state=result;failed=false;
    for(const m of result.messages)records.set(m.id,m);
    if(before||initial)historyComplete=!result.has_more;
    $("errorBanner").hidden=true;render();
  } catch(error) {
    if(number!==requestNumber)return;
    prepending=false;failed=true;renderHeader();
    $("errorBanner").textContent=error.name==="AbortError"||error instanceof TypeError?"The board isn’t reachable right now. Your draft is saved. Reconnecting…":error.message;$("errorBanner").hidden=false;
  } finally { clearTimeout(timer);if(number===requestNumber)loading=false; }
}
$("broadcastForm").addEventListener("submit",async event=>{
  event.preventDefault();
  const files=uploads.filter(u=>u.status==="done").map(u=>u.id);
  if(sending||!state||!($("message").value.trim()||files.length)||uploads.some(u=>u.status!=="done"))return;
  if(!draftKey)draftKey=crypto.randomUUID();draftBody=$("message").value;draftTopic=$("broadcastTopic").value;draftRecipient=$("recipient").value;persistDraft();sending=true;formState();
  $("broadcastForm").classList.add("sending");composerStatus("Sending…");
  const replyTo=thread?.replyTo??null, abort=new AbortController(), timer=setTimeout(()=>abort.abort(),15000);
  try {
    const response=await fetch("/api/send",{method:"POST",headers:{"Content-Type":"application/json","X-Board-CSRF":state.csrf},body:JSON.stringify({body:draftBody,topic:draftTopic,recipient:draftRecipient,request_id:draftKey,attachments:files,reply_to:replyTo}),signal:abort.signal});
    const result=await response.json();if(!response.ok)throw Error(result.error||"Message failed. Your draft is saved; retry safely.");
    composerStatus(replyTo?"Replied in thread":draftRecipient==="*"?`Sent to ${result.recipients.length} agents`:`Sent to ${draftRecipient}`);
    $("message").value="";draftKey=null;draftBody="";
    for(const u of uploads)if(u.preview?.startsWith("blob:"))URL.revokeObjectURL(u.preview);
    uploads=[];renderTray();persistDraft();grow();
    if(touch.matches)$("message").blur();   // on a phone the keyboard closes once the message is away
    if(!$("messagePreview").hidden)$("previewButton").click();$("messagePreview").replaceChildren();
    if(thread){thread.stick=true;loadThread();load();}
    else {
      const before=selectedAgent, filtered=Boolean($("search").value||$("topicFilter").value);
      if(selectedAgent&&selectedAgent!==draftRecipient)selectedAgent=draftRecipient==="*"?"":draftRecipient;
      $("search").value="";$("topicFilter").value="";syncPills();agentsSignature="";stickToBottom=true;
      if(selectedAgent!==before||filtered)refreshFilters();else load();
    }
  } catch(error) {composerStatus(error.name==="AbortError"?"The connection timed out. Your draft is saved; tap send to finish this same message.":error.message,true);}
  finally {clearTimeout(timer);sending=false;$("broadcastForm").classList.remove("sending");formState();}
});
desktop.addEventListener("change",()=>{feedSignature="";if(state)renderFeed();});
renderTray();grow();formState();load();setInterval(()=>{if(!document.hidden)load();},3000);
document.addEventListener("visibilitychange",()=>{if(!document.hidden)load();});
