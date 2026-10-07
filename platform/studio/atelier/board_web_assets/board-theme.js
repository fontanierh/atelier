"use strict";
/* Light, dark, or whatever the device uses (the setting under Agents). It runs before the board paints, so the board
   never flashes the wrong one, and keeps the browser's own bars in the same colour. */
(()=>{
  const KEY="atelier.board.theme", root=document.documentElement, system=matchMedia("(prefers-color-scheme: dark)");
  let choice="auto";
  try { const saved=localStorage.getItem(KEY); if(saved==="light"||saved==="dark")choice=saved; } catch {}
  let preloaded=false;
  function apply() {
    const dark=choice==="dark"||(choice==="auto"&&system.matches);
    // Start fetching the painting this screen will show before the stylesheet asks for it.
    if(!preloaded){preloaded=true;const wide=matchMedia("(min-width: 1100px)").matches, link=document.createElement("link");
      link.rel="preload";link.as="image";link.type="image/webp";
      link.href=`/meadow-${dark?"night-":""}${wide?"landscape":"portrait"}-${!dark&&wide?2:1}.webp`;document.head.append(link);}
    root.dataset.theme=dark?"dark":"light";
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content",dark?"#0e1530":"#e6eef0");
    dispatchEvent(new CustomEvent("boardtheme",{detail:{dark,choice}}));
  }
  system.addEventListener?.("change",()=>{if(choice==="auto")apply();});
  window.boardTheme={
    get choice(){return choice;},
    get dark(){return root.dataset.theme==="dark";},
    set(next){choice=next==="light"||next==="dark"?next:"auto";try{if(choice==="auto")localStorage.removeItem(KEY);else localStorage.setItem(KEY,choice);}catch{}apply();},
  };
  apply();
})();
