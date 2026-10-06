"use strict";
const $ = id => document.getElementById(id);
const icons = {
  messages:'<path d="M21 11a8 8 0 0 1-8 8H7l-4 3V11a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8Z"/><path d="M8 9h8M8 13h5"/>',
  agents:'<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6M21 20v-2a6 6 0 0 0-4-5"/>',
  remote:'<rect x="3" y="3" width="18" height="13" rx="2"/><path d="M8 21h8M12 16v5M7 8l3 2-3 2M13 12h4"/>',
  activity:'<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  send:'<path d="M21.5 2.5 10.5 13.5M21.5 2.5l-7 19-4-8-8-4 19-7Z"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  back:'<path d="m15 5-7 7 7 7"/>',
  chevron:'<path d="m6 9 6 6 6-6"/>',
  right:'<path d="m9 5 7 7-7 7"/>',
  down:'<path d="M12 5v14M5 12l7 7 7-7"/>',
  board:'<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
  render:'<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
};
function node(tag, cls, text) { const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=text; return n; }
function icon(name) { const n=node("span","icon"); n.innerHTML=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]||icons.messages}</svg>`; return n; }
document.querySelectorAll("[data-icon]").forEach(n=>n.append(icon(n.dataset.icon)));
const names={info:"Info",request:"Request",handoff:"Handoff",blocked:"Blocked",release:"Release",evidence:"Evidence",ack:"Ack",alert:"Alert"};
const desktop=matchMedia("(min-width:1100px)"), touch=matchMedia("(hover:none)");
let state=null, selectedAgent="", records=new Map(), expanded=new Set(), deliveryOpen=new Set(), logShown=12;
let loading=false, requestNumber=0, controller=null, historyComplete=false, sending=false, failed=false;
let feedSignature="", agentsSignature="", scheduleSignature="", contextSignature="";
let draftKey=null, draftBody="", draftTopic="", draftRecipient="*", recipientSignature="", previewRequest=0;
let stickToBottom=true, prepending=false, lastSeenId=0, newestShown=0, statusTimer=0;
let showSystem=true;
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

function persistDraft() { try { localStorage.setItem("atelier.board.draft",JSON.stringify({body:$("message").value,topic:$("broadcastTopic").value,recipient:$("recipient").value||draftRecipient,key:draftKey})); } catch {} }
try { const draft=JSON.parse(localStorage.getItem("atelier.board.draft")||"null"); if(draft) {$("message").value=draft.body||""; if([...$("broadcastTopic").options].some(o=>o.value===draft.topic))$("broadcastTopic").value=draft.topic; draftKey=draft.key; draftBody=$("message").value; draftTopic=$("broadcastTopic").value;draftRecipient=draft.recipient||"*";} } catch {}

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
  if(agent&&!agent.stop)o.append(node("span","badge "+statusOf(agent)));
  return o;
}
function clock(timestamp) { return new Date(timestamp*1000).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}); }
function dayLabel(timestamp) {
  const date=new Date(timestamp*1000), today=new Date(), yesterday=new Date(Date.now()-864e5);
  if(date.toDateString()===today.toDateString())return "Today";
  if(date.toDateString()===yesterday.toDateString())return "Yesterday";
  return date.toLocaleDateString([], {weekday:"short",month:"short",day:"numeric"});
}
function agentStatus(a) { return a.stop?"Retired":a.delivery_error?"Delivery retrying":a.listening?"Listening":"Offline"; }
function isSystem(m) { return /(^|-)watch$/.test(m.sender); }
function liveAgents() { return state?state.agents.filter(a=>!a.stop):[]; }

/* Views: one pane at a time on phones, all three side by side on wide screens. */
function setView(next) {
  $("app").dataset.view=next;
  document.querySelectorAll(".tab").forEach(tab=>{if(tab.dataset.view===next)tab.setAttribute("aria-current","page");else tab.removeAttribute("aria-current");});
  if(next==="messages"){stickToBottom=stickToBottom||!newestShown;requestAnimationFrame(()=>{if(stickToBottom)scrollToLatest();markSeen();});}
}
document.querySelectorAll(".tab").forEach(tab=>tab.addEventListener("click",()=>{
  if(tab.dataset.view==="messages"&&$("app").dataset.view==="messages")scrollToLatest(true);
  setView(tab.dataset.view);
}));
function selectAgent(name) {
  selectedAgent=name;
  const agent=state?.agents.find(a=>a.agent===name&&!a.stop);
  const target=name===""?"*":agent?name:null;
  if(target&&$("recipient").value!==target&&[...$("recipient").options].some(o=>o.value===target&&!o.disabled)){$("recipient").value=target;draftChanged();}
  setView("messages");agentsSignature="";renderAgents();renderHeader();refreshFilters();
}
$("backButton").addEventListener("click",()=>selectAgent(""));

/* Search and filters */
$("searchToggle").addEventListener("click",()=>{
  const show=$("searchBar").hidden;$("searchBar").hidden=!show;$("searchToggle").setAttribute("aria-expanded",String(show));
  if(show&&!touch.matches)$("search").focus();
  else if($("search").value||$("topicFilter").value){$("search").value="";$("topicFilter").value="";syncPills();refreshFilters();}
  $("searchToggle").classList.toggle("active",show);
});
function query(before=0) { const q=new URLSearchParams(); if(selectedAgent)q.set("agent",selectedAgent); if($("search").value.trim())q.set("q",$("search").value.trim()); if($("topicFilter").value)q.set("topic",$("topicFilter").value); if(before)q.set("before",before); return q.toString(); }
function refreshFilters() { records.clear(); feedSignature=""; historyComplete=false; stickToBottom=true; prepending=false; lastSeenId=0; load(true); }
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
  $("characterCount").textContent=length>6000?`${length.toLocaleString()} / 8,000`:"";
  $("sendButton").setAttribute("aria-label",target==="*"?`Send to all ${count} agents`:`Send to ${target}`);
  $("sendButton").disabled=sending||!state||!count||!$("message").value.trim()||(target!=="*"&&!state.agents.some(a=>a.agent===target&&!a.stop));
  $("broadcastForm").classList.toggle("has-text",Boolean(length));
}
$("message").addEventListener("input",()=>{grow();draftChanged();}); $("broadcastTopic").addEventListener("change",draftChanged);$("recipient").addEventListener("change",draftChanged);
async function preview() {
  if(!state)return;const number=++previewRequest, abort=new AbortController(), timer=setTimeout(()=>abort.abort(),5000);
  try {const response=await fetch("/api/preview",{method:"POST",headers:{"Content-Type":"application/json","X-Board-CSRF":state.csrf},body:JSON.stringify({body:$("message").value}),signal:abort.signal});const result=await response.json();if(!response.ok)throw Error();if(number===previewRequest)markdown($("messagePreview"),result.html);}
  catch {if(number===previewRequest)$("messagePreview").textContent="Preview unavailable. Your draft is saved.";}
  finally {clearTimeout(timer);}
}
$("previewButton").addEventListener("click",()=>{const show=$("messagePreview").hidden;$("messagePreview").hidden=!show;$("previewButton").textContent=show?"Edit":"Preview";$("previewButton").setAttribute("aria-expanded",String(show));if(show)preview();});
$("message").addEventListener("keydown",event=>{if((event.metaKey||event.ctrlKey)&&event.key==="Enter"&&!$("sendButton").disabled){event.preventDefault();$("broadcastForm").requestSubmit();}});
// Keep the keyboard up when tapping send, so the button doesn't move under the finger.
$("sendButton").addEventListener("pointerdown",event=>{if(document.activeElement===$("message"))event.preventDefault();});
let blurTimer;
$("message").addEventListener("focus",()=>{clearTimeout(blurTimer);if(touch.matches)$("app").classList.add("typing");if(stickToBottom)setTimeout(scrollToLatest,250);});
$("message").addEventListener("blur",()=>{blurTimer=setTimeout(()=>$("app").classList.remove("typing"),120);});
function composerStatus(text, error=false) {
  clearTimeout(statusTimer);$("composerStatus").textContent=text;$("composerStatus").className="composer-status"+(error?" error":"")+(text?" shown":"");
  if(text&&!error)statusTimer=setTimeout(()=>composerStatus(""),4000);
}

/* Agents: the list pane and the orb row share one render. */
function renderAgents() {
  const agents=state.agents, signature=JSON.stringify([selectedAgent,agents.map(a=>[a.agent,a.listening,a.stop,a.pending,a.supervised,a.delivery_error,a.checkout])]);
  if(signature===agentsSignature)return; agentsSignature=signature;
  const live=liveAgents(), listening=live.filter(a=>a.listening).length, errors=live.filter(a=>a.delivery_error).length;
  $("agentsSummary").textContent=`${listening} of ${live.length} listening${errors?` · ${errors} retrying delivery`:""}`;
  $("agentsBadge").hidden=!errors;$("agentsBadge").textContent=errors;
  const list=$("agents"), orbs=$("agentChips");list.replaceChildren();orbs.replaceChildren();
  function row(name, agent) {
    const chosen=selectedAgent===name;
    const b=node("button","agent-row"+(agent?.stop?" retired":""));b.type="button";b.setAttribute("role","listitem");if(chosen)b.setAttribute("aria-current","true");
    const text=node("span","agent-text"), detail=node("span","agent-detail");text.append(node("span","agent-name",name||"Everyone"));
    if(agent){detail.append(node("span","state "+statusOf(agent),agentStatus(agent)));for(const part of [agent.supervised&&!agent.stop?"auto-recovery":"",agent.checkout||""].filter(Boolean))detail.append(document.createTextNode(" · "+part));}
    else detail.textContent=`Broadcasts and every conversation`;
    text.append(detail);b.append(orb(name||"*",agent),text);
    if(agent?.pending)b.append(node("span","count",`${agent.pending} queued`));
    b.append(icon("right"));b.addEventListener("click",()=>selectAgent(name));list.append(b);
    if(agent?.stop)return;
    const o=node("button","orb-button");o.type="button";if(chosen)o.setAttribute("aria-current","true");
    const face=orb(name||"*",agent);if(agent?.pending)face.append(node("span","count-badge",String(agent.pending)));
    o.append(face,node("span","orb-name",name||"Everyone"));
    o.append(node("span","orb-state "+statusOf(agent),agent?(agent.delivery_error?"Retrying":agent.listening?"Online":"Offline"):`${listening} online`));
    o.title=agent?`${name} · ${agentStatus(agent)}`:"All conversations";
    o.addEventListener("click",()=>selectAgent(name));orbs.append(o);
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
  const subtitle=$("chatSubtitle"), dot=node("span","dot");
  let text;
  if(failed){dot.classList.add("error");text="Reconnecting…";}
  else if(!state){text="Connecting…";}
  else if(agent){dot.classList.add(agent.delivery_error?"error":agent.listening?"live":"idle");text=agentStatus(agent)+(agent.pending?` · ${agent.pending} queued`:"");}
  else {dot.classList.add(listening?"live":"idle");text=`${listening} of ${live.length} agents listening`;}
  if(agent)dot.className="dot "+statusOf(agent);
  subtitle.replaceChildren(dot,node("span","",text));
}

/* Feed: oldest at the top, newest by the composer, like a chat. */
function feedNearBottom() { const f=$("feed"); return f.scrollHeight-f.scrollTop-f.clientHeight<96; }
function scrollToLatest(smooth=false) { const f=$("feed"); f.scrollTo({top:f.scrollHeight,behavior:smooth?"smooth":"auto"}); stickToBottom=true; markSeen(); }
function markSeen() {
  if($("app").dataset.view!=="messages"&&!desktop.matches)return;
  if(feedNearBottom()||stickToBottom){lastSeenId=Math.max(lastSeenId,newestShown);$("jumpLatest").hidden=true;updateBadges();}
}
function updateBadges(unread=0) {
  const away=$("app").dataset.view!=="messages"&&!desktop.matches;
  $("messagesBadge").hidden=!(away&&unread);$("messagesBadge").textContent=unread>99?"99+":unread;
  $("jumpLabel").textContent=unread?`${unread} new`:"Latest";
}
$("feed").addEventListener("scroll",()=>{
  stickToBottom=feedNearBottom();
  if(stickToBottom)markSeen();else $("jumpLatest").hidden=false;
  if($("feed").scrollTop<120&&!historyComplete&&records.size&&!loading)loadOlder();
},{passive:true});
$("jumpLatest").addEventListener("click",()=>scrollToLatest(true));
// Opening search, a growing draft or the keyboard shrinks the feed: stay pinned to the latest message.
const pin=new ResizeObserver(()=>{$("app").style.setProperty("--dock-h",`${$("broadcastForm").offsetHeight}px`);if(stickToBottom)$("feed").scrollTop=$("feed").scrollHeight;});
pin.observe($("feed"));pin.observe($("broadcastForm"));
function loadOlder() { if(loading||!records.size)return; prepending=true; load(false,Math.min(...records.keys())); }
$("loadOlder").addEventListener("click",loadOlder);
function jumpTo(id) {
  const target=$("messages").querySelector(`[data-ids~="${id}"]`);
  if(!target)return;$("feed").scrollTo({top:target.offsetTop-$("feed").clientHeight/3,behavior:"smooth"});target.classList.remove("flash");void target.offsetWidth;target.classList.add("flash");
}
function groupsFrom(messages) {
  const groups=new Map();
  for(const m of messages) {
    const broadcast=(m.dedup||"").match(/^web-broadcast:([a-f0-9-]+):/);
    const key=broadcast?broadcast[1]:String(m.id);
    if(!groups.has(key))groups.set(key,{key,broadcast:Boolean(broadcast),messages:[]});
    groups.get(key).messages.push(m);
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
function renderFeed() {
  const agents=new Map(state.agents.map(a=>[a.agent,a]));
  const signature=JSON.stringify([[...records.keys()],state.agents.map(a=>[a.agent,a.cursor,a.delivery_error]),[...records.values()].map(m=>m.acknowledged),[...expanded],[...deliveryOpen],showSystem,historyComplete]);
  if(signature===feedSignature)return; feedSignature=signature;
  const feed=$("feed"), top=feed.scrollTop, fromBottom=feed.scrollHeight-feed.scrollTop, stick=stickToBottom;
  const groups=groupsFrom([...records.values()]), visible=groups.filter(g=>showSystem||!isSystem(g.first));
  const out=document.createDocumentFragment();
  let day="", previous=null, notices=null;
  const filtered=Boolean(selectedAgent||$("search").value.trim()||$("topicFilter").value);
  if(!visible.length) {
    const empty=node("div","empty");empty.append(icon("messages"),node("h2","",filtered?"No matching messages":"A quiet board, for now"),node("p","",selectedAgent?`Say hello to ${selectedAgent} below.`:filtered?"Try a different search or topic.":"Send a message to start the conversation."));out.append(empty);
  }
  for(const group of visible) {
    const m=group.first, label=dayLabel(m.created);
    if(label!==day){day=label;previous=null;notices=null;const sep=node("div","day");sep.append(node("span","",label));out.append(sep);}
    if(isSystem(m)) {
      // Consecutive automatic notices collapse into one quiet line.
      if(notices){notices.count++;notices.last=m;notices.ids.push(m.id);const sections=(m.body.match(/changed \(([^)]*)\)/)||[])[1];if(sections)sections.split(/,\s*/).forEach(s=>notices.sections.add(s));notices.update();continue;}
      const line=node("details","notice");line.dataset.ids=String(m.id);
      const summary=node("summary"), text=node("span","notice-text"), when=node("time");summary.append(icon("board"),text,when);line.append(summary,node("p","",m.body));
      notices={count:1,first:m,last:m,ids:[m.id],sections:new Set(((m.body.match(/changed \(([^)]*)\)/)||[])[1]||"").split(/,\s*/).filter(Boolean)),
        update(){const what=/render scheduling board changed/i.test(this.last.body)?`Render schedule updated${this.sections.size?` · ${[...this.sections].join(", ")}`:""}`:`${this.last.sender}: ${this.last.body.slice(0,80)}`;
          text.textContent=`${what}${this.count>1?` · ${this.count}×`:""}`;when.textContent=clock(this.last.created);line.dataset.ids=this.ids.join(" ");line.lastElementChild.textContent=this.last.body;}};
      notices.update();out.append(line);previous=null;continue;
    }
    notices=null;
    const mine=m.sender===state.sender;
    const continued=previous&&previous.sender===m.sender&&previous.recipient===m.recipient&&previous.topic===m.topic&&m.created-previous.created<300&&!group.broadcast&&!previous.broadcast;
    const article=node("article","message"+(mine?" mine":"")+(continued?" continued":"")+(m.topic==="alert"||m.topic==="blocked"?" urgent":""));
    article.dataset.ids=group.messages.map(item=>item.id).join(" ");
    if(!mine)article.append(continued?node("span","orb-space"):orb(m.sender));
    const column=node("div","message-column"), bubble=node("div","card bubble");
    if(!continued) {
      const meta=node("div","meta");
      meta.append(node("span","sender",mine?"You":m.sender));
      const to=group.broadcast||m.recipient==="*"?"everyone":m.recipient===state.sender?"you":m.recipient;
      meta.append(node("span","route",`to ${to==="everyone"&&group.broadcast?`everyone (${group.messages.length})`:to}`));
      if(m.topic!=="info")meta.append(node("span","topic "+m.topic,names[m.topic]||m.topic));
      const time=node("time","time",clock(m.created));time.dateTime=new Date(m.created*1000).toISOString();time.title=`${new Date(m.created*1000).toLocaleString()} · #${m.id}`;meta.append(time);
      bubble.append(meta);
    }
    if(m.reply_to) {
      const original=records.get(m.reply_to), quote=node("button","quote");quote.type="button";
      quote.append(node("span","quote-who",original?(original.sender===state.sender?"You":original.sender):`Reply to #${m.reply_to}`));
      if(original)quote.append(node("span","quote-text",original.body.replace(/[*_`#>]+/g,"").replace(/\s+/g," ").trim().slice(0,140)));
      quote.addEventListener("click",()=>jumpTo(m.reply_to));bubble.append(quote);
    }
    const long=m.body.length>900||m.body.split("\n").length>14, collapsed=long&&!expanded.has(group.key);
    const body=node("div","body"+(collapsed?" collapsed":""));markdown(body,m.body_html,m.body);bubble.append(body);
    if(long){const more=node("button","more",collapsed?"Read more":"Show less");more.type="button";more.addEventListener("click",()=>{collapsed?expanded.add(group.key):expanded.delete(group.key);renderFeed();});bubble.append(more);}
    if(continued){const time=node("time","bubble-time",clock(m.created));time.title=`#${m.id}`;bubble.append(time);}
    column.append(bubble);
    if(mine)column.append(receipt(group,agents));
    article.append(column);out.append(article);previous={sender:m.sender,recipient:m.recipient,topic:m.topic,created:m.created,broadcast:group.broadcast};
  }
  $("messages").replaceChildren(out);
  $("loadOlder").hidden=historyComplete||!records.size;
  const newest=visible.length?Math.max(...visible.at(-1).messages.map(item=>item.id)):0;
  const unread=visible.filter(g=>!isSystem(g.first)&&g.first.id>lastSeenId&&g.first.sender!==state.sender).length;
  newestShown=newest;
  if(prepending){feed.scrollTop=feed.scrollHeight-fromBottom;prepending=false;}
  else if(stick){feed.scrollTop=feed.scrollHeight;}
  else {feed.scrollTop=top;}
  const viewing=$("app").dataset.view==="messages"||desktop.matches;
  if(!lastSeenId||(stick&&viewing))lastSeenId=newest;
  $("jumpLatest").hidden=feedNearBottom();
  updateBadges(stick&&viewing?0:unread);
}

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
  for(const title of ["Holding","Waiting","Handoffs","Log"]) {
    let items=entries(state.schedule[title]);
    if(title==="Log")items=items.reverse();
    const card=node("details","card schedule-card");card.open=title!=="Handoffs";
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
  event.preventDefault();if(sending||!state||!$("message").value.trim())return;
  if(!draftKey)draftKey=crypto.randomUUID();draftBody=$("message").value;draftTopic=$("broadcastTopic").value;draftRecipient=$("recipient").value;persistDraft();sending=true;formState();
  $("broadcastForm").classList.add("sending");composerStatus("Sending…");
  const abort=new AbortController(), timer=setTimeout(()=>abort.abort(),15000);
  try {
    const response=await fetch("/api/send",{method:"POST",headers:{"Content-Type":"application/json","X-Board-CSRF":state.csrf},body:JSON.stringify({body:draftBody,topic:draftTopic,recipient:draftRecipient,request_id:draftKey}),signal:abort.signal});
    const result=await response.json();if(!response.ok)throw Error(result.error||"Message failed. Your draft is saved; retry safely.");
    composerStatus(draftRecipient==="*"?`Sent to ${result.recipients.length} agents`:`Sent to ${draftRecipient}`);
    $("message").value="";draftKey=null;draftBody="";persistDraft();grow();
    if(!$("messagePreview").hidden)$("previewButton").click();$("messagePreview").replaceChildren();
    if(selectedAgent&&selectedAgent!==draftRecipient)selectedAgent=draftRecipient==="*"?"":draftRecipient;
    $("search").value="";$("topicFilter").value="";agentsSignature="";refreshFilters();
  } catch(error) {composerStatus(error.name==="AbortError"?"The connection timed out. Your draft is saved; tap send to finish this same message.":error.message,true);}
  finally {clearTimeout(timer);sending=false;$("broadcastForm").classList.remove("sending");formState();}
});
desktop.addEventListener("change",()=>{feedSignature="";if(state)renderFeed();});
grow();formState();load();setInterval(()=>{if(!document.hidden)load();},3000);
document.addEventListener("visibilitychange",()=>{if(!document.hidden)load();});
