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
  up:'<path d="M12 19V5M5 12l7-7 7 7"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  close:'<path d="M6 6l12 12M18 6 6 18"/>',
  remove:'<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
  file:'<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z"/><path d="M14 3v5h5"/>',
  play:'<path d="M8 5v14l11-7L8 5Z"/>',
  thread:'<path d="M7 8h10M7 12h6"/><path d="M21 12a8 8 0 0 1-8 8H5l-2 2V12a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8Z"/>',
  reply:'<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 6 6v5"/>',
  board:'<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
  activity:'<path d="M6 9a6 6 0 0 1 12 0c0 6 2.5 8 2.5 8h-17S6 15 6 9Z"/><path d="M10 20.5a2.2 2.2 0 0 0 4 0"/>',
  tasks:'<path d="M5 21V4"/><path d="M5 4h12l-2.5 4L17 12H5"/>',
  render:'<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
};
function node(tag, cls, text) { const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=text; return n; }
function icon(name) { const n=node("span","icon"); n.innerHTML=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]||icons.messages}</svg>`; return n; }
document.querySelectorAll("[data-icon]").forEach(n=>n.append(icon(n.dataset.icon)));
const names={info:"Info",request:"Request",handoff:"Handoff",blocked:"Blocked",release:"Release",evidence:"Evidence",ack:"Ack",alert:"Alert"};
const VIEWS=["messages","threads","activity","tasks","agents","render"];
const desktop=matchMedia("(min-width:1100px)"), touch=matchMedia("(hover:none)");
let state=null, selectedAgent="", records=new Map(), expanded=new Set(), deliveryOpen=new Set(), logShown=12;
let loading=false, requestNumber=0, controller=null, historyComplete=false, sending=false, failed=false;
let feedSignature="", agentsSignature="", scheduleSignature="", contextSignature="";
let draftKey=null, draftBody="", draftTopic="", draftRecipient="*", recipientSignature="";
let stickToBottom=true, prepending=false, lastSeenId=0, newestShown=0, statusTimer=0, feedPainted=false;
// Automatic notices (the render schedule's watcher, and the like) stay out of the stream unless Settings shows them;
// the render floor has the schedule itself. A new key, so an earlier "shown" from when they showed by default lapses.
let showSystem=false, uploads=[], thread=null;
try { showSystem=localStorage.getItem("atelier.board.system-notices")==="shown"; } catch {}
$("showSystem").checked=showSystem;

// The app shell follows the visual viewport so the composer stays above the on-screen keyboard.
let fullHeight=0, viewportWidth=0, keyboardOpen=false, inboxKeyboard=null, inboxRestore=null;
function fitViewport() {
  const vv=window.visualViewport, root=document.documentElement.style, height=vv?vv.height:innerHeight;
  root.setProperty("--app-height",`${height}px`);root.setProperty("--app-top",`${vv?vv.offsetTop:0}px`);
  if(innerWidth!==viewportWidth){viewportWidth=innerWidth;fullHeight=height;}
  fullHeight=Math.max(fullHeight,height);
  // A keyboard dismissed without leaving the field (Android back, iOS "Done") should bring the tab bar back.
  const open=fullHeight-height>120;
  if(keyboardOpen&&!open&&touch.matches&&document.activeElement===$("message"))$("message").blur();
  keyboardOpen=open;
  inboxKeyboardFit();
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
    $("message").value=draft.body||"";
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
  linkMentions(container);
}
// @name of an agent on the board becomes a tappable mention that opens your conversation with them.
function linkMentions(container) {
  const names=new Set((state?.agents||[]).map(a=>a.agent));if(!names.size)return;
  const walker=document.createTreeWalker(container,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.parentElement.closest("code, pre, a, button")?NodeFilter.FILTER_REJECT:n.nodeValue.includes("@")?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_SKIP});
  const texts=[];while(walker.nextNode())texts.push(walker.currentNode);
  for(const text of texts){
    const parts=[];let last=0;
    for(const m of text.nodeValue.matchAll(MENTION)){
      const name=trimMention(m[2]);if(!names.has(name))continue;
      const at=m.index+m[1].length;parts.push(document.createTextNode(text.nodeValue.slice(last,at)));
      const b=node("button","mention","@"+name);b.type="button";b.addEventListener("click",event=>{event.stopPropagation();openAgent(name);});
      parts.push(b);last=at+1+name.length;
    }
    if(parts.length){parts.push(document.createTextNode(text.nodeValue.slice(last)));text.replaceWith(...parts);}
  }
}
// Ledger text is plain; only `code` spans are styled, everything else stays text.
function inline(text) { const span=node("span"); text.split("`").forEach((part,i)=>span.append(i%2?node("code","",part):document.createTextNode(part))); return span; }
function hue(name) { let h=0; for(const c of name)h=(h*31+c.charCodeAt(0))%360; return h; }
function initials(name) { return name.replace(/[^a-z0-9]/gi," ").trim().split(/\s+/).slice(0,2).map(w=>w[0]).join("").toUpperCase()||"?"; }
function statusOf(agent) { return !agent?"":agent.delivery_error?"error":agent.listening?"live":"idle"; }
// Waiting on the operator: the agent has an open operator task.
function isWaiting(agent) { return !!agent&&(state?.tasks||[]).some(t=>t.agent===agent.agent&&!dismissedTasks.has(t.id)); }
// Free for work: listening, not waiting on the operator, and either with no current task (its status line empty or
// exactly "idle") or with its own session quiet for QUIET seconds, whatever the line says. A busy session is never free.
const QUIET=600;
function idleLine(agent) { return /^(idle)?$/i.test((agent?.task||"").trim()); }
function quietFor(agent) { return agent?.session==="idle"&&agent.session_since?Math.max(0,(state?.time??Date.now()/1000)-agent.session_since):0; }
function isFree(agent) {
  if(!agent||agent.stop||!agent.listening||agent.delivery_error||isWaiting(agent)||agent.session==="busy")return false;
  // Render work in flight (a Holding or Waiting line, or a live lock) waits with the session idle, so quiet is not free.
  return idleLine(agent)||(!agent.engaged&&quietFor(agent)>=QUIET);
}
function orb(name, agent) {
  const o=node("span","orb");
  if(name==="*"||!name){o.classList.add("everyone");o.append(icon("agents"));return o;}
  o.textContent=initials(name).slice(0,1);o.style.setProperty("--hue",hue(name));
  if(agent&&!agent.stop){const badge=node("span","badge "+statusOf(agent)+(isFree(agent)?" free":""));badge.style.setProperty("--delay",`${(hue(name)%9)*.29}s`);o.append(badge);}
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
    const pane=$({messages:"chatPane",threads:"threadsPane",activity:"activityPane",tasks:"tasksPane",agents:"agentsPane",render:"renderPane"}[next]);
    pane.style.setProperty("--dir",to>from?1:-1);pane.classList.remove("entering");void pane.offsetWidth;pane.classList.add("entering");
    setTimeout(()=>pane.classList.remove("entering"),900);
  }
  // Coming back to the conversation lands on its latest message and keeps following new ones.
  if(next==="messages"){stickToBottom=true;requestAnimationFrame(()=>{scrollToLatest();markSeen();});}
  if(state)inboxBadges();
  if(next==="threads"&&from!==to&&animate)threadsOrder=null;
  if(next==="threads"||next==="activity"){if(inbox[next])next==="threads"?renderThreads():renderActivity();loadInbox(next);}
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
$("showSystem").addEventListener("change",()=>{showSystem=$("showSystem").checked;try{localStorage.setItem("atelier.board.system-notices",showSystem?"shown":"hidden");}catch{}feedSignature="";renderFeed();});

/* @mentions: typing @ suggests agents, and a message that mentions agents goes to exactly them (plus the agent
   whose conversation you're in). */
