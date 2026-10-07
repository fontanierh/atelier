"use strict";
/* Playful motion: petals from an agent's orb as their message lands, a paper plane for what you send, confetti for a
   release, butterflies by day and fireflies after dusk. One canvas draws the particles and sleeps once none are
   left; everything else is CSS under .app.playful. The switch under Agents, or Reduce Motion, turns it all off. */
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
    if(!on()||parts.length>600)return;
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

  /* What happens on the board */
  const done=new WeakSet();
  const inView=r=>r.bottom>0&&r.top<H&&r.width>0;
  const hueOf=el=>parseFloat(getComputedStyle(el).getPropertyValue("--hue"))||330;
  function landed(article) {
    const bubble=article.querySelector(".bubble");if(!bubble||!article.isConnected)return;
    const b=bubble.getBoundingClientRect();if(!inView(b))return;
    const topic=article.querySelector(".meta .topic");
    if(article.classList.contains("mine"))burst(b.right-16,b.top+10,{n:12,hues:[205,330,200],light:86,angle:-Math.PI*.62,spread:Math.PI*1.1,speed:[50,150]});
    else {
      const orb=article.querySelector(".orb"), r=(orb||bubble).getBoundingClientRect(), h=orb?hueOf(orb):330;
      burst(r.left+r.width/2,r.top+r.height/2,{n:18,hues:[h,h+28,h-22],speed:[60,190],size:[4.5,8]});sparks(r.left+r.width/2,r.top+r.height/2,3,h);
    }
    if(topic?.classList.contains("release"))confetti(b);
    else if(topic?.classList.contains("ack")){const c=topic.getBoundingClientRect();sparks(c.left+c.width/2,c.top+c.height/2,5,150);}
  }
  const feeds=new MutationObserver(records=>{
    if(!on())return;
    const fresh=[];
    for(const record of records)for(const n of record.addedNodes){
      if(!(n instanceof Element))continue;
      for(const m of n.matches(".message.enter")?[n]:n.querySelectorAll(".message.enter"))if(!done.has(m)){done.add(m);fresh.push(m);}
    }
    // A burst of history (a catch-up after the app wakes) celebrates only the newest few.
    fresh.slice(-3).forEach((m,i)=>setTimeout(()=>landed(m),170+i*150));
  });
  for(const id of ["messages","threadFeed"])feeds.observe(document.getElementById(id),{childList:true,subtree:true});

  const form=document.getElementById("broadcastForm");let wasSending=false;
  new MutationObserver(()=>{
    const sending=form.classList.contains("sending");
    if(sending&&!wasSending){const r=document.getElementById("sendButton").getBoundingClientRect();plane({x:r.left+r.width/2,y:r.top+r.height/2});}
    wasSending=sending;
  }).observe(form,{attributes:true,attributeFilter:["class"]});
  // Typing fizzes a few tiny sparks off the composer.
  let fizzAt=0;
  document.getElementById("message").addEventListener("input",()=>{
    const now=performance.now();if(now-fizzAt<110)return;fizzAt=now;
    const r=form.getBoundingClientRect();sparks(rnd(r.left+r.width*.3,r.right-50),r.top+4,1,pick([330,205,48]));
  });
  document.addEventListener("pointerdown",event=>{
    if(!on()||!event.isPrimary)return;
    const target=event.target.closest("button,summary,.toggle,.agent-row");if(!target||target.disabled)return;
    add({kind:"ring",x:event.clientX,y:event.clientY,life:.55,s:3,grow:24,c:"#c94f86",a:.45});
    if(target.closest(".tab,.orb-button"))sparks(event.clientX,event.clientY,4,330);
  },{passive:true});
  // Easter egg: tap the wordmark to blow on the dandelion.
  for(const mark of document.querySelectorAll(".wordmark"))mark.addEventListener("click",()=>seeds(mark.getBoundingClientRect()));

  const restart=(el,cls)=>{el.classList.remove(cls);void el.offsetWidth;el.classList.add(cls);};
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
    if(note)note.textContent=reduce.matches?"Off while Reduce Motion is on.":wanted?"Petals, butterflies and confetti.":"Off. The meadow keeps its quiet motion.";
  }
  toggle?.addEventListener("change",()=>{
    wanted=toggle.checked;try { localStorage.setItem(KEY,wanted?"on":"off"); } catch {}
    apply();if(wanted)confetti(toggle.closest(".card").getBoundingClientRect());
  });
  reduce.addEventListener?.("change",apply);
  apply();
  window.boardFx={burst,confetti,plane,seeds,sparks};
})();
