"use strict";
/* The living meadow: the board's watercolor painting as a WebGL texture, brought to life. Wind runs through the
   flowers, the trees at the edges sway, mist drifts across the valley, the sun throws slow rays and sparkles on the
   river, and motes of light float in the air. The light follows the local clock: dawn as painted, a brighter day, a
   golden hour, then dusk and a night sky with stars, a moon, an aurora, shooting stars and fireflies in the grass.
   The meadow shifts with the pointer, a tilt of the conversation and scrolling, and a finger or cursor carries a
   soft light. It draws at a low resolution (watercolor is soft) and at most 30 frames a second, stops while the
   board is hidden, and stays the still painting with Reduce Motion, the Playful switch off, or no WebGL. */
(()=>{
  const app=document.getElementById("app");
  if(!app)return;
  const canvas=document.createElement("canvas");canvas.className="scene-canvas";canvas.setAttribute("aria-hidden","true");
  app.prepend(canvas);
  const gl=canvas.getContext("webgl",{alpha:false,antialias:false,depth:false,stencil:false,premultipliedAlpha:false,powerPreference:"low-power"});
  if(!gl)return;
  const reduce=matchMedia("(prefers-reduced-motion: reduce)"), wide=matchMedia("(min-width: 1100px)");
  const PAINTINGS={portrait:{src:"/meadow-portrait-1.webp",sun:[.885,.108],river:.722,flowers:.70},
                   landscape:{src:"/meadow-landscape-1.webp",sun:[.895,.178],river:.782,flowers:.62}};

  const VERT="attribute vec2 p;varying vec2 v;void main(){v=vec2(p.x*.5+.5,.5-p.y*.5);gl_Position=vec4(p,0.,1.);}";
  const FRAG=`precision mediump float;
varying vec2 v;
uniform sampler2D T;uniform vec2 R,I,S,M,P;uniform float t,night,gold,day,flowers,river,mouseOn,flash;
float h(vec2 p){p=fract(p*vec2(123.34,456.21));p+=dot(p,p+45.32);return fract(p.x*p.y);}
float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y);}
float fbm(vec2 p){float a=.5,s=0.;for(int i=0;i<4;i++){s+=a*n(p);p=p*2.03+vec2(1.7,9.2);a*=.5;}return s;}
vec2 cover(vec2 s){float ra=R.x/R.y,ri=I.x/I.y;if(ra>ri)s.y=(s.y-.5)*(ri/ra)+.5;else s.x=(s.x-.5)*(ra/ri)+.5;return s;}
void main(){
  vec2 uv=cover(v);
  float depth=smoothstep(.15,1.,uv.y);
  uv+=P*(.003+.016*depth);
  uv=mix(vec2(.5),uv,.975);
  float fg=smoothstep(flowers-.1,flowers+.3,uv.y);
  float gust=.55+.45*sin(t*.33+uv.x*2.3)*sin(t*.21+1.3);
  float sway=sin(t*1.6+uv.y*17.+uv.x*5.)*.55+sin(t*2.7+uv.y*29.+uv.x*13.)*.25;
  uv.x+=sway*fg*fg*.0065*(.6+gust);
  float side=smoothstep(.3,.04,uv.x)+smoothstep(.7,.96,uv.x);
  uv.x+=sin(t*.75+uv.y*8.)*.0016*side*(1.-fg)*smoothstep(.05,.5,uv.y);
  float rv=exp(-pow((uv.y-river)*38.,2.))*smoothstep(.2,.4,uv.x)*smoothstep(.95,.7,uv.x);
  uv.y+=sin(t*1.9+uv.x*140.)*.0011*rv;
  vec3 c=texture2D(T,clamp(uv,.001,.999)).rgb;
  float ar=I.x/I.y;
  float m=fbm(vec2(uv.x*2.6-t*.022,uv.y*5.5+t*.004))*fbm(vec2(uv.x*1.3+t*.011,uv.y*2.6-t*.006)+3.1);
  float band=smoothstep(.12,.32,uv.y)*smoothstep(.88,.58,uv.y);
  c=mix(c,vec3(.99,1.,1.),smoothstep(.16,.52,m)*band*(.42-.12*day));
  vec2 d=(uv-S)*vec2(ar,1.);float r=length(d),a=atan(d.y,d.x);
  float glow=exp(-r*6.5)*.32+exp(-r*26.)*.55;
  float rays=pow(.5+.5*sin(a*11.+t*.12)*sin(a*6.-t*.09+1.),3.)*exp(-r*2.2)*smoothstep(.02,.22,r)*.26;
  vec3 sunC=mix(vec3(1.,.94,.8),vec3(1.,.7,.42),gold);
  float lit=1.-night;
  c+=sunC*(glow+rays*(1.-.5*day))*lit;
  vec2 q=uv*vec2(ar*34.,34.)+vec2(t*.15,-t*.32);vec2 cell=floor(q);float k=h(cell);
  vec2 o=fract(q)-vec2(h(cell+7.),h(cell+3.));float mote=smoothstep(.06,.0,length(o))*step(.82,k)*(.5+.5*sin(t*2.+k*40.));
  c+=sunC*mote*.55*lit*smoothstep(.95,.35,uv.y)*(.4+exp(-r*2.)*1.2);
  float g=h(floor(uv*vec2(520.,110.))+floor(t*4.));
  c+=vec3(1.,.97,.88)*step(.982,g)*rv*(.8*lit+.35*night);
  c*=mix(vec3(1.),vec3(1.08,.95,.8),gold*.9);
  c=mix(c,c*1.04+vec3(.012,.02,.01),day);
  vec3 nightC=c*vec3(.26,.31,.52)+vec3(.015,.02,.06);
  float sky=smoothstep(.42,.08,uv.y);
  vec2 sq=uv*vec2(ar*90.,90.);vec2 sc=floor(sq);float sk=h(sc);
  float star=smoothstep(.09,.0,length(fract(sq)-vec2(h(sc+1.),h(sc+2.))))*step(.93,sk)*(.55+.45*sin(t*(1.+sk*3.)+sk*90.));
  nightC+=vec3(.85,.9,1.)*star*sky*1.3;
  float au=fbm(vec2(uv.x*3.+t*.03,t*.05))*smoothstep(.36,.12,uv.y)*smoothstep(.0,.1,uv.y);
  float curtain=pow(.5+.5*sin(uv.x*9.+fbm(vec2(uv.x*4.,t*.07))*6.),4.);
  nightC+=mix(vec3(.15,.85,.55),vec3(.55,.35,.95),smoothstep(.1,.32,uv.y))*au*curtain*.5;
  vec2 md=(uv-S-vec2(-.05,.02))*vec2(ar,1.);float mr=length(md);
  nightC+=vec3(.85,.9,1.)*(smoothstep(.028,.022,mr)*.9+exp(-mr*14.)*.25);
  float ss=fract(t/11.);vec2 sp=vec2(.15+ss*.6,.05+ss*.18);vec2 sd=uv-sp;float sl=dot(sd,normalize(vec2(-.95,-.3)));
  float streak=smoothstep(.004,.0,abs(sd.x*.3-sd.y*.95))*smoothstep(.0,.002,sl)*smoothstep(.09,.0,sl)*step(ss,.18)*step(.5,h(vec2(floor(t/11.))));
  nightC+=vec3(1.)*streak*sky;
  vec2 fq=uv*vec2(ar*14.,14.)+vec2(sin(t*.3)*.6,t*.05);vec2 fc=floor(fq);float fk=h(fc);
  vec2 fo=fract(fq)-.5-vec2(sin(t*.7+fk*20.),cos(t*.6+fk*30.))*.3;
  float fly=smoothstep(.12,.0,length(fo))*step(.72,fk)*pow(.5+.5*sin(t*(1.2+fk*2.)+fk*60.),3.);
  nightC+=vec3(1.,.9,.4)*fly*smoothstep(flowers-.15,flowers+.1,uv.y)*1.4;
  c=mix(c,nightC,night);
  vec2 pm=(v-M)*vec2(R.x/R.y,1.);
  c+=mix(vec3(1.,.95,.84),vec3(1.,.85,.5),night)*exp(-dot(pm,pm)*14.)*(.16+.2*night)*mouseOn;
  c+=vec3(1.,.97,.9)*flash;
  vec2 vg=v-.5;c*=1.-dot(vg,vg)*.28;
  gl_FragColor=vec4(c,1.);
}`;
  function shader(type, src) { const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS)){console.warn(gl.getShaderInfoLog(s));return null;}return s; }
  const vs=shader(gl.VERTEX_SHADER,VERT), fs=shader(gl.FRAGMENT_SHADER,FRAG);
  if(!vs||!fs)return;
  const prog=gl.createProgram();gl.attachShader(prog,vs);gl.attachShader(prog,fs);gl.linkProgram(prog);
  if(!gl.getProgramParameter(prog,gl.LINK_STATUS))return;
  gl.useProgram(prog);
  const buf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,3,-1,-1,3]),gl.STATIC_DRAW);
  const loc=gl.getAttribLocation(prog,"p");gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,2,gl.FLOAT,false,0,0);
  const U={};for(const name of ["T","R","I","S","M","P","t","night","gold","day","flowers","river","mouseOn","flash"])U[name]=gl.getUniformLocation(prog,name);
  const tex=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,tex);
  for(const [k,val] of [[gl.TEXTURE_MIN_FILTER,gl.LINEAR],[gl.TEXTURE_MAG_FILTER,gl.LINEAR],[gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE],[gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE]])gl.texParameteri(gl.TEXTURE_2D,k,val);

  let painting=null, ready=false, raf=0, lastFrame=0, start=performance.now();
  function load() {
    const want=wide.matches?PAINTINGS.landscape:PAINTINGS.portrait;
    if(painting===want)return;painting=want;
    const img=new Image();img.decoding="async";
    img.onload=()=>{if(painting!==want)return;gl.bindTexture(gl.TEXTURE_2D,tex);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGB,gl.RGB,gl.UNSIGNED_BYTE,img);
      gl.uniform2f(U.I,img.naturalWidth,img.naturalHeight);gl.uniform2f(U.S,...want.sun);gl.uniform1f(U.river,want.river);gl.uniform1f(U.flowers,want.flowers);ready=true;wake();};
    img.src=want.src;
  }
  // Watercolor is soft: about one canvas pixel per CSS pixel on a phone, fewer on a big screen.
  function size() {
    const scale=Math.min(1,900/Math.max(innerWidth,innerHeight))*Math.min(devicePixelRatio||1,1.25);
    const w=Math.max(2,Math.round(canvas.clientWidth*scale)), hgt=Math.max(2,Math.round(canvas.clientHeight*scale));
    if(canvas.width!==w||canvas.height!==hgt){canvas.width=w;canvas.height=hgt;gl.viewport(0,0,w,hgt);}
    gl.uniform2f(U.R,w,hgt);
  }

  // The light by the clock (or a time-lapse, or a pinned hour for previews).
  let pinned=null, lapse=null;
  const smooth=(a,b,x)=>{const k=Math.min(1,Math.max(0,(x-a)/(b-a)));return k*k*(3-2*k);};
  function light(hour) {
    const night=Math.max(smooth(19,20.6,hour),1-smooth(5,6.6,hour));
    const gold=smooth(16.3,17.6,hour)*(1-smooth(18.8,19.8,hour));
    const day=smooth(8,10,hour)*(1-smooth(15.5,17,hour));
    return {night,gold,day};
  }
  function hourNow(now) {
    if(lapse){const k=(now-lapse.start)/lapse.ms;if(k>=1)lapse=null;else return (lapse.from+k*24)%24;}
    if(pinned!==null)return pinned;
    const d=new Date();return d.getHours()+d.getMinutes()/60;
  }

  // Parallax: the pointer (or a finger), the conversation's scroll, eased.
  const target={x:0,y:0}, par={x:0,y:0}, mouse={x:.5,y:.5,on:0,want:0};
  addEventListener("pointermove",e=>{target.x=(e.clientX/innerWidth-.5)*-1;target.y=(e.clientY/innerHeight-.5)*-1;mouse.x=e.clientX/innerWidth;mouse.y=e.clientY/innerHeight;mouse.want=e.pointerType==="mouse"?1:mouse.want;},{passive:true});
  addEventListener("pointerdown",e=>{mouse.x=e.clientX/innerWidth;mouse.y=e.clientY/innerHeight;mouse.want=1;},{passive:true});
  addEventListener("pointerup",e=>{if(e.pointerType!=="mouse")mouse.want=0;},{passive:true});
  document.addEventListener("mouseleave",()=>{mouse.want=0;});
  let flash=0;
  const feed=document.getElementById("feed");

  const on=()=>!reduce.matches&&app.classList.contains("playful")&&ready&&!document.hidden;
  function frame(now) {
    raf=0;if(!on()){app.classList.remove("scene-on");return;}
    raf=requestAnimationFrame(frame);
    if(now-lastFrame<32)return;
    const dt=Math.min(.1,(now-lastFrame)/1000);lastFrame=now;
    size();
    const scroll=feed?Math.min(1,feed.scrollTop/Math.max(1,feed.scrollHeight-feed.clientHeight)):0;
    const k=1-Math.pow(.04,dt);
    par.x+=(target.x-par.x)*k;par.y+=((target.y-(scroll-.5)*.6)-par.y)*k;
    mouse.on+=(mouse.want-mouse.on)*k;flash*=Math.pow(.02,dt);
    const L=light(hourNow(now));
    gl.uniform1f(U.t,(now-start)/1000);gl.uniform2f(U.P,par.x,par.y);gl.uniform2f(U.M,mouse.x,mouse.y);
    gl.uniform1f(U.mouseOn,mouse.on);gl.uniform1f(U.night,L.night);gl.uniform1f(U.gold,L.gold);gl.uniform1f(U.day,L.day);gl.uniform1f(U.flash,flash);
    gl.drawArrays(gl.TRIANGLES,0,3);
    if(!app.classList.contains("scene-on"))app.classList.add("scene-on");
    app.classList.toggle("scene-night",L.night>.5);
  }
  function wake() { if(!raf&&on()){lastFrame=0;raf=requestAnimationFrame(frame);} else if(!on())app.classList.remove("scene-on"); }
  canvas.addEventListener("webglcontextlost",e=>{e.preventDefault();ready=false;app.classList.remove("scene-on");});
  canvas.addEventListener("webglcontextrestored",()=>{painting=null;load();});
  wide.addEventListener?.("change",load);reduce.addEventListener?.("change",wake);
  document.addEventListener("visibilitychange",wake);
  new MutationObserver(wake).observe(app,{attributes:true,attributeFilter:["class"]});
  load();
  window.boardScene={
    pin(hour){pinned=hour;},
    timelapse(ms=12000){lapse={start:performance.now(),ms,from:hourNow(performance.now())};},
    flash(amount=.35){flash=Math.max(flash,amount);},
  };
})();
