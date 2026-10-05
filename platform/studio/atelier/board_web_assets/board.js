"use strict";
const $ = id => document.getElementById(id);
const icons = {
  messages:'<path d="M21 11a8 8 0 0 1-8 8H7l-4 3V11a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8Z"/><path d="M8 9h8M8 13h5"/>',
  calendar:'<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M16 3v4M8 3v4M3 11h18M8 15h2M14 15h2"/>',
  agents:'<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6M21 20v-2a6 6 0 0 0-4-5"/>',
  broadcast:'<path d="m3 11 16-6v14L3 13zM6 14l2 6h3l-2-5M22 9v6"/>',
  remote:'<rect x="3" y="3" width="18" height="13" rx="2"/><path d="M8 21h8M12 16v5M7 8l3 2-3 2M13 12h4"/>',
  activity:'<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  send:'<path d="m22 2-7 20-4-9-9-4 20-7ZM11 13 22 2"/>',
  refresh:'<path d="M20 7a8 8 0 0 0-14-2L3 8M3 3v5h5M4 17a8 8 0 0 0 14 2l3-3M21 21v-5h-5"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
};
function node(tag, cls, text) { const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=text; return n; }
function icon(name) { const n=node("span"); n.innerHTML=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]||icons.messages}</svg>`; return n; }
document.querySelectorAll("[data-icon]").forEach(n=>n.append(icon(n.dataset.icon)));
const names={info:"Info",request:"Request",handoff:"Handoff",blocked:"Blocked",release:"Release",evidence:"Evidence",ack:"Acknowledged",alert:"Alert"};
let state=null, selectedAgent="", view="messages", records=new Map(), expanded=new Set(), deliveryOpen=new Set();
let loading=false, requestNumber=0, controller=null, historyComplete=false, sending=false;
let feedSignature="", sidebarSignature="", scheduleSignature="", contextSignature="";
let draftKey=null, draftBody="", draftTopic="", draftRecipient="*", recipientSignature="", previewRequest=0;
function persistDraft() { try { localStorage.setItem("atelier.board.draft",JSON.stringify({body:$("message").value,topic:$("broadcastTopic").value,recipient:$("recipient").value||draftRecipient,key:draftKey})); } catch {} }
try { const draft=JSON.parse(localStorage.getItem("atelier.board.draft")||"null"); if(draft) {$("message").value=draft.body||""; if([...$("broadcastTopic").options].some(o=>o.value===draft.topic))$("broadcastTopic").value=draft.topic; draftKey=draft.key; draftBody=$("message").value; draftTopic=$("broadcastTopic").value;draftRecipient=draft.recipient||"*";} } catch {}
function markdown(container, html, raw="") {
  container.classList.add("markdown");
  if(typeof html!=="string") {container.textContent=raw;return;}
  // HTML comes exclusively from the server's HTML-disabled Markdown renderer.
  const template=document.createElement("template");template.innerHTML=html;container.replaceChildren(template.content);
  container.querySelectorAll("table").forEach(table=>{const wrap=node("div","table-scroll");table.replaceWith(wrap);wrap.append(table);});
}
function renderRecipients() {
  const available=state.agents.filter(a=>!a.stop), signature=JSON.stringify(available.map(a=>[a.agent,a.listening,a.delivery_error]));
  if(signature===recipientSignature)return;recipientSignature=signature;
  const selected=$("recipient").value!=="*"?$("recipient").value:draftRecipient;
  $("recipient").replaceChildren(new Option(`Everyone · ${available.length} agents`,"*"));
  for(const a of available)$("recipient").add(new Option(a.agent+(!a.listening?" · offline":a.delivery_error?" · retrying delivery":""),a.agent));
  if(selected!=="*"&&!available.some(a=>a.agent===selected)){const option=new Option(selected+" · retired",selected);option.disabled=true;$("recipient").add(option);}
  $("recipient").value=selected;
}
function timeText(timestamp) { const date=new Date(timestamp*1000); const now=new Date(); return date.toDateString()===now.toDateString() ? date.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}) : date.toLocaleDateString([], {month:"short",day:"numeric"})+" · "+date.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}); }
function setView(next) {
  view=next;
  $("messageView").hidden=next!=="messages"; $("scheduleView").hidden=next!=="schedule";
  for(const [id,name] of [["messagesTab","messages"],["scheduleTab","schedule"]]) {$(id).classList.toggle("selected",next===name); if(next===name)$(id).setAttribute("aria-current","page"); else $(id).removeAttribute("aria-current");}
}
$("messagesTab").addEventListener("click",()=>setView("messages"));
$("scheduleTab").addEventListener("click",()=>setView("schedule"));
$("viewSchedule").addEventListener("click",()=>{setView("schedule");$("scheduleView").scrollIntoView({block:"start",behavior:"smooth"});});
$("composeButton").addEventListener("click",()=>{if(selectedAgent&&state?.agents.some(a=>a.agent===selectedAgent&&!a.stop)){$("recipient").value=selectedAgent;draftChanged();}$("composer").open=true;$("composer").scrollIntoView({block:"center",behavior:"smooth"});$("message").focus({preventScroll:true});});
if(matchMedia("(max-width:980px)").matches)$("composer").open=false;
if(matchMedia("(max-width:650px)").matches)$("remotePanel").open=false;
let previewTimer;
function draftChanged() { if($("message").value!==draftBody || $("broadcastTopic").value!==draftTopic || $("recipient").value!==draftRecipient)draftKey=null;draftRecipient=$("recipient").value;persistDraft();formState();if(!$("messagePreview").hidden){clearTimeout(previewTimer);previewTimer=setTimeout(preview,250);} }
function formState() { const target=$("recipient").value, count=state?.agents.filter(a=>!a.stop).length||0; $("characterCount").textContent=`${$("message").value.length.toLocaleString()} / 8,000`; $("recipientCount").textContent=target==="*"?`all ${count} agents`:target;$("sendLabel").textContent=target==="*"?"Send broadcast":"Send to agent"; $("sendButton").disabled=sending||!state||!count||!$("message").value.trim()||(target!=="*"&&!state.agents.some(a=>a.agent===target&&!a.stop)); }
$("message").addEventListener("input",draftChanged); $("broadcastTopic").addEventListener("change",draftChanged);$("recipient").addEventListener("change",draftChanged);
async function preview() {
  if(!state)return;const number=++previewRequest, controller=new AbortController(), timer=setTimeout(()=>controller.abort(),5000);
  try {const response=await fetch("/api/preview",{method:"POST",headers:{"Content-Type":"application/json","X-Board-CSRF":state.csrf},body:JSON.stringify({body:$("message").value}),signal:controller.signal});const result=await response.json();if(!response.ok)throw Error();if(number===previewRequest)markdown($("messagePreview"),result.html);}
  catch {if(number===previewRequest)$("messagePreview").textContent="Preview unavailable. Your draft is saved.";}
  finally {clearTimeout(timer);}
}
$("previewButton").addEventListener("click",()=>{const show=$("messagePreview").hidden;$("messagePreview").hidden=!show;$("previewButton").textContent=show?"Hide preview":"Preview";$("previewButton").setAttribute("aria-expanded",String(show));if(show)preview();});
$("message").addEventListener("keydown",event=>{if((event.metaKey||event.ctrlKey)&&event.key==="Enter"&&!$("sendButton").disabled){event.preventDefault();$("broadcastForm").requestSubmit();}});
function query(before=0) { const q=new URLSearchParams(); if(selectedAgent)q.set("agent",selectedAgent); if($("search").value.trim())q.set("q",$("search").value.trim()); if($("topicFilter").value)q.set("topic",$("topicFilter").value); if(before)q.set("before",before); return q.toString(); }
function refreshFilters() { records.clear(); feedSignature=""; historyComplete=false; load(true); }
let searchTimer;
$("search").addEventListener("input",()=>{clearTimeout(searchTimer);searchTimer=setTimeout(refreshFilters,250);});
$("topicFilter").addEventListener("change",refreshFilters);
$("loadOlder").addEventListener("click",()=>load(false,Math.min(...records.keys())));
function renderSidebar() {
  const agents=state.agents, signature=JSON.stringify([selectedAgent,agents.map(a=>[a.agent,a.listening,a.stop,a.pending,a.supervised,a.delivery_error])]);
  if(signature===sidebarSignature)return; sidebarSignature=signature;
  $("agents").replaceChildren(); $("agentCount").textContent=agents.filter(a=>!a.stop).length;
  function add(name,label,agent) {
    const b=node("button","agent-button"+(selectedAgent===name?" selected":"")+(agent?.stop?" paused":""));
    b.type="button"; b.setAttribute("aria-pressed",String(selectedAgent===name));
    b.append(node("span","dot"+(agent?.delivery_error?" error-dot":!agent||agent.listening?" live-dot":"")),node("span","agent-name",label));
    if(agent?.pending)b.append(node("span","pending",String(agent.pending)));
    if(agent)b.title=`${label} · ${agent.stop?"Retired":agent.delivery_error?"Delivery retrying":agent.listening?"Listening":"Not listening"}${agent.supervised?" · Auto-recovery enabled":""}${agent.pending?` · ${agent.pending} pending`:""}`;
    b.addEventListener("click",()=>{selectedAgent=name;setView("messages");renderSidebar();refreshFilters();});
    $("agents").append(b);
  }
  add("","All agents"); for(const agent of [...agents].sort((a,b)=>a.stop-b.stop||a.agent.localeCompare(b.agent)))add(agent.agent,agent.agent,agent);
}
function renderFeed() {
  const agents=new Map(state.agents.map(a=>[a.agent,a]));
  const signature=JSON.stringify([[...records.values()],state.agents.map(a=>[a.agent,a.cursor,a.delivery_error]),[...expanded],selectedAgent,$("search").value,$("topicFilter").value]);
  if(signature===feedSignature)return; feedSignature=signature;
  const groups=new Map();
  for(const m of [...records.values()].sort((a,b)=>b.id-a.id)) {
    const broadcast=(m.dedup||"").match(/^web-broadcast:([a-f0-9-]+):/);
    const key=broadcast?broadcast[1]:String(m.id);
    if(!groups.has(key))groups.set(key,{key,broadcast:Boolean(broadcast),messages:[]});
    groups.get(key).messages.push(m);
  }
  $("feed").replaceChildren(); $("messageCount").textContent=groups.size;
  $("activeFilter").hidden=!selectedAgent;
  if(selectedAgent) { const clear=node("button","", "Clear filter ×");clear.addEventListener("click",()=>{selectedAgent="";renderSidebar();refreshFilters();});$("activeFilter").replaceChildren(node("span","",`Showing ${selectedAgent}`),clear); }
  if(!groups.size) {
    const empty=node("div","empty"); empty.append(icon("messages"),node("h3","",selectedAgent||$("search").value||$("topicFilter").value?"No matching messages":"A quiet board, for now"),node("p","","Send a message to start the conversation."));$("feed").append(empty);
  }
  for(const group of groups.values()) {
    const m=group.messages[0], article=node("article","message"+(group.broadcast?" broadcast":"")); article.dataset.messageId=m.id;
    const header=node("div","message-header"), human=m.sender===state.sender;
    header.append(node("span","avatar"+(human?" human":""), human?"YOU":m.sender.slice(0,2).toUpperCase()));
    const sender=node("div","sender-info");sender.append(node("span","sender",human?"You":m.sender),node("span","route",group.broadcast?`Broadcast · ${group.messages.length} agents`:m.recipient==="*"?"To all agents":`To ${m.recipient}`));header.append(sender,node("span","topic "+m.topic,names[m.topic]||m.topic));
    const clock=node("time","message-time",timeText(m.created));clock.dateTime=new Date(m.created*1000).toISOString();clock.title=clock.dateTime;header.append(clock);article.append(header);
    if(m.reply_to)article.append(node("div","reply-tag",`↳ Reply to #${m.reply_to}`));
    const long=m.body.length>600||m.body.split("\n").length>8;
    const body=node("div","message-body"+(long&&!expanded.has(group.key)?" collapsed":""));markdown(body,m.body_html,m.body);article.append(body);
    if(long) {const expand=node("button","expand-button",expanded.has(group.key)?"Show less":"Read full message ↓");expand.addEventListener("click",()=>{expanded.has(group.key)?expanded.delete(group.key):expanded.add(group.key);renderFeed();});article.append(expand);}
    const footer=node("div","message-footer");const ids=group.messages.map(item=>item.id).sort((a,b)=>a-b);
    footer.append(node("span","",group.broadcast?`Broadcast #${ids[0]}${ids.length>1?`–${ids.at(-1)}`:""}`:`Message #${m.id}`));
    if(group.broadcast) {
      const pickedUp=group.messages.filter(item=>(agents.get(item.recipient)?.cursor||0)>=item.id), acked=group.messages.filter(item=>item.acknowledged);
      const details=node("details","delivery-details"), receipt=node("summary","receipt");receipt.append(icon("check"),node("span","",`Sent ${pickedUp.length} / ${group.messages.length} · Ack ${acked.length} ⌄`));
      const list=node("div","delivery-list");
      for(const item of group.messages) {const agent=agents.get(item.recipient), picked=(agent?.cursor||0)>=item.id;const row=node("div","delivery-row");row.append(node("span","",item.recipient),node("span",picked?"picked":"queued",item.acknowledged?"Acknowledged":picked?"Sent to session":agent?.delivery_error?"Retrying":"Pending"));list.append(row);}
      details.append(receipt,list);details.open=deliveryOpen.has(group.key);details.addEventListener("toggle",()=>{details.open?deliveryOpen.add(group.key):deliveryOpen.delete(group.key);});footer.append(details);
    } else {const agent=agents.get(m.recipient),picked=(agent?.cursor||0)>=m.id;footer.append(node("span","",m.recipient==="*"?"Shared with the board":m.acknowledged?"Acknowledged":picked?"Sent to session · awaiting acknowledgement":agent?.delivery_error?"Delivery retrying":"Pending delivery"));}
    article.append(footer);$("feed").append(article);
  }
}
function renderContext() {
  const signature=JSON.stringify([state.holders,state.resources,state.sessions]);
  if(signature===contextSignature)return; contextSignature=signature;
  $("liveJobs").replaceChildren();
  for(const [slot,holder] of Object.entries(state.holders)) {
    const job=node("div","live-job"), label=node("div","job-label");label.append(node("span","dot live-dot"),node("span","",`${slot.toUpperCase()} SLOT · RUNNING`));job.append(label,node("div","job-purpose",holder.purpose),node("div","job-checkout",holder.checkout));$("liveJobs").append(job);
  }
  if(!Object.keys(state.holders).length)$("liveJobs").append(node("p","quiet-message","The render floor is clear. Check the schedule for what’s next."));
  const r=state.resources; $("resourceLine").replaceChildren(node("span","",r.fresh&&r.cpu!==null?`CPU · ${Math.round(r.cpu)}%`:"CPU · awaiting telemetry"),node("span","",r.fresh&&r.available_gib!==null?`${r.available_gib.toFixed(1)} GiB available`:"Memory · awaiting telemetry"));
  $("sessions").replaceChildren();
  for(const [i,s] of state.sessions.entries()) {
    const a=node("a","session-link");a.href=s.url;a.target="_blank";a.rel="noopener noreferrer";
    const online=s.fresh&&s.connection==="connected"&&s.health==="healthy";
    const name=node("span","session-name"), status=node("span","session-state");
    name.append(node("span","dot"+(online?" live-dot":"")),node("span","",s.name||`Session ${i+1}`));status.append(node("span","",!s.fresh?"Status stale":online?"Online":s.health?.startsWith("recovery_deferred")?"Recovery waiting":"Reconnecting"),node("span","","↗"));a.append(name,status);$("sessions").append(a);
  }
  if(!state.sessions.length)$("sessions").append(node("p","quiet-message","No remote session monitor configured."));
}
function renderSchedule() {
  const signature=JSON.stringify(state.schedule);if(signature===scheduleSignature)return;scheduleSignature=signature;$("scheduleView").replaceChildren();
  for(const title of ["Holding","Waiting","Handoffs","Log"]) {
    const card=node("section","schedule-card"); card.append(node("h2","",title));
    card.append(node("div",state.schedule[title]?"schedule-text":"schedule-empty",state.schedule[title]||"No entries right now."));$("scheduleView").append(card);
  }
}
function render() {
  const agents=state.agents.filter(a=>!a.stop), listening=agents.filter(a=>a.listening).length;
  $("listeningStat").textContent=String(listening);$("listeningStat").append(node("span","",`/ ${agents.length}`));
  $("listeningNote").textContent=`${agents.length-listening} waiting to check in`;
  const online=state.sessions.filter(s=>s.fresh&&s.connection==="connected"&&s.health==="healthy").length;
  $("sessionStat").textContent=state.sessions.length?`${online} online`:"—"; $("sessionNote").textContent=state.sessions.length?`${state.sessions.length} sessions on this machine`:"Monitor not configured";
  const jobs=Object.keys(state.holders).length;$("renderStat").textContent=jobs?`${jobs} ${jobs===1?"job":"jobs"}`:"Idle";$("renderNote").textContent=jobs?Object.keys(state.holders).join(" + ")+" slot occupied":"Ready for the next turn";
  $("lastUpdated").textContent="Last synced "+timeText(state.time);renderRecipients();formState();renderSidebar();renderFeed();renderContext();renderSchedule();
  $("loadOlder").hidden=historyComplete||!records.size;
}
async function load(reset=false,before=0) {
  if(loading&&!reset)return;if(reset)controller?.abort();
  const number=++requestNumber;const activeController=new AbortController();controller=activeController;loading=true;
  const timer=setTimeout(()=>activeController.abort(),12000);
  try {
    const response=await fetch("/api/state?"+query(before),{signal:activeController.signal,cache:"no-store"});
    const result=await response.json();if(!response.ok)throw Error(result.error||"Could not load the board.");
    if(number!==requestNumber)return;
    const initial=!records.size;state=result;
    for(const m of result.messages)records.set(m.id,m);
    if(before||initial)historyComplete=!result.has_more;
    $("connection").className="connection live";$("connection").replaceChildren(node("span","dot"),node("span","","Live board"));$("errorBanner").hidden=true;render();
  } catch(error) {
    if(number!==requestNumber)return;
    $("connection").className="connection failed";$("connection").replaceChildren(node("span","dot"),node("span","","Reconnecting"));
    $("errorBanner").textContent="The board isn’t reachable right now. Your draft is saved. Reconnecting automatically…";$("errorBanner").hidden=false;
  } finally { clearTimeout(timer);if(number===requestNumber)loading=false; }
}
$("broadcastForm").addEventListener("submit",async event=>{
  event.preventDefault();if(sending||!state||!$("message").value.trim())return;
  if(!draftKey)draftKey=crypto.randomUUID();draftBody=$("message").value;draftTopic=$("broadcastTopic").value;draftRecipient=$("recipient").value;persistDraft();sending=true;formState();
  $("message").disabled=true;$("broadcastTopic").disabled=true;$("recipient").disabled=true;$("composerStatus").className="composer-status";$("composerStatus").textContent="Sending to your agents…";
  const abort=new AbortController(), timer=setTimeout(()=>abort.abort(),15000);
  try {
    const response=await fetch("/api/send",{method:"POST",headers:{"Content-Type":"application/json","X-Board-CSRF":state.csrf},body:JSON.stringify({body:draftBody,topic:draftTopic,recipient:draftRecipient,request_id:draftKey}),signal:abort.signal});
    const result=await response.json();if(!response.ok)throw Error(result.error||"Message failed. Your draft is saved; retry safely.");
    $("composerStatus").textContent=`Saved for ${draftRecipient==="*"?`${result.recipients.length} agents`:draftRecipient}. Delivery and acknowledgement appear on your message.`;
    $("message").value="";draftKey=null;draftBody="";persistDraft();$("messagePreview").replaceChildren();selectedAgent=draftRecipient==="*"?"":draftRecipient;$("search").value="";$("topicFilter").value="";setView("messages");refreshFilters();
  } catch(error) {$("composerStatus").className="composer-status error";$("composerStatus").textContent=error.name==="AbortError"?"The connection timed out. Your draft is saved; retry to finish this same message.":error.message;}
  finally {clearTimeout(timer);sending=false;$("message").disabled=false;$("broadcastTopic").disabled=false;$("recipient").disabled=false;formState();}
});
formState();load();setInterval(()=>{if(!document.hidden)load();},3000);
document.addEventListener("visibilitychange",()=>{if(!document.hidden)load();});
