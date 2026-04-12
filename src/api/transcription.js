/**
 * api/transcription.js — Audio transcription and transcript cleanup.
 */

import { BASE } from './client';

export async function transcribeAudio(audioBlob, groqApiKey) {
  const form = new FormData();
  form.append('audio', audioBlob, 'recording.webm');
  form.append('groq_api_key', groqApiKey);

  const res = await fetch(`${BASE}/api/transcribe`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    let detail;
    try { const d = await res.json(); detail = d.detail; } catch { detail = await res.text(); }
    throw new Error(detail || `Transcription failed (${res.status})`);
  }
  const data = await res.json();
  return data.text || '';
}

export async function cleanTranscript(rawTranscript, provider, apiKey, model) {
  if (!rawTranscript || rawTranscript.trim().length < 15) return rawTranscript;
  try {
    const res = await fetch(`${BASE}/api/clean-transcript`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raw_transcript: rawTranscript,
        provider: provider || 'groq',
        api_key: apiKey || '',
        model: model || '',
      }),
    });
    if (!res.ok) return rawTranscript; // non-fatal
    const data = await res.json();
    return data.text || rawTranscript;
  } catch {
    return rawTranscript; // non-fatal
  }
}
