/**
 * api/evaluation.js — Evaluation and follow-up API calls.
 */

import { BASE, extractErrorDetail } from './client';

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
  if (!res.ok) throw new Error((await extractErrorDetail(res)) || `Evaluation failed (${res.status})`);
  return res.json();
}

export async function generateFollowUp(originalQuestion, userAnswer, provider, apiKey, model, opts = {}) {
  const res = await fetch(`${BASE}/api/generate-followup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      original_question: originalQuestion,
      user_answer: userAnswer,
      topic: opts.topic || '',
      provider: provider || 'groq',
      api_key: apiKey || '',
      model: model || '',
      profile: opts.profile || null,
      interview_session_id: opts.interviewSessionId || '',
    }),
  });
  if (!res.ok) throw new Error((await extractErrorDetail(res)) || `Follow-up generation failed (${res.status})`);
  return res.json();
}

export async function evaluateFollowUp(
  originalQuestion,
  followUpQuestion,
  answer,
  provider,
  apiKey,
  model,
  opts = {},
) {
  const res = await fetch(`${BASE}/api/evaluate-followup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      original_question: originalQuestion,
      follow_up_question: followUpQuestion,
      answer,
      provider: provider || 'groq',
      api_key: apiKey || '',
      model: model || '',
      profile: opts.profile || null,
      interview_session_id: opts.interviewSessionId || '',
    }),
  });
  if (!res.ok) throw new Error((await extractErrorDetail(res)) || `Follow-up evaluation failed (${res.status})`);
  return res.json();
}
