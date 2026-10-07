"use strict";
/* Playful motion: a comet of light carries each delivery from the speaker's orb to the feed, where the bubble unfolds
   out of their orb and its words stream in; what you send flies out of the composer; a release takes over the screen
   with fireworks. One canvas draws the particles and sleeps once none are left; everything else is CSS under
   .app.playful. The switch under Agents, or Reduce Motion, turns it all off. */
(()=>{
  const app=document.getElementById("app"), toggle=document.getElementById("playfulToggle"), note=document.getElementById("playfulNote");
  const reduce=matchMedia("(prefers-reduced-motion: reduce)"), KEY="atelier.board.playful";
  let wanted=true;
  try { wanted=localStorage.getItem(KEY)!=="off"; } catch {}
  const on=()=>wanted&&!reduce.matches;
  const rnd=(a,b)=>a+Math.random()*(b-a), pick=list=>list[Math.floor(Math.random()*list.length)];

  /* Particles: each has a position, velocity, gravity, drag and a life; it fades in fast and out over its last 30%. */
  const canvas=document.createElement("canvas");canvas.className="fx-layer";canvas.setAttribute("aria-hidden","true");document.body.append(canvas);
  const ctx=canvas.getContext("2d"), parts=[];
  let W=0, H=0, dpr=1, running=false, last=0;
  function size() { dpr=Math.min(devicePixelRatio||1,2);W=innerWidth;H=innerHeight;canvas.width=Math.round(W*dpr);canvas.height=Math.round(H*dpr); }
  size();addEventListener("resize",size);
  function add(p) {
    if(!on()||parts.length>=600)return;
    parts.push(Object.assign({age:0,r:0,vr:0,g:0,drag:.85,flip:rnd(4,9),sway:0,s:6,a:1},p));
    if(!running){running=true;last=performance.now();requestAnimationFrame(tick);}
  }
  function tick(now) {
    const dt=Math.min(.05,(now-last)/1000);last=now;
    ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,H);
    for(let i=parts.length-1;i>=0;i--){
      const p=parts[i];p.age+=dt;
      if(p.age>=p.life||!on()){parts.splice(i,1);continue;}
      if(p.move)p.move(p);
      else {const k=Math.pow(p.drag,dt*6);p.vx*=k;p.vy=p.vy*k+p.g*dt;p.x+=p.vx*dt+Math.sin(p.age*p.flip)*p.sway*dt;p.y+=p.vy*dt;p.r+=p.vr*dt;}
      const t=p.age/p.life;ctx.globalAlpha=p.a*Math.min(1,p.age/.08)*(t>.7?(1-t)/.3:1);
      DRAW[p.kind](p,t);
    }
    ctx.globalAlpha=1;
    if(parts.length)requestAnimationFrame(tick);else {running=false;ctx.clearRect(0,0,W,H);}
  }
  const DRAW={
    petal(p) {
      ctx.save();ctx.translate(p.x,p.y);ctx.rotate(p.r);ctx.scale(1,Math.cos(p.age*p.flip));
      ctx.fillStyle=p.c;ctx.beginPath();ctx.ellipse(0,0,p.s,p.s*.55,0,0,7);ctx.fill();
      ctx.fillStyle="#ffffff8c";ctx.beginPath();ctx.ellipse(-p.s*.25,-p.s*.12,p.s*.4,p.s*.18,0,0,7);ctx.fill();ctx.restore();
    },
    confetti(p) { ctx.save();ctx.translate(p.x,p.y);ctx.rotate(p.r);ctx.scale(Math.cos(p.age*p.flip),1);ctx.fillStyle=p.c;ctx.fillRect(-p.s/2,-p.s*.22,p.s,p.s*.44);ctx.restore(); },
    spark(p,t) {
      const s=p.s*(1-t*.5), k=s*.24;
      ctx.save();ctx.translate(p.x,p.y);ctx.rotate(p.r);ctx.fillStyle=p.c;ctx.beginPath();
      ctx.moveTo(0,-s);ctx.lineTo(k,-k);ctx.lineTo(s,0);ctx.lineTo(k,k);ctx.lineTo(0,s);ctx.lineTo(-k,k);ctx.lineTo(-s,0);ctx.lineTo(-k,-k);ctx.closePath();ctx.fill();ctx.restore();
    },
    ring(p,t) { ctx.strokeStyle=p.c;ctx.lineWidth=2.2*(1-t)+.4;ctx.beginPath();ctx.arc(p.x,p.y,p.s+(1-Math.pow(1-t,3))*p.grow,0,7);ctx.stroke(); },
    fluff(p) {
      ctx.save();ctx.translate(p.x,p.y);ctx.rotate(p.r);ctx.strokeStyle="#ffffffeb";ctx.lineWidth=.9;ctx.lineCap="round";ctx.beginPath();
      for(let i=0;i<9;i++){const a=-Math.PI*(.12+.76*i/8);ctx.moveTo(0,0);ctx.lineTo(Math.cos(a)*p.s,Math.sin(a)*p.s);}
      ctx.moveTo(0,0);ctx.lineTo(0,p.s*1.3);ctx.stroke();ctx.fillStyle="#d8cfa8";ctx.beginPath();ctx.arc(0,p.s*1.35,1.3,0,7);ctx.fill();ctx.restore();
    },
    // A comet's tail is a tapering line in its hue; the head a white core in a glow. Both add light.
    comet(p) {
      const n=p.trail.length;if(!n)return;
      ctx.save();ctx.globalCompositeOperation="lighter";ctx.lineCap="round";
      for(let i=1;i<n;i++){const k=i/n;ctx.strokeStyle=`hsl(${p.h} 95% ${60+k*25}% / ${k*.9})`;ctx.lineWidth=p.s*1.6*k;ctx.beginPath();ctx.moveTo(...p.trail[i-1]);ctx.lineTo(...p.trail[i]);ctx.stroke();}
      if(!p.hit){
        const g=ctx.createRadialGradient(p.x,p.y,0,p.x,p.y,p.s*4.5);g.addColorStop(0,"#ffffff");g.addColorStop(.25,`hsl(${p.h} 100% 80% / .9)`);g.addColorStop(1,`hsl(${p.h} 100% 60% / 0)`);
        ctx.fillStyle=g;ctx.beginPath();ctx.arc(p.x,p.y,p.s*4.5,0,7);ctx.fill();
      }
      ctx.restore();
    },
    ember(p,t) {
      ctx.save();ctx.globalCompositeOperation="lighter";ctx.fillStyle=p.c;
      ctx.globalAlpha*=.35;ctx.beginPath();ctx.arc(p.x,p.y,p.s*2.8,0,7);ctx.fill();
      ctx.globalAlpha/=.35;ctx.beginPath();ctx.arc(p.x,p.y,p.s*(1-t*.4),0,7);ctx.fill();ctx.restore();
    },
    plane(p) {
      const n=p.trail.length;
      ctx.save();ctx.lineCap="round";ctx.strokeStyle="#4f8fc4";ctx.lineWidth=1.6;ctx.setLineDash([2,6]);
      for(let i=1;i<n;i++){ctx.globalAlpha=p.a*.6*i/n*(p.age>1.1?Math.max(0,1-(p.age-1.1)/.4):1);ctx.beginPath();ctx.moveTo(...p.trail[i-1]);ctx.lineTo(...p.trail[i]);ctx.stroke();}
      ctx.restore();
      if(p.landed)return;
      const s=p.s;
      ctx.save();ctx.translate(p.x,p.y);ctx.rotate(p.r);ctx.scale(1,.75+.25*Math.cos(p.age*11));
      ctx.lineJoin="round";ctx.lineWidth=1.3;ctx.strokeStyle="#3f7fb4";
      ctx.fillStyle="#ffffff";ctx.beginPath();ctx.moveTo(s,0);ctx.lineTo(-s,-s*.72);ctx.lineTo(-s*.42,0);ctx.closePath();ctx.fill();ctx.stroke();
      ctx.fillStyle="#cfe3f2";ctx.beginPath();ctx.moveTo(s,0);ctx.lineTo(-s*.42,0);ctx.lineTo(-s,s*.72);ctx.closePath();ctx.fill();ctx.stroke();
      ctx.restore();
    },
  };
  function burst(x, y, {kind="petal", n=14, hues=[340], sat=78, light=84, speed=[60,170], angle=-Math.PI/2, spread=Math.PI*2, g=70, life=[1.1,1.9], size=[4,7], sway=24, drag=.85}={}) {
    for(let i=0;i<n;i++){
      const a=angle+(Math.random()-.5)*spread, v=rnd(...speed), h=pick(hues)+rnd(-10,10);
      add({kind,x,y,vx:Math.cos(a)*v,vy:Math.sin(a)*v,g,drag,sway,life:rnd(...life),s:rnd(...size),r:rnd(0,6.3),vr:rnd(-5,5),c:`hsl(${h} ${sat}% ${light+rnd(-6,6)}%)`});
    }
  }
  const sparks=(x,y,n,h)=>burst(x,y,{kind:"spark",n,hues:[h,45],sat:92,light:78,speed:[50,130],g:0,life:[.45,.8],size:[3,6],drag:.55});
  const CONFETTI=[340,45,200,150,275,18];
  function confetti(box) {
    for(const side of [-1,1])burst(side<0?box.left+18:box.right-18,box.bottom,{kind:"confetti",n:52,hues:CONFETTI,sat:84,light:64,
      angle:-Math.PI/2+side*.3,spread:.8,speed:[520,940],g:560,drag:.8,life:[2.2,3],size:[7,12],sway:46});
    sparks(box.left+box.width/2,box.top+box.height/2,8,45);
  }
  function seeds(box, n=16) {
    for(let i=0;i<n;i++)add({kind:"fluff",x:box.left+rnd(0,box.width),y:box.top+rnd(0,box.height),vx:rnd(15,80),vy:rnd(-70,-25),g:-8,drag:.9,sway:34,life:rnd(2.6,4.2),s:rnd(5,8),r:rnd(-.4,.4),vr:rnd(-.7,.7)});
  }
  // The plane leaves the send button, loops up over the conversation and pops into petals where messages land.
  function plane(from) {
    const p0=[from.x,from.y], p3=[Math.max(48,from.x-W*.4),Math.max(80,H*.24)], p1=[Math.min(from.x+W*.12,W-28),from.y-H*.42], p2=[Math.min(p3[0]+W*.38,W-40),p3[1]-H*.06];
    const at=(t,i)=>(1-t)**3*p0[i]+3*(1-t)**2*t*p1[i]+3*(1-t)*t*t*p2[i]+t**3*p3[i];
    const slope=(t,i)=>3*(1-t)**2*(p1[i]-p0[i])+6*(1-t)*t*(p2[i]-p1[i])+3*t*t*(p3[i]-p2[i]);
    add({kind:"plane",x:p0[0],y:p0[1],life:1.5,s:12,trail:[],move(p){
      const t=Math.min(1,p.age/1.1), e=t<.5?2*t*t:1-(-2*t+2)**2/2;
      if(t<1){p.x=at(e,0);p.y=at(e,1);p.r=Math.atan2(slope(e,1),slope(e,0));p.trail.push([p.x,p.y]);if(p.trail.length>30)p.trail.shift();}
      else if(!p.landed){p.landed=true;burst(p.x,p.y,{n:12,hues:[205,330,48],speed:[40,130]});sparks(p.x,p.y,5,205);}
    }});
  }

  /* What happens on the board. A delivery is a comet of light from the speaker's orb up in the strip to their orb in
     the feed; the orb pops, the bubble unfolds out of it and the words stream in. What you send morphs out of the
     composer into its bubble. A release takes over the screen for a moment. Each runs once per message id, so a
     message rebuilt by a later render (a new reply, say) does not celebrate again. */
  const SPRING="linear(0, .009, .035 2.1%, .141, .281 6.7%, .723 12.9%, .938 16.7%, 1.017, 1.077, 1.121, 1.149 24.3%, 1.159, 1.163, 1.161, 1.154 29.9%, 1.129 32.8%, 1.051 39.6%, 1.017 43.1%, .991, .977 51%, .974 53.8%, .975 57.1%, .997 69.8%, 1.003 76.9%, 1.004 83.8%, 1)";
  const springy=CSS.supports("transition-timing-function",SPRING)?SPRING:"cubic-bezier(.3, 1.35, .5, 1)";
  const celebrated=new Set();
  const inView=r=>r.bottom>0&&r.top<H&&r.width>0;
  const hueOf=el=>parseFloat(getComputedStyle(el).getPropertyValue("--hue"))||330;
  const centre=r=>({x:r.left+r.width/2,y:r.top+r.height/2});
  function senderOf(article) {
    for(let a=article;a;a=a.previousElementSibling)if(a.matches?.(".message")){const s=a.querySelector(".meta .sender");if(s)return s.textContent.trim();}
    return "";
  }
  // Where the speaker's orb is on screen: the strip under the top bar, then the Agents list on a wide screen.
  function sourceOf(name) {
    for(const b of document.querySelectorAll(".orb-button"))if(b.querySelector(".orb-name")?.textContent===name){const o=b.querySelector(".orb"), r=o.getBoundingClientRect();if(inView(r)&&r.top>=0)return {el:o,r};}
    const cell=[...document.querySelectorAll(".agent-cell")].find(c=>c.dataset.agent===name)?.querySelector(".orb");
    if(cell){const r=cell.getBoundingClientRect();if(inView(r))return {el:cell,r};}
    return null;
  }
  const restart=(el,cls)=>{el.classList.remove(cls);void el.offsetWidth;el.classList.add(cls);};
  function speak(el) { if(!el)return;restart(el,"speaking");setTimeout(()=>el.classList.remove("speaking"),2400); }

  // Words fade up out of a blur one after another. Code stays whole; a long message is folded anyway, so only
  // messages of up to 160 words stream. The spans are unwrapped once the words have settled.
  function stream(article) {
    const body=article.querySelector(".bubble .body");if(!body)return;
    const texts=[], walker=document.createTreeWalker(body,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.parentElement.closest("pre,code")||!n.nodeValue.trim()?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});
    while(walker.nextNode())texts.push(walker.currentNode);
    const count=texts.reduce((n,t)=>n+t.nodeValue.split(/\s+/).filter(Boolean).length,0);if(!count||count>160)return;
    const step=Math.min(32,1100/count), words=[];
    for(const t of texts){
      const frag=document.createDocumentFragment();
      for(const part of t.nodeValue.split(/(\s+)/)){
        if(!part)continue;
        if(/^\s+$/.test(part)){frag.append(part);continue;}
        const w=document.createElement("span");w.className="w";w.textContent=part;w.style.setProperty("--wd",`${Math.round(words.length*step)}ms`);words.push(w);frag.append(w);
      }
      t.replaceWith(frag);
    }
    body.classList.add("streaming");
    const delay=parseFloat(article.style.getPropertyValue("--d"))||0;
    setTimeout(()=>{for(const w of words)if(w.isConnected)w.replaceWith(w.textContent);body.normalize();body.classList.remove("streaming");},delay*1000+words.length*step+1200);
  }

  // A comet: a bright head with a fading tail along a gentle arc, then a ring and petals where it lands.
  function comet(from, to, h, arrive) {
    const bend=Math.max(60,Math.abs(to.x-from.x)*.35), c=[(from.x+to.x)/2+(from.x<to.x?-1:1)*bend*.4,Math.min(from.y,to.y)-bend*.25+(to.y-from.y)*.3];
    add({kind:"comet",x:from.x,y:from.y,life:.95,s:5,h,trail:[],move(p){
      const t=Math.min(1,p.age/.48), e=1-(1-t)**2.4;
      if(t<1){p.x=(1-e)**2*from.x+2*(1-e)*e*c[0]+e*e*to.x;p.y=(1-e)**2*from.y+2*(1-e)*e*c[1]+e*e*to.y;p.trail.push([p.x,p.y]);if(p.trail.length>22)p.trail.shift();}
      else if(!p.hit){p.hit=true;p.trail.push([to.x,to.y]);arrive?.();}
      else if(p.trail.length>1)p.trail.shift();
    }});
  }
  function arrive(article) {
    if(!article.isConnected)return;
    const o=article.querySelector(":scope > .orb-link .orb"), b=article.querySelector(".bubble");
    const r=(o||b).getBoundingClientRect(), at=o?centre(r):{x:r.left+18,y:r.top+14}, h=o?hueOf(o):330;
    add({kind:"ring",x:at.x,y:at.y,life:.7,s:r.width/2||12,grow:30,c:`hsl(${h} 90% 70%)`,a:.8});
    burst(at.x,at.y,{n:16,hues:[h,h+28,h-22],speed:[60,200],size:[4.5,8]});sparks(at.x,at.y,5,h);
    const topic=article.querySelector(".meta .topic");
    if(topic?.classList.contains("ack")){const c=topic.getBoundingClientRect();setTimeout(()=>sparks(c.left+c.width/2,c.top+c.height/2,6,150),420);}
  }

  // What you send flies out of the composer: the column starts at the composer's place and size and springs into
  // its bubble while the words stream in.
  let sent=null;
  function morph(article) {
    const col=article.querySelector(".message-column"), b=col?.getBoundingClientRect();if(!b?.width)return false;
    const dx=sent.r.left-b.left, dy=sent.r.top-b.top, sx=sent.r.width/b.width, sy=Math.min(2.5,sent.r.height/b.height);
    article.classList.add("morph");
    col.animate([{transformOrigin:"0 0",transform:`translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`,opacity:.35},{transformOrigin:"0 0",opacity:1,offset:.35},{transformOrigin:"0 0",transform:"none",opacity:1}],{duration:720,easing:springy});
    setTimeout(()=>{const r=article.querySelector(".bubble")?.getBoundingClientRect();if(r){burst(r.right-14,r.top+8,{n:14,hues:[205,330,200],light:86,angle:-Math.PI*.62,spread:Math.PI*1.1,speed:[50,160]});sparks(r.right-14,r.top+8,4,205);}},380);
    return true;
  }

  function fresh(article, i) {
    const mine=article.classList.contains("mine"), b=article.getBoundingClientRect();
    stream(article);
    if(!inView(b))return;
    if(mine){if(sent&&performance.now()-sent.at<8000&&morph(article))sent=null;return;}
    const o=article.querySelector(":scope > .orb-link .orb"), name=senderOf(article), src=name&&sourceOf(name);
    const to=o?centre(o.getBoundingClientRect()):{x:b.left+20,y:b.top+16};
    const from=src?centre(src.r):{x:Math.min(W-30,to.x+W*.45),y:-20};
    // The bubble waits for its comet.
    const wait=.4+i*.16;article.style.setProperty("--d",`${wait}s`);
    setTimeout(()=>{speak(src?.el);comet(from,to,o?hueOf(o):(src?hueOf(src.el):330),()=>arrive(article));},i*160);
  }
  const feeds=new MutationObserver(records=>{
    if(!on())return;
    const list=[];
    for(const record of records)for(const n of record.addedNodes){
      if(!(n instanceof Element))continue;
      for(const m of n.matches(".message.enter")?[n]:n.querySelectorAll(".message.enter")){
        const id=m.dataset.ids||"";
        if(celebrated.has(id)){m.classList.add("again");continue;}
        celebrated.add(id);list.push(m);
      }
    }
    // A burst of history (a catch-up after the app wakes) celebrates only the newest few; the rest appear quietly.
    list.slice(0,-3).forEach(m=>m.classList.add("again"));
    list.slice(-3).forEach(fresh);
    const release=list.slice(-3).find(m=>m.querySelector(".meta .topic.release"));
    if(release)setTimeout(()=>takeover(release),900);
  });
  for(const id of ["messages","threadFeed"]){const feed=document.getElementById(id);if(feed)feeds.observe(feed,{childList:true,subtree:true});}

  /* A release: the meadow flashes, fireworks go up, confetti rains and its first line springs up letter by letter
     across the screen. A tap, or a few seconds, puts it away. Each release celebrates once on this device. */
  const SEEN="atelier.board.celebrated";
  function firstTime(id) {
    try { const seen=JSON.parse(localStorage.getItem(SEEN)||"[]");if(seen.includes(id))return false;localStorage.setItem(SEEN,JSON.stringify([...seen,id].slice(-40))); } catch {}
    return true;
  }
  function rocket(x, y, h, delay) {
    setTimeout(()=>add({kind:"comet",x,y:H+10,life:1,s:3.2,h,trail:[],move(p){
      const t=Math.min(1,p.age/.62), e=1-(1-t)**2;
      if(t<1){p.x=x+Math.sin(t*5)*6;p.y=H+10-(H+10-y)*e;p.trail.push([p.x,p.y]);if(p.trail.length>16)p.trail.shift();}
      else if(!p.hit){p.hit=true;
        burst(x,y,{kind:"ember",n:54,hues:[h,h+35,45],sat:95,light:70,speed:[90,300],g:110,drag:.62,life:[1,1.7],size:[1.6,2.8],sway:0});
        add({kind:"ring",x,y,life:.6,s:4,grow:90,c:`hsl(${h} 95% 75%)`,a:.7});boardScene()?.flash(.12);}
      else if(p.trail.length>1)p.trail.shift();
    }}),delay);
  }
  const boardScene=()=>window.boardScene;
  function rain(n=110) {
    for(let i=0;i<n;i++)add({kind:"confetti",x:rnd(0,W),y:rnd(-H*.5,-10),vx:rnd(-30,30),vy:rnd(90,220),g:70,drag:.96,sway:60,life:rnd(3,4.4),s:rnd(7,12),r:rnd(0,6.3),vr:rnd(-6,6),c:`hsl(${pick(CONFETTI)} 84% ${rnd(58,70)}%)`});
  }
  function takeover(article) {
    if(!article.isConnected||document.querySelector(".celebration"))return;
    if(!firstTime((article.dataset.ids||"").split(" ")[0]))return;
    const text=(article.querySelector(".body")?.textContent||"Released").trim().split(/\n|(?<=[.!?])\s/)[0].replace(/[*_`#]/g,"").slice(0,90);
    const who=senderOf(article)||"The team", o=article.querySelector(".orb");
    const layer=document.createElement("div");layer.className="celebration";layer.setAttribute("aria-hidden","true");
    const card=document.createElement("div");card.className="cel-card";
    const kicker=document.createElement("p");kicker.className="cel-kicker";kicker.textContent=`Release · ${who}`;
    const title=document.createElement("h2");title.className="cel-title";
    let k=0;
    for(const word of text.split(/\s+/).filter(Boolean)){
      const w=document.createElement("span");w.className="cw";
      for(const ch of word){const l=document.createElement("span");l.className="cl";l.textContent=ch;l.style.setProperty("--i",k++);w.append(l);}
      title.append(w," ");
    }
    const hint=document.createElement("p");hint.className="cel-hint";hint.textContent="Tap to carry on";
    card.append(kicker,title,hint);layer.append(card);
    if(o)layer.style.setProperty("--hue",hueOf(o));
    document.body.append(layer);requestAnimationFrame(()=>layer.classList.add("show"));
    boardScene()?.flash(.6);
    const hues=[340,45,200,150,275];
    for(let i=0;i<6;i++)rocket(rnd(W*.12,W*.88),rnd(H*.12,H*.42),pick(hues),150+i*360);
    setTimeout(()=>rain(),250);
    let gone=false;
    const close=()=>{if(gone)return;gone=true;layer.classList.add("hide");setTimeout(()=>layer.remove(),700);};
    layer.addEventListener("pointerdown",close);setTimeout(close,4200);
  }

  const form=document.getElementById("broadcastForm");let wasSending=false;
  new MutationObserver(()=>{
    const sending=form.classList.contains("sending");
    if(sending&&!wasSending&&on()){
      sent={r:form.getBoundingClientRect(),at:performance.now()};
      const r=document.getElementById("sendButton").getBoundingClientRect(), c=centre(r);
      add({kind:"ring",x:c.x,y:c.y,life:.55,s:r.width/2,grow:22,c:"#4f8fc4",a:.6});sparks(c.x,c.y,6,205);
      form.animate([{scale:"1"},{scale:".975 .94"},{scale:"1"}],{duration:420,easing:springy});
    }
    wasSending=sending;
  }).observe(form,{attributes:true,attributeFilter:["class"]});
  // Typing fizzes a few tiny sparks off the composer.
  let fizzAt=0;
  document.getElementById("message").addEventListener("input",()=>{
    const now=performance.now();if(now-fizzAt<110)return;fizzAt=now;
    const r=form.getBoundingClientRect();sparks(rnd(r.left+r.width*.3,r.right-50),r.top+4,1,pick([330,205,48]));
  });
  // An aurora drifts inside the composer's glass while you write.
  const aurora=document.createElement("span");aurora.className="aurora";aurora.setAttribute("aria-hidden","true");aurora.append(document.createElement("i"));form.prepend(aurora);
  document.addEventListener("pointerdown",event=>{
    if(!on()||!event.isPrimary)return;
    const target=event.target.closest("button,summary,.toggle,.agent-row");if(!target||target.disabled)return;
    add({kind:"ring",x:event.clientX,y:event.clientY,life:.55,s:3,grow:24,c:"#c94f86",a:.45});
    if(target.closest(".tab,.orb-button"))sparks(event.clientX,event.clientY,4,330);
  },{passive:true});
  // Easter eggs: tap the wordmark to blow on the dandelion; double-tap it to watch a whole day pass over the meadow.
  for(const mark of document.querySelectorAll(".wordmark")){
    mark.addEventListener("click",()=>seeds(mark.getBoundingClientRect()));
    mark.addEventListener("dblclick",()=>{if(on())boardScene()?.timelapse(14000);});
  }
  // On a desktop the bubble under the pointer tilts toward it like a pane of glass.
  if(matchMedia("(hover: hover) and (pointer: fine)").matches){
    let tilted=null;
    document.addEventListener("pointermove",event=>{
      const b=on()&&event.target.closest?.(".message .bubble");
      if(tilted&&tilted!==b){tilted.classList.remove("tilt");tilted=null;}
      if(!b)return;
      const r=b.getBoundingClientRect();
      b.style.setProperty("--tx",((event.clientX-r.left)/r.width*2-1).toFixed(3));b.style.setProperty("--ty",((event.clientY-r.top)/r.height*2-1).toFixed(3));
      if(!tilted){b.classList.add("tilt");tilted=b;}
    },{passive:true});
  }

  for(const id of ["messagesBadge","agentsBadge"]){
    const badge=document.getElementById(id);let text=badge.textContent;
    new MutationObserver(()=>{if(badge.textContent!==text&&!badge.hidden&&on())restart(badge,"jiggle");text=badge.textContent;})
      .observe(badge,{childList:true,characterData:true,subtree:true,attributes:true,attributeFilter:["hidden"]});
  }
  const indicator=document.querySelector(".tab-indicator");
  new MutationObserver(()=>{if(on())restart(indicator,"squish");}).observe(document.getElementById("tabbar"),{subtree:true,attributes:true,attributeFilter:["aria-current"]});

  /* The meadow's residents, and the light by the time of day. */
  const bit=(cls,inner,tag="span")=>{const n=document.createElement(tag);n.className=cls;if(inner)n.append(document.createElement("i"));return n;};
  for(const layer of document.querySelectorAll(".ambience")){
    layer.append(bit("tint"),bit("sunbeams"),bit("butterfly",true),bit("butterfly b2",true));
    for(let i=0;i<7;i++)layer.append(bit("firefly",false,"b"));
  }
  function daylight() {
    const now=new Date(), h=now.getHours()+now.getMinutes()/60;
    app.classList.toggle("dusk",h>=19||h<6);app.classList.toggle("golden",h>=17&&h<19);
  }
  daylight();setInterval(daylight,300000);

  function apply() {
    app.classList.toggle("playful",on());
    if(toggle){toggle.checked=wanted;toggle.disabled=reduce.matches;}
    if(note)note.textContent=reduce.matches?"Off while Reduce Motion is on.":wanted?"Comets, fireworks and a living meadow.":"Off. The meadow keeps its quiet motion.";
  }
  toggle?.addEventListener("change",()=>{
    wanted=toggle.checked;try { localStorage.setItem(KEY,wanted?"on":"off"); } catch {}
    apply();if(wanted)confetti(toggle.closest(".card").getBoundingClientRect());
  });
  reduce.addEventListener?.("change",apply);
  apply();
  window.boardFx={burst,confetti,plane,seeds,sparks};
})();