const MENTION=/(^|[^\w@.-])@([A-Za-z0-9][\w.-]*)/g;
const trimMention=name=>name.replace(/[.-]+$/,"");
function mentioned(text) {
  const names=new Set(liveAgents().map(a=>a.agent)), found=[];
  for(const m of text.matchAll(MENTION)){const name=trimMention(m[2]);if(names.has(name)&&!found.includes(name))found.push(name);}
  return found;
}
// Who a draft goes to: '*', one agent, or the list of agents it mentions.
// Who a thread's replies go to: the agent who started it, or the agents your opening message mentioned, plus every
// agent who has joined in the replies. A message you sent to the whole board keeps its replies there.
function threadAudience(root, replies) {
  const m=root.first, live=new Set(liveAgents().map(a=>a.agent));
  if(m.sender===state.sender&&!root.mentions&&(root.broadcast||m.recipient==="*"))return "*";
  const names=new Set(m.sender===state.sender?root.messages.map(x=>x.recipient):[m.sender]);
  for(const g of replies)for(const x of g.messages)names.add(x.sender===state.sender?x.recipient:x.sender);
  const list=[...names].filter(name=>live.has(name)&&name!==state.sender);
  return list.length===0?"*":list.length===1?list[0]:list;
}
function recipients() {
  const mentions=mentioned($("message").value), chosen=$("recipient").value;
  if(thread?.audience){const list=[...thread.audience];for(const name of mentions)if(!list.includes(name))list.push(name);return list;}
  if(!mentions.length)return chosen;
  if(chosen!=="*"&&!mentions.includes(chosen))mentions.unshift(chosen);
  return mentions.length===1?mentions[0]:mentions;
}
const describe=target=>target==="*"?"everyone":Array.isArray(target)?target.join(", "):target;
// A reply box's hint names one person and counts the rest, so it fits on a phone's single line.
const replyHint=target=>`Reply to ${Array.isArray(target)&&target.length>1?`${target[0]} +${target.length-1}`:describe(target)}…`;
function mentionQuery() {
  const box=$("message");if(document.activeElement!==box||box.selectionStart!==box.selectionEnd)return null;
  const before=box.value.slice(0,box.selectionStart), m=before.match(/(^|[^\w@.-])@([\w.-]*)$/);
  return m?{start:before.length-m[2].length-1,text:m[2].toLowerCase()}:null;
}
let mentionChoices=[], mentionIndex=0;
function renderMentions() {
  const query=mentionQuery(), menu=$("mentionMenu");
  const choices=query?liveAgents().filter(a=>a.agent.toLowerCase().includes(query.text))
    .sort((a,b)=>b.agent.toLowerCase().startsWith(query.text)-a.agent.toLowerCase().startsWith(query.text)||b.listening-a.listening||a.agent.localeCompare(b.agent)).slice(0,6):[];
  if(choices.map(a=>a.agent).join()!==mentionChoices.map(a=>a.agent).join())mentionIndex=0;
  mentionChoices=choices;menu.hidden=!choices.length;
  if(menu.hidden)return;
  menu.replaceChildren(...choices.map((a,i)=>{
    const b=node("button","mention-option");b.type="button";b.id=`mention-${i}`;b.setAttribute("role","option");b.setAttribute("aria-selected",String(i===mentionIndex));
    const text=node("span","mention-text");text.append(node("span","mention-name",a.agent),node("span","mention-task",a.task||agentStatus(a)));
    b.append(orb(a.agent,a),text);
    // Choosing keeps focus (and the phone keyboard) in the composer.
    b.addEventListener("pointerdown",event=>event.preventDefault());b.addEventListener("click",()=>pickMention(a.agent));
    return b;
  }));
  $("message").setAttribute("aria-activedescendant",`mention-${mentionIndex}`);
}
function pickMention(name) {
  const query=mentionQuery();if(!query)return;
  const box=$("message");box.setRangeText(`@${name} `,query.start,box.selectionStart,"end");
  grow();draftChanged();renderMentions();
}
function closeMentions() { $("mentionMenu").hidden=true;mentionChoices=[];$("message").removeAttribute("aria-activedescendant"); }
for(const type of ["input","click","keyup"])$("message").addEventListener(type,event=>{if(!(type==="keyup"&&["ArrowDown","ArrowUp","Enter","Tab","Escape"].includes(event.key)))renderMentions();});
$("message").addEventListener("blur",()=>setTimeout(()=>{if(document.activeElement!==$("message"))closeMentions();},150));

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
// The operator's messages are always requests: agents treat them as actionable, so there is no type to pick.
function draftChanged() { if($("message").value!==draftBody || $("recipient").value!==draftRecipient)draftKey=null;draftRecipient=$("recipient").value;persistDraft();formState(); }
function grow() { const box=$("message"); box.style.height="auto"; box.style.height=`${box.scrollHeight}px`; }
function syncPills() {
  document.querySelectorAll(".select-pill").forEach(pill=>{const option=pill.querySelector("select").selectedOptions[0];pill.querySelector(".pill-value").textContent=option?option.textContent.replace(/ · .*/,""):"";});
  // Mentions decide who a message goes to; the To pill says so.
  const target=state?recipients():"*", pill=$("recipient").closest(".select-pill"), mentioning=Array.isArray(target)||target!==$("recipient").value;
  pill.classList.toggle("mentioning",mentioning);
  if(mentioning)pill.querySelector(".pill-value").textContent=Array.isArray(target)?`${target.length} people`:target;
}
function formState() {
  syncPills();
  const target=recipients(), count=liveAgents().length, length=$("message").value.length;
  const ready=uploads.filter(u=>u.status==="done").length, busy=uploads.some(u=>u.status!=="done");
  $("characterCount").textContent=length>6000?`${length.toLocaleString()} / 8,000`:"";
  $("sendButton").setAttribute("aria-label",busy?"Waiting for uploads":target==="*"?`Send to all ${count} agents`:`Send to ${describe(target)}`);
  $("sendButton").disabled=sending||busy||!state||!count||!($("message").value.trim()||ready)||(target!=="*"&&![target].flat().every(name=>state.agents.some(a=>a.agent===name&&!a.stop)));
  $("broadcastForm").classList.toggle("has-text",Boolean(length));
  const form=$("broadcastForm"), focused=form.contains(document.activeElement);
  form.classList.toggle("expanded",Boolean(length||uploads.length||focused||thread));
  $("message").placeholder=thread?replyHint(target):target==="*"?"Message everyone, or @someone…":`Message ${describe(target)}…`;
}
$("message").addEventListener("input",()=>{grow();draftChanged();}); $("recipient").addEventListener("change",draftChanged);
$("message").addEventListener("keydown",event=>{
  if(mentionChoices.length&&!event.isComposing){
    const step={ArrowDown:1,ArrowUp:-1}[event.key];
    if(step){event.preventDefault();mentionIndex=(mentionIndex+step+mentionChoices.length)%mentionChoices.length;renderMentions();return;}
    if(event.key==="Enter"||event.key==="Tab"){event.preventDefault();pickMention(mentionChoices[mentionIndex].agent);return;}
    if(event.key==="Escape"){event.preventDefault();event.stopPropagation();closeMentions();return;}
  }
  if(event.key!=="Enter"||event.isComposing)return;
  const send=event.metaKey||event.ctrlKey||(!touch.matches&&!event.shiftKey&&!event.altKey);
  if(send&&!$("sendButton").disabled){event.preventDefault();$("broadcastForm").requestSubmit();}
});
// Keep the keyboard up when tapping send, so the button doesn't move under the finger.
$("sendButton").addEventListener("pointerdown",event=>{if(document.activeElement===$("message"))event.preventDefault();});
let blurTimer, composerTimer;
$("broadcastForm").addEventListener("focusin",()=>{clearTimeout(composerTimer);formState();});
$("broadcastForm").addEventListener("focusout",()=>{composerTimer=setTimeout(formState,180);});
// The keyboard: what you were reading before it opened is where you are once it closes. While it is up the feed is
// shorter and gets clamped at its end, which used to flip the board into following the latest message, so closing
// the keyboard jumped there. Unless you scrolled or sent meanwhile, the reading position is put back.
let keyboardReturn=null;
$("message").addEventListener("focus",()=>{
  clearTimeout(blurTimer);
  if(touch.matches){$("app").classList.add("typing");if(!keyboardReturn)keyboardReturn={top:$("feed").scrollTop,stick:stickToBottom,moved:false,sent:false};}
  if(stickToBottom)setTimeout(scrollToLatest,250);
});
$("message").addEventListener("blur",()=>{
  blurTimer=setTimeout(()=>$("app").classList.remove("typing"),120);
  const saved=keyboardReturn;keyboardReturn=null;
  if(!saved||saved.moved||saved.sent)return;
  // Twice: once the keyboard has mostly gone, and again after its animation and the viewport have settled.
  for(const ms of [350,750])setTimeout(()=>{
    if(document.activeElement===$("message"))return;
    settle(250);stickToBottom=saved.stick;
    if(saved.stick)scrollToLatest();else $("feed").scrollTop=saved.top;
  },ms);
});
$("feed").addEventListener("touchmove",()=>{if(keyboardReturn)keyboardReturn.moved=true;},{passive:true});
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
    else {const a=node("a","att-file");a.href=f.url;a.target="_blank";a.rel="noopener noreferrer";
      if(f.readable)a.addEventListener("click",event=>{if(event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;event.preventDefault();openReader(f);});const text=node("span");text.append(node("b","",f.name),node("small","",`${sizeText(f.size)} · ${(f.name.split(".").pop()||"file").toUpperCase()}`));a.append(icon("file"),text);wrap.append(a);}
  }
  return wrap;
}
function openLightbox(f) { $("lightboxImage").src=f.url;$("lightboxImage").alt=f.name;$("lightboxName").textContent=f.name;$("lightboxOpen").href=f.url;$("lightbox").hidden=false;$("lightboxClose").focus(); }
function closeLightbox() { $("lightbox").hidden=true;$("lightboxImage").removeAttribute("src"); }
$("lightbox").addEventListener("click",event=>{if(event.target!==$("lightboxOpen"))closeLightbox();});
// Markdown and text attachments open in a reader over the board (rendered by the server) instead of downloading.
// While it is open the meadow behind it rests.
let readerFor=null, readerReturn=null, readerBehind=[];
// While the reader is open the rest of the board is inert, so Tab and screen readers stay inside it.
function holdBoard(held) {
  if(held){readerBehind=[...$("app").children].filter(el=>el!==$("reader")&&!el.inert);for(const el of readerBehind)el.inert=true;}
  else{for(const el of readerBehind)el.inert=false;readerBehind=[];}
}
async function openReader(f) {
  readerFor=f.id;readerReturn=document.activeElement;
  $("readerTitle").textContent=f.name;$("readerOpen").href=f.url;$("readerOpen").download=f.name;
  $("readerBody").replaceChildren(node("p","quiet","Opening…"));$("readerBody").scrollTop=0;
  $("reader").hidden=false;$("app").classList.add("reader-open");holdBoard(true);$("readerClose").focus();
  try {
    const response=await fetch(`/api/document/${f.id}`);const result=await response.json();
    if(!response.ok)throw Error(result.error||"This file could not be opened.");
    if(readerFor===f.id)markdown($("readerBody"),result.html);
  } catch(error) { if(readerFor===f.id)$("readerBody").replaceChildren(node("p","quiet",error.message||"This file could not be opened.")); }
}
function closeReader() { readerFor=null;$("reader").hidden=true;$("app").classList.remove("reader-open");holdBoard(false);$("readerBody").replaceChildren();readerReturn?.focus?.();readerReturn=null; }
$("readerClose").addEventListener("click",closeReader);
$("reader").addEventListener("click",event=>{if(event.target===$("reader"))closeReader();});
// Tab and Shift+Tab wrap around the reader's own controls and links.
$("reader").addEventListener("keydown",event=>{
  if(event.key!=="Tab")return;
  const stops=[...$("reader").querySelectorAll("a[href],button:not(:disabled),[tabindex]:not([tabindex='-1'])")].filter(el=>el.getClientRects().length);
  if(!stops.length)return;
  const first=stops[0], last=stops[stops.length-1];
  if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
  else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
});
addEventListener("keydown",event=>{if(event.key==="Escape"){if(!$("reader").hidden)closeReader();else if(!$("lightbox").hidden)closeLightbox();else if(thread)navBack();}});

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
  const agents=state.agents, signature=JSON.stringify([selectedAgent,agents.map(a=>[a.agent,a.listening,a.stop,a.pending,a.supervised,a.delivery_error,a.checkout,a.task,a.session,isFree(a),isWaiting(a),unreadFrom(a)])]);
  if(signature===agentsSignature)return; agentsSignature=signature;
  const live=liveAgents(), listening=live.filter(a=>a.listening).length, errors=live.filter(a=>a.delivery_error).length;
  const free=live.filter(isFree).length;
  $("agentsSummary").textContent=`${listening} of ${live.length} listening${free?` · ${free} idle`:""}${errors?` · ${errors} retrying delivery`:""}`;
  $("agentsBadge").hidden=!errors;$("agentsBadge").textContent=errors;
  const list=$("agents"), orbs=$("agentChips");list.replaceChildren();orbs.replaceChildren();
  let index=0;
  function row(name, agent) {
    const chosen=selectedAgent===name;
    const cell=node("div","agent-cell"), b=node("button","agent-row"+(agent?.stop?" retired":""));b.type="button";cell.setAttribute("role","listitem");if(chosen)b.setAttribute("aria-current","true");
    cell.style.setProperty("--i",index++);cell.dataset.agent=name;
    const text=node("span","agent-text"), detail=node("span","agent-detail");text.append(node("span","agent-name",name||"Everyone"));if(agent&&unreadFrom(agent))b.classList.add("unread");
    if(isFree(agent)){
      // A quiet session whose line still names work shows that line as the last thing it said it was doing.
      const line=node("span","agent-task");line.append(node("span","free-tag","Idle"),idleLine(agent)?" No task":` Last: ${agent.task}`);
      if(!idleLine(agent))line.title=`Quiet for ${Math.floor(quietFor(agent)/60)} min; its status line may be stale`;
      text.append(line);
    }
    else if(isWaiting(agent)){
      const line=node("span","agent-task");line.append(node("span","waiting-tag","Waiting on you"));
      if(!/^(idle)?$/i.test((agent.task||"").trim()))line.append(" "+agent.task);text.append(line);
    }
    else if(agent?.session==="busy"&&idleLine(agent))text.append(node("span","agent-task","Working (no status line)"));
    else if(agent?.task)text.append(node("span","agent-task",agent.task));
    if(agent){detail.append(node("span","state "+statusOf(agent),agentStatus(agent)));for(const part of [!agent.supervised&&!agent.stop?"no auto-recovery":"",agent.checkout||""].filter(Boolean))detail.append(document.createTextNode(" · "+part));}
    else detail.textContent=`Broadcasts and every conversation`;
    text.append(detail);b.append(orb(name||"*",agent),text);
    if(agent?.pending)b.append(node("span","count",`${agent.pending} queued`));
    b.append(icon("right"));b.addEventListener("click",()=>{if(!closeSwiped())openAgent(name);});cell.append(b);list.append(cell);
    if(agent){
      // Behind the row, revealed by swiping it left (or shown on hover with a mouse): take an evicted agent off the board.
      const remove=node("button","agent-remove");remove.type="button";remove.append(icon("remove"),node("span","","Remove"));
      remove.setAttribute("aria-label",`Remove ${name}`);remove.addEventListener("click",event=>{event.stopPropagation();removeAgent(name);});
      cell.prepend(remove);
    }
    if(agent?.stop)return;
    const o=node("button","orb-button");o.type="button";if(chosen)o.setAttribute("aria-current","true");
    // The orb marks new direct messages from the agent; what is still queued for it lives in the Agents list.
    const face=orb(name||"*",agent);if(agent&&unreadFrom(agent))face.append(node("span","unread-dot"));
    o.append(face,node("span","orb-name",name||"Everyone"));
    o.title=agent?`${name} · ${agentStatus(agent)}${agent.task?` · ${agent.task}`:""}`:"All conversations";o.setAttribute("aria-label",o.title);
    o.addEventListener("click",()=>openAgent(name));orbs.append(o);
  }
  row("");
  for(const agent of [...agents].sort((a,b)=>a.stop-b.stop||b.listening-a.listening||isFree(b)-isFree(a)||a.agent.localeCompare(b.agent)))row(agent.agent,agent);
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
  else if(agent){dot.classList.add(statusOf(agent));text=agentStatus(agent)+(agent.pending?` · ${agent.pending} queued`:"")+(agent.task?` · ${agent.task}`:"");}
  else {dot.classList.add(listening?"live":"idle");text=`${listening} of ${live.length} agents listening`;}
  subtitle.replaceChildren(dot,node("span","",text));
}

