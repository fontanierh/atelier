// The stream's web server: Epic's signalling protocol plus the pages, on loopback only. `atelier stream` starts it;
// Tailscale Serve (or another private proxy) is the only way in from other devices. No public port, no cloud service.
//   ATELIER_STREAM_OUTPUT   build/<game>/stream: web/ (the pages), peer-options.json, logs
//   ATELIER_STREAM_HTTP_PORT, ATELIER_STREAM_STREAMER_PORT, ATELIER_STREAM_TURN_PORT
//   ATELIER_STREAM_ROUTES   JSON {"<route>": "<folder>"}: extra static folders (a game's map sheet)
const http = require('node:http');
const path = require('node:path');
const fs = require('node:fs');
const express = require('express');
const {SignallingServer, InitLogging} = require('@epicgames-ps/lib-pixelstreamingsignalling-ue5.8');
const root = path.resolve(process.env.ATELIER_STREAM_OUTPUT);
const HTTP_PORT = Number(process.env.ATELIER_STREAM_HTTP_PORT || 8080);
const STREAMER_PORT = Number(process.env.ATELIER_STREAM_STREAMER_PORT || 8888);
const TURN_PORT = Number(process.env.ATELIER_STREAM_TURN_PORT || 3478);
const routes = JSON.parse(process.env.ATELIER_STREAM_ROUTES || '{}');
InitLogging({logDir: path.join(root, 'logs'), logLevelConsole: 'info'});
const app = express();
app.disable('x-powered-by');
app.post('/diagnostics', express.json({limit: '16kb'}), (req, res) => {
    fs.appendFileSync(path.join(root, 'diagnostics.jsonl'), JSON.stringify({time: new Date().toISOString(), ...req.body}) + '\n');
    res.sendStatus(204);
});
app.use((req, res, next) => {res.set('Cache-Control', 'no-store'); next();});
app.get('/health', (_req, res) => res.json({streamers: signal.streamerRegistry.count(), players: signal.playerRegistry.count()}));
for (const [route, folder] of Object.entries(routes)) app.use('/' + route, express.static(path.resolve(folder), {index: false}));
app.use(express.static(path.join(root, 'web'), {index: 'index.html'}));
const server = http.createServer(app);
const peerOptions = JSON.parse(fs.readFileSync(path.join(root, 'peer-options.json'), 'utf8'));
const signal = new SignallingServer({httpServer: server, streamerPort: STREAMER_PORT,
    streamerWsOptions: {host: '127.0.0.1'}, maxSubscribers: 1, playerKeepaliveTimeout: 10000,
    peerOptions, peerOptionsProvider: ({peerType, peerId}) => {
        // The game and pages opened on this machine reach the relay on loopback; other devices through the proxy.
        const host = signal.playerRegistry.get(peerId)?.request?.headers.host || '';
        if (peerType === 'streamer' || /^(127\.0\.0\.1|localhost)(:|$)/.test(host)) {
            const options = structuredClone(peerOptions);
            options.iceServers[0].urls = [`turn:127.0.0.1:${TURN_PORT}?transport=udp`]; return options;
        }
        return peerOptions;
    }});
server.listen(HTTP_PORT, '127.0.0.1', () => console.log(`Stream pages ready on 127.0.0.1:${HTTP_PORT}`));
