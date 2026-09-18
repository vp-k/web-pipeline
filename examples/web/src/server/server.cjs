'use strict';
// Deliberately local demonstration, not a production identity/authentication system.
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');

async function start(databasePath) {
  if (process.env.WEB_PIPELINE_DEMO !== '1') throw new Error('Explicit local demo mode required');
  const database = new DatabaseSync(databasePath);
  database.exec('CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY, title TEXT NOT NULL) STRICT');
  const html = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Pipeline Notes</title><body><script type="module" src="/app.mjs"></script></body></html>';
  const send = (res, status, value) => {
    res.writeHead(status, {'Content-Type':'application/json', 'Cache-Control':'no-store'});
    res.end(JSON.stringify(value));
  };
  const server = http.createServer(async (req, res) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'");
    try {
      if (req.method === 'GET' && req.url === '/') {
        res.writeHead(200, {'Content-Type':'text/html; charset=utf-8'}); res.end(html); return;
      }
      if (req.method === 'GET' && ['/app.mjs', '/client.mjs'].includes(req.url)) {
        res.writeHead(200, {'Content-Type':'text/javascript'});
        res.end(fs.readFileSync(path.join(__dirname, '../client', req.url.slice(1)))); return;
      }
      if (req.url !== '/api/notes') { send(res, 404, {error:'Not found'}); return; }
      const role = {'Bearer demo-reader-only':'reader', 'Bearer demo-writer-only':'writer'}[req.headers.authorization];
      if (!role) { send(res, 401, {error:'Sign in to the demo'}); return; }
      if (req.method === 'GET') {
        send(res, 200, {notes:database.prepare('SELECT id, title FROM notes ORDER BY id').all()}); return;
      }
      if (req.method !== 'POST') { send(res, 405, {error:'Method not allowed'}); return; }
      if (role !== 'writer') { send(res, 403, {error:'Writer access required'}); return; }
      if (req.headers.origin && req.headers.origin !== `http://127.0.0.1:${server.address().port}`) {
        send(res, 403, {error:'Origin denied'}); return;
      }
      let body = '';
      for await (const chunk of req) {
        body += chunk;
        if (Buffer.byteLength(body) > 2048) { send(res, 413, {error:'Request too large'}); return; }
      }
      let input;
      try { input = JSON.parse(body); } catch { send(res, 400, {error:'Invalid JSON'}); return; }
      if (!input || typeof input.title !== 'string' || !input.title.trim() || input.title.length > 120) {
        send(res, 400, {error:'Title must contain 1–120 characters'}); return;
      }
      const title = input.title.trim();
      const inserted = database.prepare('INSERT INTO notes(title) VALUES (?)').run(title);
      send(res, 201, {id:Number(inserted.lastInsertRowid), title});
    } catch {
      if (!res.headersSent) send(res, 500, {error:'Demo request failed'});
      else res.end();
    }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  return {url:`http://127.0.0.1:${server.address().port}`,
    close:async () => { await new Promise(resolve => server.close(resolve)); database.close(); }};
}
module.exports = {start};
if (require.main === module) {
  start(process.argv[2]).then(service => {
    process.send({url:service.url});
    process.once('message', async message => {
      if (message === 'close') { await service.close(); process.disconnect(); }
    });
    process.once('disconnect', () => process.exit(0));
  }).catch(error => { console.error(error); process.exitCode = 1; });
}