/* Removing an agent: swipe its row left in Agents, then confirm on an action sheet. */
let rowSwipe=null;
function closeSwiped(except) {
  let closed=false;
  document.querySelectorAll(".agent-cell.open").forEach(cell=>{if(cell!==except){cell.classList.remove("open");cell.querySelector(".agent-row").style.transform="";closed=true;}});
  return closed;
}
$("agents").addEventListener("touchstart",event=>{
  const cell=event.target.closest(".agent-cell");
  if(event.touches.length!==1||!cell?.querySelector(".agent-remove")||event.target.closest(".agent-remove"))return;
  const t=event.touches[0], row=cell.querySelector(".agent-row");
  rowSwipe={cell,row,x:t.clientX,y:t.clientY,axis:null,base:cell.classList.contains("open")?-92:0,dx:0,at:event.timeStamp};
},{passive:true});
$("agents").addEventListener("touchmove",event=>{
  if(!rowSwipe)return;
  const t=event.touches[0], dx=t.clientX-rowSwipe.x, dy=t.clientY-rowSwipe.y;
  if(!rowSwipe.axis){if(Math.hypot(dx,dy)<8)return;rowSwipe.axis=Math.abs(dx)>Math.abs(dy)?"x":"y";if(rowSwipe.axis==="y"){rowSwipe=null;return;}closeSwiped(rowSwipe.cell);rowSwipe.row.style.transition="none";}
  event.preventDefault();
  let x=rowSwipe.base+dx;if(x>0)x=0;if(x<-92)x=-92+(x+92)/3;   // resists past the button, like a native list
  rowSwipe.dx=dx;rowSwipe.row.style.transform=`translateX(${x}px)`;
},{passive:false});
function endRowSwipe() {
  const s=rowSwipe;rowSwipe=null;if(!s||s.axis!=="x")return;
  s.row.style.transition="";
  const open=s.base+s.dx<-46;s.cell.classList.toggle("open",open);s.row.style.transform=open?"translateX(-92px)":"";
}
$("agents").addEventListener("touchend",endRowSwipe);$("agents").addEventListener("touchcancel",endRowSwipe);
document.addEventListener("pointerdown",event=>{if(!event.target.closest(".agent-cell.open"))closeSwiped();},{capture:true});
function confirmSheet(title, text, action) {
  return new Promise(done=>{
    const sheet=$("sheet");$("sheetTitle").textContent=title;$("sheetText").textContent=text;$("sheetConfirm").textContent=action;
    sheet.hidden=false;requestAnimationFrame(()=>sheet.classList.add("shown"));$("sheetCancel").focus();
    const finish=answer=>{sheet.classList.remove("shown");setTimeout(()=>{sheet.hidden=true;},260);$("sheetConfirm").onclick=$("sheetCancel").onclick=sheet.onclick=null;done(answer);};
    $("sheetConfirm").onclick=()=>finish(true);$("sheetCancel").onclick=()=>finish(false);
    sheet.onclick=event=>{if(event.target===sheet)finish(false);};
  });
}
async function removeAgent(name) {
  const agent=state?.agents.find(a=>a.agent===name);
  const ok=await confirmSheet(`Remove ${name}?`,`${name} leaves the board and stops receiving messages${agent?.pending?`, including ${agent.pending} still queued`:""}. Its messages stay in the history, and it comes back if it subscribes again.`,`Remove ${name}`);
  if(!ok){closeSwiped();return;}
  try {
    const response=await fetch("/api/remove",{method:"POST",headers:{"Content-Type":"application/json","X-Board-CSRF":state.csrf},body:JSON.stringify({agent:name})});
    const result=await response.json();if(!response.ok)throw Error(result.error||"Could not remove the agent.");
    const cell=document.querySelector(`.agent-cell[data-agent="${CSS.escape(name)}"]`);
    if(cell){cell.style.height=`${cell.offsetHeight}px`;cell.classList.add("leaving");}
    if(selectedAgent===name){if(nav.at(-1)?.kind==="dm")navBack();else selectAgent("");}
    setTimeout(()=>{agentsSignature="";recipientSignature="";load();},280);
  } catch(error) { closeSwiped();$("errorBanner").textContent=error.message;$("errorBanner").hidden=false; }
}

