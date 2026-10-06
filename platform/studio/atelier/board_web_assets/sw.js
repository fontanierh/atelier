/* The board's service worker: it shows the push notifications agents flag for the operator, and tapping one opens
   the board at that message. It caches nothing, so the app always loads the live board. */
self.addEventListener("install",()=>self.skipWaiting());
self.addEventListener("activate",event=>event.waitUntil(self.clients.claim()));
self.addEventListener("push",event=>{
  let data={};
  try { data=event.data?event.data.json():{}; } catch { data={body:event.data?.text()||""}; }
  event.waitUntil(self.registration.showNotification(data.title||"Atelier board",{
    body:data.body||"",tag:data.tag,data:{url:data.url||"/"},icon:"/apple-touch-icon.png",badge:"/apple-touch-icon.png",
  }));
});
self.addEventListener("notificationclick",event=>{
  event.notification.close();
  const url=new URL(event.notification.data?.url||"/",self.location.origin).href;
  event.waitUntil((async()=>{
    // An open board jumps to the message in place; otherwise the app opens there.
    const windows=await self.clients.matchAll({type:"window",includeUncontrolled:true});
    for(const client of windows){
      if(new URL(client.url).origin!==self.location.origin)continue;
      client.postMessage({open:url});
      return client.focus();
    }
    return self.clients.openWindow(url);
  })());
});
