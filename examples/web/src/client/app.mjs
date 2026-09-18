import {requestNotes} from './client.mjs';
const style = document.createElement('style');
style.textContent = 'body{font:16px system-ui;background:#f4f5f8;color:#182334;margin:0;padding:24px}main{max-width:660px;margin:40px auto;background:white;padding:28px;border-radius:16px}label{display:block;margin:16px 0 6px}input,select,button{box-sizing:border-box;width:100%;font:inherit;padding:12px;border:1px solid #aab4c3;border-radius:8px}button{margin-top:16px;background:#2457c5;color:white;cursor:pointer}li{overflow-wrap:anywhere;padding:12px 0}small{color:#46556c}#status{min-height:24px}';
document.head.append(style);
document.body.innerHTML = `<main><small>LOCAL PIPELINE DEMONSTRATION</small><h1>Pipeline Notes</h1>
<p>Browser → API → SQLite, with executed verification evidence.</p>
<label for="role">Demo role</label><select id="role"><option value="writer">Writer</option><option value="reader">Reader</option></select>
<form><label for="title">Note title</label><input id="title" maxlength="120" required autocomplete="off"><button>Add note</button></form>
<p id="status" role="status" aria-live="polite"></p><ul aria-label="Notes"></ul></main>`;
const status = document.querySelector('#status');
const role = document.querySelector('#role');
async function refresh() {
  const notes = await requestNotes(role.value);
  const list = document.querySelector('ul'); list.replaceChildren();
  for (const note of notes) { const item = document.createElement('li'); item.textContent = note.title; list.append(item); }
  status.textContent = notes.length ? `${notes.length} notes` : 'No notes yet';
}
document.querySelector('form').addEventListener('submit', async event => {
  event.preventDefault(); status.textContent = 'Saving…';
  try { await requestNotes(role.value, document.querySelector('#title').value); await refresh(); }
  catch (error) { status.textContent = error.message; }
});
role.addEventListener('change', () => refresh().catch(error => { status.textContent = error.message; }));
refresh().catch(error => { status.textContent = error.message; });
