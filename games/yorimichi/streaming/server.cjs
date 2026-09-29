// Epic's signalling protocol; only loopback listeners. Tailscale Serve is the
// private HTTPS/WebSocket ingress. No public port forwarding or cloud service.
const http = require('node:http');
const path = require('node:path');
const fs = require('node:fs');
const express = require('express');
const {SignallingServer, InitLogging} = require('@epicgames-ps/lib-pixelstreamingsignalling-ue5.8');
const root = path.resolve(process.env.YORIMICHI_STREAM_OUTPUT || path.resolve(__dirname, '../../../build/yorimichi/pixel-streaming'));
// Ports are overridable so a second checkout can run its own private stream for testing next to the live one.
const HTTP_PORT=Number(process.env.YORIMICHI_HTTP_PORT||8080), STREAMER_PORT=Number(process.env.YORIMICHI_STREAMER_PORT||8888), TURN_PORT=Number(process.env.YORIMICHI_TURN_PORT||3478);
InitLogging({logDir: path.join(root, 'logs'), logLevelConsole: 'info'});
const app=express();
app.disable('x-powered-by');
app.post('/diagnostics',express.json({limit:'16kb'}),(req,res)=>{
    fs.appendFileSync(path.join(root,'phone-diagnostics.jsonl'),JSON.stringify({time:new Date().toISOString(),...req.body})+'\n');
    res.sendStatus(204);
});
app.use((req,res,next)=>{res.set('Cache-Control','no-store');next();});
app.get('/health', (_req,res)=>res.json({streamers: signal.streamerRegistry.count(), players: signal.playerRegistry.count()}));
// The painted world map sheet straight from the generator's output, always the one the game loaded.
app.use('/map',express.static(path.resolve(__dirname,'../../../build/yorimichi/map'),{index:false}));
app.use(express.static(path.join(root,'web'), {index:'index.html'}));
const server=http.createServer(app);
const peerOptions=JSON.parse(fs.readFileSync(path.join(root,'peer-options.json'),'utf8'));
const signal=new SignallingServer({httpServer:server,streamerPort:STREAMER_PORT,
    streamerWsOptions:{host:'127.0.0.1'},maxSubscribers:1,playerKeepaliveTimeout:10000,
    peerOptions,peerOptionsProvider:({peerType,peerId})=>{
      const host=signal.playerRegistry.get(peerId)?.request?.headers.host||'';
      if(peerType==='streamer'||/^(127\.0\.0\.1|localhost)(:|$)/.test(host)){
        const options=structuredClone(peerOptions);
        options.iceServers[0].urls=[`turn:127.0.0.1:${TURN_PORT}?transport=udp`];return options;
      }
      return peerOptions;
    }});
server.listen(HTTP_PORT,'127.0.0.1',()=>console.log(`Yorimichi player ready on 127.0.0.1:${HTTP_PORT}`));
