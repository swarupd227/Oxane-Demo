// Serves a production build of the web app and proxies /api to the running API, for recording.
// Usage: node serve.mjs <dist folder>   (port 5184, API on 8010)
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';

const DIST = path.resolve(process.argv[2] || '../apps/web/dist');
const PORT = Number(process.env.PORT || 5184);
const API = { host: '127.0.0.1', port: Number(process.env.API_PORT || 8010) };
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2', '.json': 'application/json',
  '.pfb': 'application/octet-stream', '.ttf': 'font/ttf', '.wasm': 'application/wasm' };

http.createServer((req, res) => {
  if (req.url.startsWith('/api')) {
    const upstream = http.request({ ...API, path: req.url, method: req.method, headers: req.headers }, (answer) => {
      res.writeHead(answer.statusCode, answer.headers);
      answer.pipe(res);
    });
    upstream.on('error', () => { res.writeHead(502); res.end('API unavailable'); });
    req.pipe(upstream);
    return;
  }
  const clean = decodeURIComponent(req.url.split('?')[0]);
  let file = path.join(DIST, clean);
  if (!file.startsWith(DIST) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(DIST, 'index.html');
  res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
}).listen(PORT, '127.0.0.1', () => console.log(`serving ${DIST} on http://127.0.0.1:${PORT}`));