/* Feed: oldest at the top, newest by the composer, like a chat. */
function feedNearBottom() { const f=$("feed"); return f.scrollHeight-f.scrollTop-f.clientHeight<96; }
function scrollToLatest(smooth=false) { $("app").classList.remove("reading","hide-top"); const f=$("feed"); f.scrollTo({top:f.scrollHeight,behavior:smooth?"smooth":"auto"}); stickToBottom=true; markSeen(); }
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
let settleUntil=0, lastScrollTop=0, scrollTravel=0;
function settle(ms=500) { settleUntil=performance.now()+ms; }
// Parallax: as you scroll back through history the meadow follows at a fraction of the speed, up to 44 px.
let parallaxFrame=0;
function parallax() {
  if(parallaxFrame||motion.matches||desktop.matches)return;
  parallaxFrame=requestAnimationFrame(()=>{
    parallaxFrame=0;const f=$("feed"), gap=Math.max(0,f.scrollHeight-f.scrollTop-f.clientHeight);
    $("painting").style.transform=`translate3d(0,${Math.min(44,gap*.035).toFixed(1)}px,0)`;
  });
}
$("feed").addEventListener("scroll",()=>{
  parallax();
  if(performance.now()<settleUntil){if(stickToBottom)$("feed").scrollTop=$("feed").scrollHeight;return;}
  stickToBottom=feedNearBottom();
  const f=$("feed"), gap=f.scrollHeight-f.scrollTop-f.clientHeight, app=$("app");
  if(gap>320)app.classList.add("reading");else if(gap<60)app.classList.remove("reading");
  // The top bar slides away while you scroll back through history and returns as you scroll down, like Safari's.
  const delta=f.scrollTop-lastScrollTop;lastScrollTop=f.scrollTop;
  scrollTravel=Math.sign(delta)===Math.sign(scrollTravel)?scrollTravel+delta:delta;
  if(gap<60||scrollTravel>36)app.classList.remove("hide-top");else if(scrollTravel<-36&&gap>160)app.classList.add("hide-top");
  if(stickToBottom)markSeen();else $("jumpLatest").hidden=false;
  if($("feed").scrollTop<120&&!historyComplete&&records.size&&!loading)loadOlder();
},{passive:true});
$("jumpLatest").addEventListener("click",()=>scrollToLatest(true));
// Opening search, a growing draft or the keyboard shrinks the feed: stay pinned to the latest message.
const pin=new ResizeObserver(()=>{$("app").style.setProperty("--dock-h",`${$("broadcastForm").offsetHeight}px`);if(stickToBottom)$("feed").scrollTop=$("feed").scrollHeight;if(thread?.stick)$("threadFeed").scrollTop=$("threadFeed").scrollHeight;});
pin.observe($("feed"));pin.observe($("broadcastForm"));pin.observe($("messages"));
// The floating agent row's height is the feed's fixed top inset (0 where the row is not shown, e.g. wide screens).
new ResizeObserver(()=>$("app").style.setProperty("--orbs-h",`${$("agentChips").offsetHeight}px`)).observe($("agentChips"));
// On a phone the top bar floats over the feed (it hides on scroll), so the feed keeps an inset of its height.
new ResizeObserver(()=>$("app").style.setProperty("--top-h",`${desktop.matches?0:$("topbar").offsetHeight}px`)).observe($("topbar"));
function loadOlder() { if(loading||!records.size)return; prepending=true; load(false,Math.min(...records.keys())); }
$("loadOlder").addEventListener("click",loadOlder);
function groupsFrom(messages) {
  const groups=new Map(), loops=new Map();
  for(const m of [...messages].sort((a,b)=>a.id-b.id)) {
    const broadcast=(m.dedup||"").match(/^web-broadcast:([a-f0-9-]+(~m)?):/);
    let key=broadcast?broadcast[1]:String(m.id), merged=false;
    // The same text sent to several agents one by one (a loop of direct posts) reads as one message to them all.
    if(!broadcast&&m.recipient!=="*"&&!isSystem(m)) {
      const same=`${m.sender}\u0000${m.topic}\u0000${m.reply_to||""}\u0000${m.body}`, open=loops.get(same);
      if(open&&m.created-open.created<15&&!open.recipients.has(m.recipient)){key=open.key;merged=true;open.recipients.add(m.recipient);}
      else loops.set(same,{key,created:m.created,recipients:new Set([m.recipient])});
    }
    if(!groups.has(key))groups.set(key,{key,broadcast:Boolean(broadcast),mentions:Boolean(broadcast?.[2]),messages:[]});
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
    meta.append(node("span","route",group.merged||group.mentions?`to ${people.length>3?`${people.length} agents`:people.join(", ")}`
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
    // Long messages start folded to about nine lines; "Read more" opens them in place. The limits match board.py's
    // PREVIEW_CHARS and PREVIEW_LINES, which warn agents whose posts would fold.
    const text=snippetless(m.body), long=text.length>500||text.split("\n").length>8, collapsed=long&&!expanded.has(group.key);
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
  s.left=s.top.getBoundingClientRect().left;s.width=s.top.offsetWidth;
  s.boxes=s.under.map(n=>{const r=n.getBoundingClientRect();return {left:r.left,right:r.right};});
  return s;
}
// p is how far the top screen has gone: 0 covers everything, 1 is off to the right. The screen underneath and the dim
// are clipped to the strip the top screen has not yet covered: a see-through screen (over the scenery) then never
// shows the one beneath it, and nothing changes in the frame where the move ends and that screen is hidden. They move
// by `translate`, which adds to their own transform (the top bar tucked away while scrolling) instead of replacing it.
const strip=(right,cut)=>`polygon(-200px -200px, ${right-cut}px -200px, ${right-cut}px calc(100% + 200px), -200px calc(100% + 200px))`;
function frame(s,p) {
  const edge=s.left+p*s.width, shift=-(1-p)*PARALLAX*s.width;
  return {top:{transform:`translate3d(${p*s.width}px,0,0)`},
    under:s.boxes.map(b=>({translate:`${shift}px 0`,clipPath:strip(b.right-b.left,Math.min(b.right-b.left,Math.max(0,b.right+shift-edge)))})),
    scrim:{opacity:(1-p)*DIM,clipPath:strip(s.width,(1-p)*s.width)}};
}
function paint(s,p) {
  const f=frame(s,p); s.top.style.transform=f.top.transform;
  s.under.forEach((n,i)=>{n.style.translate=f.under[i].translate;n.style.clipPath=f.under[i].clipPath;});
  s.scrim.style.opacity=f.scrim.opacity;s.scrim.style.clipPath=f.scrim.clipPath;
}
// Only this scene's layers take part: a conversation's still copy stays hidden while a thread moves over it.
function begin(s) { $("app").classList.add("navigating");s.top.classList.add("nav-top");for(const n of s.under)n.classList.add("nav-under");s.scrim.hidden=false; }
function end(s) {
  $("app").classList.remove("navigating");s.top.classList.remove("nav-top");for(const n of s.under)n.classList.remove("nav-under");s.scrim.hidden=true;
  for(const n of [s.top,...s.under,s.scrim])n.style.transform=n.style.translate=n.style.opacity=n.style.clipPath="";
}
function glide(s,from,to,velocity=0) {
  const {easing,duration}=motion.matches?{easing:"linear",duration:1}:spring(velocity), a=frame(s,from), b=frame(s,to);
  paint(s,to);
  const runs=[s.top.animate([a.top,b.top],{duration,easing}),...s.under.map((n,i)=>n.animate([a.under[i],b.under[i]],{duration,easing})),s.scrim.animate([a.scrim,b.scrim],{duration,easing})];
  // Settle on time even if the browser never reports an animation finished, so nothing stays mid-transition.
  moving=Promise.race([Promise.all(runs.map(r=>r.finished.catch(()=>{}))),new Promise(done=>setTimeout(done,duration+250))])
    .then(()=>{for(const r of runs)r.cancel();moving=null;});
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
  const animate=!instant&&!motion.matches&&!desktop.matches&&!(entry.kind==="thread"&&thread?.origin);
  let s=given;
  if(animate){if(!s){if(moving)return;s=scene(entry);begin(s);}await glide(s,from,1,velocity);}
  if(entry.kind==="thread"){
    closeThread();if(s)end(s);
    else if(desktop.matches&&!instant&&!motion.matches)enter([$("topbar"),$("feed")],"view-in");
    return;
  }
  const underlay=entry.underlay;entry.underlay=null;
  selectAgent("","dm",entry.from,false);
  // The live pane stays off to the right, behind the still copy, until the full conversation has painted again.
  if(entry.from==="messages"&&s)await waitFor(()=>feedPainted,1200);
  if(s)end(s);underlay?.remove();
}

// A short entrance (on a wide screen, instead of a slide); the class goes once its own animation has played.
function enter(nodes, name) {
  for(const n of nodes){
    n.classList.remove(name);void n.offsetWidth;n.classList.add(name);
    const done=event=>{if(event.target!==n)return;n.classList.remove(name);n.removeEventListener("animationend",done);};
    n.addEventListener("animationend",done);
  }
}

/* Thread view: the original and every reply, with the composer replying in the thread. */
// `origin` is the Threads or Activity view it was opened from, which closing it returns to.
async function openThread(id, focus=false, origin="") {
  const nested=!!thread;
  thread={id,data:null,signature:"",newest:Infinity,stick:true,savedRecipient:nested?thread.savedRecipient:$("recipient").value,origin:nested?thread.origin:origin};
  $("threadView").hidden=false;$("app").classList.add("in-thread");
  $("threadTitle").textContent="Thread";$("threadSubtitle").textContent="Loading…";$("threadFeed").replaceChildren();
  const loaded=loadThread();
  if(!nested){
    const entry={kind:"thread"};navPush(entry);
    // A wide screen opens the thread in place over the conversation, which steps out of sight; a phone pushes it.
    // From Threads or Activity it fades in the same way, since the conversation beneath is not what it came from.
    if(desktop.matches||thread.origin){if(!motion.matches)enter([$("threadView")],"thread-in");}
    else if(!motion.matches&&!moving){
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
  const saved=thread.savedRecipient, origin=thread.origin;thread=null;navForget("thread");
  $("threadView").hidden=true;$("app").classList.remove("in-thread");
  if([...$("recipient").options].some(o=>o.value===saved&&!o.disabled)&&$("recipient").value!==saved){$("recipient").value=saved;draftChanged();}
  formState();
  stickToBottom=true;requestAnimationFrame(()=>scrollToLatest());
  if(origin&&$("app").dataset.view==="messages")setView(origin,false);
}
$("threadBack").addEventListener("click",()=>navBack());
// Swipe back: from the left edge, or (as on iOS 26) a rightward drag anywhere that isn't on something that scrolls
// sideways or takes text. A mostly vertical drag stays a scroll.
let swipe=null;
$("chatPane").addEventListener("touchstart",event=>{
  const entry=nav.at(-1);
  if(event.touches.length!==1||!entry||moving||desktop.matches||(entry.kind==="dm"&&!entry.underlay)||(entry.kind==="thread"&&thread?.origin))return;
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
  const m=root.first, target=threadAudience(root,replies);
  // Several agents: the thread keeps them all as its audience, so a reply never falls back to everyone.
  current.audience=Array.isArray(target)?target:null;
  const usable=typeof target==="string"&&[...$("recipient").options].some(o=>o.value===target&&!o.disabled);
  if(usable&&$("recipient").value!==target&&!current.recipientSet){$("recipient").value=target;draftChanged();}
  current.recipientSet=true;current.replyTo=m.id;
  formState();
  // Seeing a thread reads it (on the board, so Threads and Activity agree everywhere), up to what was shown.
  const shown=Math.max(m.id,newest);
  if(shown>(current.readThrough||0)&&!document.hidden){current.readThrough=shown;postJSON("/api/read",{id:m.id,through:shown}).then(()=>{if(thread===current)load();}).catch(()=>{});}
}
$("threadFeed").addEventListener("scroll",()=>{if(thread){const f=$("threadFeed");thread.stick=f.scrollHeight-f.scrollTop-f.clientHeight<96;}},{passive:true});

/* Threads and Activity, as in Slack. Threads lists every conversation with replies that you started, joined, or were
   addressed or @mentioned in: unread ones first, then newest reply first, each with its latest replies and a reply box.
   Activity is everything that involves you, newest first. Read state is kept by the board, so devices agree. */
const inbox={threads:null,activity:null,threadLimit:30,activityLimit:60,kind:"",unreadOnly:false,loading:{},signature:{}};
const threadCards=new Map();
const inboxView=()=>["threads","activity"].includes($("app").dataset.view)?$("app").dataset.view:"";
async function loadInbox(view=inboxView()) {
  if(!view||inbox.loading[view]||!state)return;
  inbox.loading[view]=true;
  const q=view==="threads"?`limit=${inbox.threadLimit}`:`limit=${inbox.activityLimit}${inbox.kind?`&kind=${inbox.kind}`:""}${inbox.unreadOnly?"&unread=1":""}`;
  try {
    const response=await fetch(`/api/${view}?${q}`,{cache:"no-store"}), result=await response.json();
    if(!response.ok)throw Error(result.error||"Could not load.");
    inbox[view]=result;view==="threads"?renderThreads():renderActivity();
  } catch(error) { $(`${view}Summary`).textContent=error instanceof TypeError?"Reconnecting…":error.message; }
  finally { inbox.loading[view]=false; }
}
async function markInboxRead(body) {
  try { await postJSON("/api/read",body); } catch {}
  load();loadInbox();
}
function inboxBadges() {
  const counts=state?.inbox||{threads:0,activity:0};
  for(const [id,n] of [["threadsBadge",counts.threads],["activityBadge",counts.activity],["threadsCount",counts.threads],["activityCount",counts.activity]]){
    $(id).hidden=!n;$(id).textContent=n>99?"99+":n;
  }
  document.querySelectorAll(".inbox-link").forEach(b=>{if(b.dataset.view===$("app").dataset.view)b.setAttribute("aria-current","page");else b.removeAttribute("aria-current");});
}
// Who your reply goes to: as in the thread view, the agents in the conversation still on the board, else everyone.
function replyTarget(audience, text) {
  const live=new Set(liveAgents().map(a=>a.agent));
  let target=audience==="*"?"*":audience.filter(name=>live.has(name)&&name!==state.sender);
  const extra=mentioned(text);
  if(target==="*")return extra.length?(extra.length===1?extra[0]:extra):"*";
  for(const name of extra)if(!target.includes(name))target.push(name);
  return target.length===0?"*":target.length===1?target[0]:target;
}
function who(name) { return name===state.sender?"You":name; }
function people(names) {
  const list=[...new Set(names.map(who))];
  return list.length<=3?list.join(", "):`${list.slice(0,2).join(", ")} and ${list.length-2} others`;
}
// A reply box that keeps its draft and request id across refreshes, like the Tasks page's.
function replyBox(label, send) {
  const form=node("form","task-reply inbox-reply"), box=node("textarea"), button=node("button","send-button"), status=node("p","task-status");
  box.rows=1;box.maxLength=8000;box.setAttribute("aria-label",label);
  button.type="submit";button.disabled=true;button.setAttribute("aria-label","Send reply");button.append(icon("send"));
  status.setAttribute("role","status");form.append(box,button);
  const entry={form,box,status,key:null,sending:false};
  const grow=()=>{box.style.height="auto";box.style.height=`${box.scrollHeight}px`;};
  box.addEventListener("input",()=>{entry.key=null;button.disabled=!box.value.trim()||entry.sending;grow();});
  box.addEventListener("keydown",event=>{if(event.key==="Enter"&&!event.shiftKey&&!touch.matches&&!event.isComposing){event.preventDefault();form.requestSubmit();}});
  form.addEventListener("submit",async event=>{
    event.preventDefault();const text=box.value.trim();if(!text||entry.sending)return;
    entry.key??=crypto.randomUUID();entry.sending=true;button.disabled=true;status.textContent="Sending…";status.classList.remove("error");
    try { const target=await send(text,entry.key);box.value="";entry.key=null;grow();status.textContent=`Sent to ${describe(target)}.`;load();loadInbox(); }
    catch(error) { status.textContent=error.message;status.classList.add("error"); }
    finally { entry.sending=false;button.disabled=!box.value.trim(); }
  });
  return entry;
}
function sendReply(audience, replyTo) {
  return async(text,key)=>{
    const target=replyTarget(audience,text);
    await postJSON("/api/send",{body:text,topic:"info",recipient:target,request_id:key,reply_to:replyTo});
    return target;
  };
}
const inboxExpanded=new Set();
function openFromInbox(id, focus=false) { const from=inboxView();setView("messages",false);openThread(id,focus,from); }
function inboxMessage(m, cls="") {
  const row=node("div","inbox-message"+(m.unread?" unread":"")+(cls?" "+cls:""));
  const head=node("div","inbox-meta"), time=node("time","time",since(m.created));
  time.dateTime=new Date(m.created*1000).toISOString();time.title=`${new Date(m.created*1000).toLocaleString()} · #${m.id}`;
  head.append(node("b","",who(m.sender)));
  if(m.topic!=="info")head.append(node("span","topic "+m.topic,names[m.topic]||m.topic));
  head.append(time);
  // Long messages fold as in the chat, with the same Read more, and stay open across refreshes.
  const text=snippetless(m.body), long=text.length>500||text.split("\n").length>8;
  const body=node("div","body"+(long&&!inboxExpanded.has(m.id)?" collapsed":""));markdown(body,m.body_html,m.body);
  const column=node("div","inbox-column");column.append(head,body);
  if(long){const more=node("button","more",inboxExpanded.has(m.id)?"Show less":"Read more");more.type="button";
    more.addEventListener("click",()=>{const folded=body.classList.toggle("collapsed");folded?inboxExpanded.delete(m.id):inboxExpanded.add(m.id);more.textContent=folded?"Read more":"Show less";});
    column.append(more);}
  if(m.attachments?.length)column.append(attachmentNodes(m.attachments));
  row.append(orb(m.sender===state.sender?"you":m.sender,state.agents.find(a=>a.agent===m.sender)),column);
  return row;
}
function threadCard(t) {
  const card=node("article","card inbox-thread"), head=node("header","inbox-thread-head"), title=node("div","inbox-thread-title");
  card.setAttribute("role","listitem");card.dataset.key=t.id;
  const reply=replyBox("Reply in thread",sendReply(t.reply_audience,t.id));
  const entry={card,reply,signature:""};
  const open=node("button","text-button","Open");open.type="button";open.addEventListener("click",()=>openFromInbox(t.id));
  const read=node("button","text-button","Mark read");read.type="button";
  read.addEventListener("click",()=>markInboxRead({id:entry.t.id,through:entry.t.newest}));
  const unfollow=node("button","text-button quiet-button","Unfollow");unfollow.type="button";
  unfollow.title="Hide this thread until someone @mentions you in it";
  unfollow.addEventListener("click",()=>{card.classList.add("leaving");markInboxRead({id:entry.t.id,through:entry.t.newest,follow:false});});
  const actions=node("div","inbox-actions");actions.append(read,unfollow,open);
  head.append(title,actions);
  const content=node("div","inbox-thread-body"), replies=node("div","inbox-replies");repliesFit.observe(replies);
  // On a phone a thread is one screen with no Read more: a tap on a reply opens the whole thread.
  replies.addEventListener("click",event=>{if(snapping(threadsBody)&&!event.target.closest("a,button,video,audio,summary,details"))openFromInbox(entry.t.id);});
  card.append(head,content,reply.form,reply.status);
  entry.update=t=>{
    entry.t=t;
    const signature=JSON.stringify([t.newest,t.unread,t.replies,t.root.id,t.latest.map(m=>[m.id,m.unread]),Math.floor((state.time-t.last_activity)/60)]);
    if(signature===entry.signature)return;entry.signature=signature;
    card.classList.toggle("unread",t.unread>0);read.hidden=!t.unread;
    title.replaceChildren(node("span","inbox-people",people(t.participants)));
    if(t.unread)title.append(node("span","new-pill",`${t.unread} new`));
    title.append(node("span","inbox-when",`${t.replies} ${t.replies===1?"reply":"replies"} · ${since(t.last_activity)}`));
    const nodes=[inboxMessage(t.root,"inbox-root")];
    nodes[0].addEventListener("click",event=>{if(!event.target.closest("a,button,video,audio,summary,details"))openFromInbox(t.id);});
    if(t.replies>t.latest.length){
      const more=node("button","text-button inbox-earlier",`Show ${t.replies-t.latest.length} more ${t.replies-t.latest.length===1?"reply":"replies"}`);
      more.type="button";more.addEventListener("click",()=>openFromInbox(t.id));nodes.push(more);
    }
    for(const row of replies.children)repliesFit.unobserve(row);
    replies.replaceChildren(...t.latest.map(m=>inboxMessage(m,"inbox-reply-row")));
    for(const row of replies.children)repliesFit.observe(row);
    content.replaceChildren(...nodes,replies);fitReplies(replies);
    const target=replyTarget(t.reply_audience,"");
    reply.box.placeholder=replyHint(target);
  };
  return entry;
}
/* New threads and replies never shove what you are reading. Scrolled down, the item you are on stays exactly where it
   is while others arrive or move above it, and a pill says how many; at the top, they slide in and the rest glide
   down to make room. */
const unseenAbove=new Map();
function paneEdge(pane) { return pane.getBoundingClientRect().top+(parseFloat(getComputedStyle(pane).scrollPaddingTop)||parseFloat(getComputedStyle(pane).paddingTop)||0); }
function steadyRender(list, nodes, release=false) {
  const pane=list.closest(".pane-body"), edge=paneEdge(pane), keyed=[...list.children].filter(n=>n.dataset.key);
  const before=new Map(keyed.map(n=>[n.dataset.key,n.getBoundingClientRect().top]));
  const snap=snapping(pane), atTop=release||!snap&&pane.scrollTop<24&&!pane.contains(document.activeElement);
  const anchor=snap&&snapCard?.isConnected&&list.contains(snapCard)?snapCard:keyed.find(n=>n.getBoundingClientRect().bottom>edge+1);
  const anchorTop=anchor?.getBoundingClientRect().top, above=new Set(keyed.slice(0,keyed.indexOf(anchor)).map(n=>n.dataset.key));
  reconcile(list,nodes);
  // A snapping pane would otherwise snap back to the card that was first.
  if(release){pane.scrollTop=0;requestAnimationFrame(()=>{pane.scrollTop=0;});}
  if(!before.size)return;
  if(atTop){
    for(const n of nodes){
      if(!n.dataset.key)continue;
      if(!before.has(n.dataset.key)){n.classList.remove("arrive");void n.offsetWidth;n.classList.add("arrive");continue;}
      // Snap points follow transforms, so a snapping pane would be dragged along by the glide.
      const shift=before.get(n.dataset.key)-n.getBoundingClientRect().top;if(snap||Math.abs(shift)<1)continue;
      n.style.transition="none";n.style.transform=`translateY(${shift}px)`;void n.offsetWidth;
      n.style.transition="transform .45s cubic-bezier(.2, .9, .25, 1)";n.style.transform="";
      n.addEventListener("transitionend",()=>{n.style.transition="";},{once:true});
    }
    return;
  }
  const key=anchor?.dataset.key, now=key&&nodes.find(n=>n.dataset.key===key);
  if(!now)return;
  const shift=now.getBoundingClientRect().top-anchorTop;
  if(Math.abs(shift)>=1){
    pane.scrollTop+=shift;
    for(const k of [inboxKeyboard,inboxRestore])if(k?.pane===pane)k.top+=shift;
  }
  if(snap)snapCard=now;
  const unseen=unseenAbove.get(pane)||new Set();unseenAbove.set(pane,unseen);
  for(const n of nodes){if(n===now)break;if(n.dataset.key&&!above.has(n.dataset.key))unseen.add(n.dataset.key);}
  showUnseen(pane);
}
function showUnseen(pane) {
  const unseen=unseenAbove.get(pane)||new Set();unseenAbove.set(pane,unseen);
  const edge=paneEdge(pane);
  for(const key of [...unseen]){const n=pane.querySelector(`[data-key="${key}"]`);if(!n||pane.scrollTop<4||n.getBoundingClientRect().bottom>edge+1)unseen.delete(key);}
  let pill=pane.parentElement.querySelector(".inbox-new-above");
  const count=unseen.size+(pane===threadsBody?threadsHeld.size+threadsMoved.size:0);
  if(!pill&&count){
    pill=node("button","inbox-new-above");pill.type="button";pill.append(icon("up"),node("span",""));pane.after(pill);
    pill.addEventListener("click",()=>{if(pane===threadsBody)releaseThreads();else pane.scrollTo({top:0,behavior:"smooth"});});
  }
  if(!pill)return;
  pill.style.top=`${pane.offsetTop+10}px`;
  pill.lastChild.textContent=`${count} new`;pill.hidden=!count;
}
document.querySelectorAll(".inbox-pane .pane-body").forEach(pane=>pane.addEventListener("scroll",()=>{if(unseenAbove.get(pane)?.size)showUnseen(pane);},{passive:true}));

/* Phones: Threads is one thread per screen, as in a short-video feed. A swipe moves to the next thread, or back to the
   one above; a thread's latest replies sit just over its reply box, and the keyboard lifts the box with them, since
   the card shrinks to the room left rather than the list scrolling. */
const snapScreen=matchMedia("(max-width: 699px)"), threadsBody=$("threadsPane").querySelector(".pane-body");
let snapCard=null, snapHold=0, snapTimer=0, snapBlur=0;
function snapping(pane) { return snapScreen.matches&&pane===threadsBody; }
function snapTop(card) { return card.getBoundingClientRect().top-paneEdge(threadsBody)+threadsBody.scrollTop; }
function snapAlign() {
  if(!snapping(threadsBody)||!snapCard?.isConnected||$("app").dataset.view!=="threads")return;
  const top=Math.round(snapTop(snapCard));if(Math.abs(threadsBody.scrollTop-top)>=1)threadsBody.scrollTop=top;
}
// The thread you are on is where the pane rests once you stop swiping; near the end, older threads load.
threadsBody.addEventListener("scroll",()=>{
  clearTimeout(snapTimer);
  snapTimer=setTimeout(()=>{
    if(!snapping(threadsBody)||performance.now()<snapHold)return;
    const cards=[...$("threadsList").querySelectorAll(":scope > .inbox-thread")];if(!cards.length)return;
    snapCard=cards.reduce((best,card)=>Math.abs(snapTop(card)-threadsBody.scrollTop)<Math.abs(snapTop(best)-threadsBody.scrollTop)?card:best);
    if(cards.indexOf(snapCard)>=cards.length-3&&!$("threadsMore").hidden&&!inbox.loading.threads)$("threadsMore").click();
  },140);
},{passive:true});
// The keyboard, a growing reply or a phone turning resizes the pane: it stays on the same thread.
new ResizeObserver(snapAlign).observe(threadsBody);
// As the keyboard opens the browser may scroll toward the field, so for a moment the pane holds on to the thread.
function snapFollow(ms=900) {
  const running=performance.now()<snapHold;snapHold=performance.now()+ms;if(running)return;
  const step=()=>{snapAlign();if(performance.now()<snapHold)requestAnimationFrame(step);};requestAnimationFrame(step);
}
threadsBody.addEventListener("focusin",event=>{
  if(!touch.matches||!event.target.matches("textarea")||!snapping(threadsBody))return;
  clearTimeout(snapBlur);snapCard=event.target.closest(".inbox-thread")||snapCard;
  $("app").classList.add("typing");snapFollow();
});
threadsBody.addEventListener("focusout",()=>{
  snapBlur=setTimeout(()=>{if(!threadsBody.contains(document.activeElement)&&document.activeElement!==$("message")){$("app").classList.remove("typing");snapFollow();}},120);
});
threadsBody.addEventListener("touchmove",()=>{snapHold=0;},{passive:true});
// Replies that outgrow their card show the newest, just above the reply box, fading out at the top. The rows are
// watched too, since an image or video can grow one after it renders.
const repliesFit=new ResizeObserver(entries=>new Set(entries.map(e=>e.target.closest(".inbox-replies"))).forEach(fitReplies));
function fitReplies(box) {
  const rows=[...box.children], gap=parseFloat(getComputedStyle(box).rowGap)||0;
  const need=rows.reduce((sum,row)=>sum+row.offsetHeight,0)+gap*Math.max(0,rows.length-1);
  box.classList.toggle("overflowing",need>box.clientHeight+1);
}
// While Threads is on screen its order holds: a thread with a new reply updates where it is, and threads new to the
// list wait behind the pill, which also counts unread threads that would now move up. Coming back to the view, or
// tapping the pill, brings the current order.
let threadsOrder=null;
const threadsHeld=new Set(), threadsMoved=new Set();
function releaseThreads() { snapCard=null;threadsBody.scrollTop=0;renderThreads(true); }
function renderThreads(release=false) {
  const data=inbox.threads;if(!data||!state)return;
  $("threadsSummary").textContent=data.total?`${data.unread?`${data.unread} with new replies · `:""}${data.total} ${data.total===1?"thread":"threads"} you're part of`:"No threads yet";
  $("threadsAllRead").hidden=!data.unread;
  const keep=new Set(data.threads.map(t=>t.id));
  for(const id of [...threadCards.keys()])if(!keep.has(id))threadCards.delete(id);
  let shown=data.threads;threadsHeld.clear();threadsMoved.clear();
  if(threadsOrder&&!release){
    const byId=new Map(data.threads.map((t,i)=>[t.id,i])), kept=threadsOrder.filter(id=>byId.has(id)), last=Math.max(-1,...kept.map(id=>byId.get(id)));
    const fresh=data.threads.filter(t=>!threadsOrder.includes(t.id));
    // Older threads loaded with Show more go after the rest; newer ones are held.
    for(const t of fresh)if(byId.get(t.id)<last)threadsHeld.add(t.id);
    let latest=-1;for(const id of kept){const rank=byId.get(id);if(rank<latest&&data.threads[rank].unread)threadsMoved.add(id);latest=Math.max(latest,rank);}
    shown=[...kept.map(id=>data.threads[byId.get(id)]),...fresh.filter(t=>!threadsHeld.has(t.id))];
  }
  threadsOrder=shown.map(t=>t.id);
  const nodes=shown.map(t=>{let entry=threadCards.get(t.id);if(!entry){entry=threadCard(t);threadCards.set(t.id,entry);}entry.update(t);return entry.card;});
  if(!nodes.length){const empty=node("div","empty inbox-empty");empty.append(icon("thread"),node("h2","","No threads yet"),node("p","","When you reply to an agent, or one replies to you, the conversation shows up here."));nodes.push(empty);}
  steadyRender($("threadsList"),nodes,release);showUnseen(threadsBody);
  $("threadsMore").hidden=data.total<=data.threads.length;
}
const KIND_TEXT={mention:"Mentioned you",dm:"Direct message",ack:"Acknowledged",reply:"Replied"};
const activityRows=new Map();
function activityText(item) {
  if(item.kind==="ack")return `${people(item.senders)} acknowledged your message`;
  if(item.kind==="reply"&&item.count>1)return `${item.count} new replies from ${people(item.senders)}`;
  if(item.kind==="reply")return `${who(item.message.sender)} replied${item.message.recipient===state.sender?" to you":""} in a thread`;
  if(item.kind==="mention")return `${who(item.message.sender)} mentioned you`;
  return `${who(item.message.sender)} messaged you`;
}
function activityRow(item) {
  const row=node("article","activity-item"+(item.unread?" unread":""));row.setAttribute("role","listitem");row.dataset.key=item.id;
  const main=node("button","activity-main");main.type="button";
  const face=orb(item.message.sender===state.sender?"you":item.message.sender,state.agents.find(a=>a.agent===item.message.sender));
  const text=node("span","activity-text"), line=node("span","activity-line");
  line.append(node("span","kind-tag "+item.kind,KIND_TEXT[item.kind]),node("span","inbox-when",since(item.created)));
  text.append(line,node("span","activity-summary",activityText(item)));
  const quoted=item.kind==="ack"?item.target:item.message;
  if(quoted)text.append(node("span","activity-snippet",quoted.snippet||""));
  if(item.root&&item.kind!=="ack")text.append(node("span","activity-context",`in thread: ${who(item.root.sender)}: ${item.root.snippet}`));
  main.append(face,text);
  main.addEventListener("click",()=>{if(item.unread)postJSON("/api/read",{id:item.id,through:item.id}).catch(()=>{});openFromInbox(item.id);});
  const actions=node("div","inbox-actions");
  if(item.unread){const read=node("button","text-button","Mark read");read.type="button";read.addEventListener("click",()=>markInboxRead({id:item.id,through:item.id}));actions.append(read);}
  if(item.kind!=="ack"){
    const replyButton=node("button","text-button","Reply");replyButton.type="button";actions.append(replyButton);
    let box=null;
    replyButton.addEventListener("click",()=>{
      if(!box){box=replyBox(`Reply to ${item.message.sender}`,sendReply(item.reply_audience,item.id));box.box.placeholder=replyHint(replyTarget(item.reply_audience,""));row.append(box.form,box.status);}
      box.box.focus();
    });
  }
  row.append(main,actions);return row;
}
function renderActivity() {
  const data=inbox.activity;if(!data||!state)return;
  const n=data.unread.all;
  $("activitySummary").textContent=n?`${n} unread`:"You're all caught up";
  $("activityAllRead").hidden=!n&&!data.unread.ack;
  document.querySelectorAll("#activityKinds button").forEach(b=>{
    b.setAttribute("aria-pressed",String(b.dataset.kind===inbox.kind));
    const count=b.dataset.kind?data.unread[b.dataset.kind]:0;b.dataset.count=count&&b.dataset.kind!=="ack"?count:"";
  });
  const signature=JSON.stringify([data.items.map(i=>[i.id,i.unread,i.count]),inbox.kind,inbox.unreadOnly,Math.floor(state.time/60)]);
  if(signature===inbox.signature.activity)return;inbox.signature.activity=signature;
  // A row with a reply being typed keeps its node.
  const nodes=data.items.map(item=>{
    const key=`${item.kind}:${item.id}:${item.unread}:${item.count}`, cached=activityRows.get(item.id);
    if(cached&&(cached.key===key||cached.node.querySelector("textarea")?.value))return cached.node;
    const built=activityRow(item);activityRows.set(item.id,{key,node:built});return built;
  });
  for(const id of [...activityRows.keys()])if(!data.items.some(i=>i.id===id))activityRows.delete(id);
  if(!nodes.length){const empty=node("div","empty inbox-empty");empty.append(icon("activity"),node("h2","",inbox.unreadOnly?"Nothing unread":"No activity yet"),node("p","","Mentions, replies to you and direct messages land here."));nodes.push(empty);}
  steadyRender($("activityList"),nodes);
  $("activityMore").hidden=data.total<=data.items.length;
}
$("threadsMore").addEventListener("click",()=>{inbox.threadLimit=Math.min(200,inbox.threadLimit+30);loadInbox("threads");});
$("activityMore").addEventListener("click",()=>{inbox.activityLimit=Math.min(300,inbox.activityLimit+60);loadInbox("activity");});
$("threadsAllRead").addEventListener("click",()=>markInboxRead({all:true}));
$("activityAllRead").addEventListener("click",()=>markInboxRead({all:true}));
document.querySelectorAll("#activityKinds button").forEach(b=>b.addEventListener("click",()=>{inbox.kind=b.dataset.kind;inbox.activityLimit=60;renderActivity();loadInbox("activity");}));
$("activityUnread").addEventListener("change",()=>{inbox.unreadOnly=$("activityUnread").checked;loadInbox("activity");});
document.querySelectorAll(".inbox-link").forEach(b=>b.addEventListener("click",()=>{if(thread)closeThread();setView(b.dataset.view);}));

// The phone keyboard in Threads and Activity: what you were looking at moves up by the keyboard's height, and once the
// keyboard has gone the pane is exactly where it was, unless you scrolled meanwhile.
let inboxTouchTop=null;
function inboxKeyboardFit() {
  const k=inboxKeyboard;if(!k)return;
  const shrink=Math.max(0,k.height-k.pane.clientHeight);
  if(shrink>120)k.opened=true;
  // Dismissed without leaving the field (Android back): leave it, as the chat composer does.
  else if(k.opened&&shrink<40){inboxKeyboardEnd();k.field.blur();return;}
  if(k.moved)return;
  // Room below for the push, then up by the keyboard, but never so far that the field being typed in leaves the top.
  // Only real changes are written: rewriting an unchanged scroll position makes phones repaint the list mid-animation.
  const padding=`${k.base+shrink}px`;if(k.pane.style.paddingBottom!==padding)k.pane.style.paddingBottom=padding;
  const field=k.field.getBoundingClientRect().top-k.pane.getBoundingClientRect().top+k.pane.scrollTop;
  const top=Math.round(k.top+Math.max(0,Math.min(shrink,field-k.top-8)));
  if(Math.abs(k.pane.scrollTop-top)>=1)k.pane.scrollTop=top;
}
function inboxKeyboardEnd() {
  const k=inboxKeyboard;inboxKeyboard=null;if(!k)return;
  k.pane.style.paddingBottom="";
  if(k.moved)return;
  // Again once the keyboard's animation and the viewport have settled.
  inboxRestore=k;const restore=()=>{if(inboxRestore===k&&!inboxKeyboard&&Math.abs(k.pane.scrollTop-k.top)>=1)k.pane.scrollTop=k.top;};
  restore();for(const ms of [350,750])setTimeout(restore,ms);
}
document.querySelectorAll(".inbox-pane .pane-body").forEach(pane=>{
  // Where the pane was before a tap, since the browser may scroll to the field as it takes focus.
  pane.addEventListener("pointerdown",()=>{if(!inboxKeyboard)inboxTouchTop=pane.scrollTop;},{capture:true,passive:true});
  pane.addEventListener("focusin",event=>{
    if(!touch.matches||!event.target.matches("textarea")||snapping(pane))return;
    if(inboxKeyboard?.pane===pane){inboxKeyboard.field=event.target;return;}   // another reply box, same keyboard
    inboxKeyboardEnd();inboxRestore=null;
    inboxKeyboard={pane,field:event.target,top:inboxTouchTop??pane.scrollTop,height:pane.clientHeight,
      base:parseFloat(getComputedStyle(pane).paddingBottom)||0,opened:false,moved:false};
    inboxTouchTop=null;inboxKeyboardFit();
  });
  pane.addEventListener("focusout",()=>setTimeout(()=>{if(inboxKeyboard?.pane===pane&&!pane.contains(document.activeElement))inboxKeyboardEnd();},120));
  pane.addEventListener("touchmove",()=>{if(inboxKeyboard?.pane===pane)inboxKeyboard.moved=true;if(inboxRestore?.pane===pane)inboxRestore=null;},{passive:true});
});

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
/* Operator tasks: an agent blocked on the operator asks once, and the Tasks page holds the ask until someone dismisses
   it. Each card is built once and then only updated, so a reply being typed survives the board's refreshes. */
const taskCards=new Map(), dismissedTasks=new Set();
function since(timestamp) {
  const s=Math.max(0,(state?.time??Date.now()/1000)-timestamp);
  return s<60?"just now":s<3600?`${Math.floor(s/60)} min ago`:s<86400?`${Math.floor(s/3600)} h ago`:`${Math.floor(s/86400)} d ago`;
}
function taskCard(task) {
  const card=node("article","card task-card"), head=node("header","task-head"), who=node("span","task-who");
  card.setAttribute("role","listitem");
  const agent=state.agents.find(a=>a.agent===task.agent);
  who.append(node("b","",task.agent),node("span","task-age"));
  const open=node("button","text-button task-thread");open.type="button";open.append(node("span","","Thread"),icon("right"));
  open.addEventListener("click",()=>{setView("messages");openThread(task.message);});
  head.append(orb(task.agent,agent),who,open);
  const body=node("div","task-body markdown"), last=node("p","task-last");
  const form=node("form","task-reply"), box=node("textarea");box.rows=1;box.maxLength=8000;box.placeholder=`Reply to ${task.agent}…`;
  box.setAttribute("aria-label",`Reply to ${task.agent}`);
  const send=node("button","send-button");send.type="submit";send.disabled=true;send.setAttribute("aria-label","Send reply");send.append(icon("send"));
  const dismiss=node("button","text-button task-dismiss","Dismiss");dismiss.type="button";
  const status=node("p","task-status");status.setAttribute("role","status");
  form.append(box,send);card.append(head,body,last,form,status,dismiss);
  const entry={card,task,key:null,sending:false,html:null};
  const grow=()=>{box.style.height="auto";box.style.height=`${box.scrollHeight}px`;};
  box.addEventListener("input",()=>{entry.key=null;send.disabled=!box.value.trim()||entry.sending;grow();});
  box.addEventListener("keydown",event=>{if(event.key==="Enter"&&!event.shiftKey&&!touch.matches&&!event.isComposing){event.preventDefault();form.requestSubmit();}});
  form.addEventListener("submit",async event=>{
    event.preventDefault();const text=box.value.trim();if(!text||entry.sending)return;
    entry.key??=crypto.randomUUID();entry.sending=true;send.disabled=true;status.textContent="Sending…";status.classList.remove("error");
    try {
      await postJSON("/api/send",{body:text,topic:"info",recipient:entry.task.agent,request_id:entry.key,reply_to:entry.task.message});
      box.value="";entry.key=null;grow();status.textContent=`Sent to ${entry.task.agent}.`;load();
    } catch(error) {status.textContent=error.message;status.classList.add("error");}
    finally {entry.sending=false;send.disabled=!box.value.trim();}
  });
  dismiss.addEventListener("click",async()=>{
    dismiss.disabled=true;status.textContent="";
    try {
      await postJSON("/api/task/dismiss",{id:entry.task.id});
      dismissedTasks.add(entry.task.id);card.classList.add("leaving");state.tasks=state.tasks.filter(t=>t.id!==entry.task.id);renderAgents();
      setTimeout(()=>{renderTasks();load();},motion.matches?0:220);
    } catch(error) {status.textContent=error.message;status.classList.add("error");dismiss.disabled=false;}
  });
  entry.update=t=>{
    entry.task=t;card.querySelector(".task-age").textContent=` · ${since(t.asked)}${t.edited?" · edited":""}`;
    if(entry.html!==t.body_html){entry.html=t.body_html;markdown(body,t.body_html,t.body);}
    const r=t.last_reply;last.hidden=!r;
    if(r)last.textContent=`${r.sender===state.sender?"You":r.sender}: ${snippet(r.body)} · ${since(r.created)}`;
  };
  return entry;
}
function renderTasks() {
  // A snapshot already in flight when a task was dismissed must not bring its card back.
  const list=(state.tasks||[]).filter(t=>!dismissedTasks.has(t.id)), n=list.length;
  $("tasksBadge").hidden=!n;$("tasksBadge").textContent=n>99?"99+":n;
  const who=new Set(list.map(t=>t.agent)).size;
  $("tasksSummary").textContent=n?`${who} ${who===1?"agent is":"agents are"} waiting on you`:"Nobody is waiting on you";
  $("app").classList.toggle("has-tasks",n>0);
  const keep=new Set(list.map(t=>t.id));
  for(const [id,entry] of taskCards)if(!keep.has(id))taskCards.delete(id);
  const nodes=list.map(t=>{let entry=taskCards.get(t.id);if(!entry){entry=taskCard(t);taskCards.set(t.id,entry);}entry.update(t);return entry.card;});
  reconcile($("tasks"),nodes);
  $("tasksNote").hidden=n>0&&desktop.matches;
}
function render() {
  $("lastUpdated").textContent=`Live · last synced ${clock(state.time)} · updates every 3 seconds`;
  renderRecipients();formState();renderAgents();renderHeader();renderFeed();renderContext();renderSchedule();renderTasks();inboxBadges();
  if(thread)loadThread();
  if(inboxView())loadInbox();
}
let loadStarted=0;
async function load(reset=false,before=0) {
  if(loading&&!reset)return;if(reset)controller?.abort();
  const number=++requestNumber;const activeController=new AbortController();controller=activeController;loading=true;loadStarted=Date.now();
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
  const replyTo=thread?.replyTo??null, target=recipients(), abort=new AbortController(), timer=setTimeout(()=>abort.abort(),15000);
  try {
    const response=await fetch("/api/send",{method:"POST",headers:{"Content-Type":"application/json","X-Board-CSRF":state.csrf},body:JSON.stringify({body:draftBody,topic:draftTopic,recipient:target,request_id:draftKey,attachments:files,reply_to:replyTo}),signal:abort.signal});
    const result=await response.json();if(!response.ok)throw Error(result.error||"Message failed. Your draft is saved; retry safely.");
    composerStatus("");closeMentions();   // the message appearing in the feed is the confirmation
    $("message").value="";draftKey=null;draftBody="";
    for(const u of uploads)if(u.preview?.startsWith("blob:"))URL.revokeObjectURL(u.preview);
    uploads=[];renderTray();persistDraft();grow();
    if(keyboardReturn)keyboardReturn.sent=true;   // after sending, the conversation follows your new message
    if(touch.matches)$("message").blur();   // on a phone the keyboard closes once the message is away
    if(thread){thread.stick=true;loadThread();load();}
    else {
      const before=selectedAgent, filtered=Boolean($("search").value||$("topicFilter").value);
      if(selectedAgent&&!Array.isArray(target)&&selectedAgent!==target)selectedAgent=target==="*"?"":target;
      $("search").value="";$("topicFilter").value="";syncPills();agentsSignature="";stickToBottom=true;
      if(selectedAgent!==before||filtered)refreshFilters();else load();
    }
  } catch(error) {composerStatus(error.name==="AbortError"?"The connection timed out. Your draft is saved; tap send to finish this same message.":error.message,true);}
  finally {clearTimeout(timer);sending=false;$("broadcastForm").classList.remove("sending");formState();}
});
desktop.addEventListener("change",()=>{feedSignature="";if(state)renderFeed();});
/* Notifications: an agent flags a message with board post --notify-operator, this device gets it as a push, and
   tapping it opens that message's thread. */
const pushSupported="serviceWorker" in navigator&&"PushManager" in window&&"Notification" in window;
let pushRegistration=null;
const notifyNote=text=>{$("notifyNote").textContent=text;};
function unb64(text) { const raw=atob(text.replace(/-/g,"+").replace(/_/g,"/")+"=".repeat((4-text.length%4)%4)); return Uint8Array.from(raw,c=>c.charCodeAt(0)); }
async function postJSON(path, body) {
  const response=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json","X-Board-CSRF":state.csrf},body:JSON.stringify(body)});
  const result=await response.json();if(!response.ok)throw Error(result.error||"Something went wrong. Try again.");return result;
}
async function setupPush() {
  if(!pushSupported){
    notifyNote(/iPhone|iPad/.test(navigator.userAgent)&&!standalone?"To get notifications, add the board to your Home Screen (Share, then Add to Home Screen) and open it from there.":"This browser can't show notifications.");
    return;
  }
  try { pushRegistration=await navigator.serviceWorker.register("/sw.js"); } catch { notifyNote("Notifications aren't available here.");return; }
  const subscription=await pushRegistration.pushManager.getSubscription(), on=Boolean(subscription)&&Notification.permission==="granted";
  $("notifyToggle").disabled=false;$("notifyToggle").checked=on;$("notifyTest").hidden=!on;
  // Re-register an existing subscription, in case the board lost it.
  if(on)postJSON("/api/push/subscribe",{subscription:subscription.toJSON()}).catch(()=>{});
  if(Notification.permission==="denied")notifyNote("Notifications are turned off for the board in Settings.");
}
$("notifyToggle").addEventListener("change",async()=>{
  const on=$("notifyToggle").checked;$("notifyToggle").disabled=true;
  try {
    if(on) {
      if(await Notification.requestPermission()!=="granted")throw Error("Allow notifications for the board to turn them on.");
      const {key}=await (await fetch("/api/push/key",{cache:"no-store"})).json();
      const subscription=await pushRegistration.pushManager.getSubscription()||await pushRegistration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:unb64(key)});
      await postJSON("/api/push/subscribe",{subscription:subscription.toJSON()});
      notifyNote("On. Agents notify you only when you've asked to be told, or it's urgent.");
    } else {
      const subscription=await pushRegistration.pushManager.getSubscription();
      if(subscription){await postJSON("/api/push/unsubscribe",{endpoint:subscription.endpoint});await subscription.unsubscribe();}
      notifyNote("Off. Flagged messages still appear on the board.");
    }
  } catch(error) { $("notifyToggle").checked=!on;notifyNote(error.message); }
  finally { $("notifyToggle").disabled=false;$("notifyTest").hidden=!$("notifyToggle").checked;settingsSummary(); }
});
$("notifyTest").addEventListener("click",async()=>{
  try { const result=await postJSON("/api/push/test",{});notifyNote(result.delivered?"Test sent; it should arrive in a moment.":"No device received it. Turn notifications off and on again."); }
  catch(error) { notifyNote(error.message); }
});
// Settings fold away under Agents; their row says how they are set.
const THEMES={auto:"Auto",light:"Light",dark:"Dark"};
function settingsSummary() {
  $("settingsSummary").textContent=[`Notifications ${$("notifyToggle").checked?"on":"off"}`,$("playfulToggle").checked?"Playful":"Calm",
    THEMES[window.boardTheme?.choice]||"Auto"].join(" · ");
}
function themeSwitch() {
  const choice=window.boardTheme?.choice||"auto";
  document.querySelectorAll("[data-theme-choice]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.themeChoice===choice)));
  $("themeNote").textContent=choice==="auto"?`Follows this device: ${window.boardTheme?.dark?"dark":"light"} now.`:choice==="dark"?"The meadow by moonlight.":"The misty morning meadow.";
  settingsSummary();
}
document.querySelectorAll("[data-theme-choice]").forEach(b=>b.addEventListener("click",()=>window.boardTheme?.set(b.dataset.themeChoice)));
addEventListener("boardtheme",themeSwitch);
$("settings").addEventListener("change",settingsSummary);
$("settings").addEventListener("toggle",()=>{if($("settings").open)requestAnimationFrame(()=>$("settings").scrollIntoView({block:"end",behavior:motion.matches?"instant":"smooth"}));});
themeSwitch();
// A notification links to /?m=ID, that message's thread, or /?task=ID, the Tasks page; whether the app was closed or open.
function openLink(url) {
  const params=new URL(url,location.href).searchParams;
  if(params.has("task")){setView("tasks");return;}
  const id=Number(params.get("m"));if(!(id>0))return;
  setView("messages");if(thread?.id!==id){if(thread)closeThread();openThread(id);}
}
navigator.serviceWorker?.addEventListener("message",event=>{if(event.data?.open)openLink(event.data.open);});
waitFor(()=>state,15000).then(()=>{
  if(!state)return;
  setupPush().finally(settingsSummary);
  const params=new URLSearchParams(location.search);
  if(params.has("m")||params.has("task")){openLink(location.href);history.replaceState(history.state,"","/");}
});

// iOS freezes the app in the background, and a request caught mid-flight may never settle, which used to block
// every later refresh until the app was killed. Coming back always starts over, and a request older than 15 s (by
// the wall clock, which keeps running while frozen) is abandoned.
function resume() { if(document.hidden)return; load(true); if(thread)loadThread(); }
renderTray();grow();formState();load();
setInterval(()=>{if(!document.hidden){if(loading&&Date.now()-loadStarted>15000)load(true);else load();}},3000);
document.addEventListener("visibilitychange",resume);
addEventListener("pageshow",event=>{if(event.persisted)resume();});
addEventListener("focus",resume);addEventListener("online",resume);
// A window behind others holds its looping animations where they are, as the scene does. A toggle that changes
// nothing records no mutation, which the scene's class observer relies on.
function rest() { $("app").classList.toggle("at-rest",document.hidden||!document.hasFocus()); }
addEventListener("blur",rest);addEventListener("focus",rest);document.addEventListener("visibilitychange",rest);rest();
