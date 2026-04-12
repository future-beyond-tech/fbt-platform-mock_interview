/**
 * api/questions.js — Question catalogue and file-based generation.
 */

import { BASE, extractErrorDetail } from './client';

export async function fetchQuestions() {
  const res = await fetch(`${BASE}/api/questions`);
  if (!res.ok) throw new Error('Failed to load questions');
  return res.json();
}

export async function generateQuestions(provider, apiKey, model, topic = '', count = 3) {
  const res = await fetch(`${BASE}/api/generate-questions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider: provider || 'groq', api_key: apiKey || '', model: model || '', topic, count }),
  });
  if (!res.ok) throw new Error((await extractErrorDetail(res)) || `Generation failed (${res.status})`);
  return res.json(); // { questions: [...] }
}

export async function generateFromFile(file, provider, apiKey, model) {
  const form = new FormData();
  form.append('file', file);
  form.append('provider', provider || 'groq');
  form.append('api_key', apiKey || '');
  form.append('model', model || '');

  const res = await fetch(`${BASE}/api/generate-from-file`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) throw new Error((await extractErrorDetail(res)) || `File question generation failed (${res.status})`);
  return res.json(); // { questions: [{ id, q, s, day }] }
}
