const {test, expect} = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const {fork} = require('node:child_process');
const contract = require('../src/shared/contract.json');
let service;
const headers = role => ({Authorization:`Bearer demo-${role}-only`});
async function start(databasePath) {
  const child = fork(path.join(__dirname, '../src/server/server.cjs'), [databasePath], {
    execArgv:[], env:{...process.env,WEB_PIPELINE_DEMO:'1'}, silent:true
  });
  const log = fs.createWriteStream(path.join(process.env.PIPELINE_EVIDENCE_DIR, 'artifacts/server.log'), {flags:'a'});
  child.stdout.pipe(log, {end:false}); child.stderr.pipe(log, {end:false});
  child.once('exit', () => log.end());
  const exited = new Promise(resolve => child.once('exit', resolve));
  const timer = setTimeout(() => child.kill(), 10000);
  try {
    const url = await new Promise((resolve, reject) => {
      child.once('message', message => resolve(message.url));
      child.once('error', reject);
      child.once('exit', code => reject(new Error(`Demo server exited before ready: ${code}`)));
    });
    return {url, close:async () => {
      const timeout = setTimeout(() => child.kill(), 5000);
      if (child.connected) child.send('close');
      await exited; clearTimeout(timeout);
    }};
  } finally { clearTimeout(timer); }
}
test.beforeAll(async () => {
  process.env.WEB_PIPELINE_DEMO = '1';
  service = await start(path.join(process.env.PIPELINE_EVIDENCE_DIR, 'artifacts/notes.sqlite'));
});
test.afterAll(async () => { if (service) await service.close(); });

test('[provider] real responses follow the contract', async ({request}) => {
  const response = await request.post(service.url + '/api/notes', {headers:headers('writer'), data:{title:'Provider note'}});
  expect(response.status()).toBe(contract.statuses.create);
  const item = await response.json();
  expect(Number.isInteger(item.id)).toBe(true); expect(typeof item.title).toBe(contract.required.title);
  const list = await request.get(service.url + '/api/notes', {headers:headers('reader')});
  expect(list.status()).toBe(contract.statuses.list);
  expect((await list.json())[contract.collection]).toContainEqual(item);
});
test('[consumer] decoder rejects malformed responses', async () => {
  const {decodeNotes} = await import('../src/client/client.mjs');
  expect(decodeNotes({notes:[{id:1,title:'Valid'}]})).toHaveLength(1);
  for (const input of [{}, {notes:null}, {notes:[{id:'1',title:'wrong'}]}, {notes:[{id:1}]}]) {
    expect(() => decodeNotes(input)).toThrow('Invalid API response');
  }
});
test('[compatibility] version-one contract remains compatible', () => {
  expect(contract.collection).toBe('notes');
  expect(contract.required).toEqual({id:'integer', title:'string'});
  expect(contract.statuses).toEqual({list:200,create:201,unauthenticated:401,forbidden:403,invalid:400});
});
test('[security] authentication, role, origin and input denial', async ({request}) => {
  expect((await request.get(service.url + '/api/notes')).status()).toBe(401);
  expect((await request.post(service.url + '/api/notes', {headers:headers('reader'),data:{title:'Denied'}})).status()).toBe(403);
  expect((await request.post(service.url + '/api/notes', {headers:{...headers('writer'),Origin:'https://invalid.example'},data:{title:'Denied'}})).status()).toBe(403);
  expect((await request.post(service.url + '/api/notes', {headers:headers('writer'),data:{title:''}})).status()).toBe(400);
});
test('[database] committed data survives a server restart', async ({request}) => {
  const url = service.url;
  await request.post(url + '/api/notes', {headers:headers('writer'), data:{title:'Persistent note'}});
  await service.close();
  service = await start(path.join(process.env.PIPELINE_EVIDENCE_DIR, 'artifacts/notes.sqlite'));
  const response = await request.get(service.url + '/api/notes', {headers:headers('reader')});
  expect((await response.json()).notes.some(note => note.title === 'Persistent note')).toBe(true);
});
test('[browser] desktop/mobile create, reload, denied action and safe text', async ({browser}) => {
  const shots = [], errors = [];
  for (const viewport of [{kind:'desktop',width:1440,height:900},{kind:'mobile',width:390,height:844}]) {
    const context = await browser.newContext({viewport:{width:viewport.width,height:viewport.height}});
    const page = await context.newPage(); page.on('pageerror', error => errors.push(error.message));
    try {
      await page.goto(service.url);
      await expect(page.getByRole('heading', {name:/Pipeline Notes/})).toBeVisible();
      const title = `<img src=x> ${viewport.kind}`;
      await page.getByLabel('Note title').fill(title); await page.getByRole('button', {name:'Add note'}).click();
      await expect(page.getByRole('listitem').filter({hasText:title})).toBeVisible();
      await page.reload(); await expect(page.getByRole('listitem').filter({hasText:title})).toBeVisible();
      await expect(page.locator('img')).toHaveCount(0);
      await page.getByLabel('Demo role').selectOption('reader');
      await page.getByLabel('Note title').fill('Not allowed'); await page.getByRole('button', {name:'Add note'}).click();
      await expect(page.getByRole('status')).toHaveText('Writer access required');
      const relative = `screenshots/notes-${viewport.kind}.png`;
      fs.mkdirSync(path.join(process.env.PIPELINE_EVIDENCE_DIR, 'screenshots'), {recursive:true});
      await page.screenshot({path:path.join(process.env.PIPELINE_EVIDENCE_DIR, relative)});
      shots.push({...viewport,path:relative,url:service.url});
    } finally { await context.close(); }
  }
  expect(errors).toEqual([]);
  fs.writeFileSync(path.join(process.env.PIPELINE_EVIDENCE_DIR, 'screenshots/manifest.json'), JSON.stringify(shots));
});
