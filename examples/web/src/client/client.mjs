export function decodeNotes(value) {
  if (!value || !Array.isArray(value.notes) || value.notes.some(note =>
    !Number.isInteger(note.id) || note.id < 1 || typeof note.title !== 'string')) {
    throw new Error('Invalid API response');
  }
  return value.notes;
}

export async function requestNotes(role, title) {
  const headers = {'Authorization':`Bearer demo-${role}-only`};
  const response = await fetch('/api/notes', title === undefined ? {headers} : {
    method:'POST', headers:{...headers, 'Content-Type':'application/json'}, body:JSON.stringify({title})});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || 'Request failed');
  return title === undefined ? decodeNotes(value) : value;
}
