/**
 * api/interview.js — Structured interview session API calls.
 */

import { BASE, extractErrorDetail } from './client';

export async function startInterview(file, provider, apiKey, model) {
  const form = new FormData();
  form.append('file', file);
  form.append('provider', provider || 'gemini');
  form.append('api_key', apiKey || '');
  form.append('model', model || '');

  const res = await fetch(`${BASE}/api/interview/start`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) throw new Error((await extractErrorDetail(res)) || `Interview start failed (${res.status})`);
  return res.json(); // { session_id, question, section, state }
}

export async function enqueueInterviewProbe(
  sessionId,
  originalQuestion,
  userAnswer,
  category,
  provider,
  apiKey,
  model,
) {
  const res = await fetch(`${BASE}/api/interview/enqueue-probe`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      original_question: originalQuestion,
      user_answer: userAnswer,
      category,
      provider: provider || 'gemini',
      api_key: apiKey || '',
      model: model || '',
    }),
  });
  if (!res.ok) throw new Error((await extractErrorDetail(res)) || `Enqueue failed (${res.status})`);
  return res.json();
}

export async function interviewTurn(sessionId, answer, provider, apiKey, model) {
  const res = await fetch(`${BASE}/api/interview/turn`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      answer,
      provider: provider || 'gemini',
      api_key: apiKey || '',
      model: model || '',
    }),
  });
  if (!res.ok) throw new Error((await extractErrorDetail(res)) || `Interview turn failed (${res.status})`);
  return res.json(); // { question, section, state }
}

export async function getInterviewReport(sessionId, provider, apiKey, model, answers = []) {
  const res = await fetch(`${BASE}/api/interview/report`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      provider: provider || 'gemini',
      api_key: apiKey || '',
      model: model || '',
      answers,
    }),
  });
  if (!res.ok) throw new Error((await extractErrorDetail(res)) || `Report generation failed (${res.status})`);
  return res.json();
}

export async function endInterview(sessionId) {
  const form = new FormData();
  form.append('session_id', sessionId);
  try {
    await fetch(`${BASE}/api/interview/end`, { method: 'POST', body: form });
  } catch {
    // Best effort — ignore failures.
  }
}
