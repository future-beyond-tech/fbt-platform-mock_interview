/**
 * API client — multi-provider backend.
 */
const BASE = import.meta.env.VITE_API_URL || '';

export async function fetchQuestions() {
  const res = await fetch(`${BASE}/api/questions`);
  if (!res.ok) throw new Error('Failed to load questions');
  return res.json();
}

export async function fetchProviders() {
  const res = await fetch(`${BASE}/api/providers`);
  if (!res.ok) throw new Error('Failed to load providers');
  return res.json();
}

export async function evaluateAnswer(questionId, answer, provider, apiKey, model, opts = {}) {
  const res = await fetch(`${BASE}/api/evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question_id: questionId,
      answer,
      provider: provider || 'ollama',
      api_key: apiKey || '',
      model: model || '',
      question_text: opts.questionText || '',
      section: opts.section || '',
      interview_session_id: opts.interviewSessionId || '',
      profile: opts.profile || null,
    }),
  });
  if (!res.ok) {
    let detail;
    try { const d = await res.json(); detail = d.detail; } catch { detail = await res.text(); }
    throw new Error(detail || `Evaluation failed (${res.status})`);
  }
  return res.json();
}

export async function generateQuestions(provider, apiKey, model, topic = '', count = 3) {
  const res = await fetch(`${BASE}/api/generate-questions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider: provider || 'groq', api_key: apiKey || '', model: model || '', topic, count }),
  });
  if (!res.ok) {
    let detail;
    try { const d = await res.json(); detail = d.detail; } catch { detail = await res.text(); }
    throw new Error(detail || `Generation failed (${res.status})`);
  }
  return res.json(); // { questions: [...] }
}

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
  if (!res.ok) {
    let detail;
    try { const d = await res.json(); detail = d.detail; } catch { detail = await res.text(); }
    throw new Error(detail || `Interview start failed (${res.status})`);
  }
  return res.json(); // { session_id, question, section, state }
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
  if (!res.ok) {
    let detail;
    try { const d = await res.json(); detail = d.detail; } catch { detail = await res.text(); }
    throw new Error(detail || `Interview turn failed (${res.status})`);
  }
  return res.json(); // { question, section, state }
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
  if (!res.ok) {
    let detail;
    try { const d = await res.json(); detail = d.detail; } catch { detail = await res.text(); }
    throw new Error(detail || `File question generation failed (${res.status})`);
  }
  return res.json(); // { questions: [{ id, q, s, day }] }
}

export async function healthCheck() {
  try {
    const res = await fetch(`${BASE}/api/health`);
    if (!res.ok) throw new Error('Health check failed');
    return res.json();
  } catch {
    return { status: 'unreachable', ollama: false };
  }
}
