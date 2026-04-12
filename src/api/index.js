/**
 * api/index.js — Barrel re-exporting all feature API modules.
 *
 * Import from 'src/api' (this file) to access all API functions,
 * or import directly from a feature module for tree-shaking.
 */

export { BASE, extractErrorDetail } from './client';

export {
  evaluateAnswer,
  generateFollowUp,
  evaluateFollowUp,
} from './evaluation';

export {
  fetchQuestions,
  generateQuestions,
  generateFromFile,
} from './questions';

export {
  startInterview,
  enqueueInterviewProbe,
  interviewTurn,
  getInterviewReport,
  endInterview,
} from './interview';

export {
  transcribeAudio,
  cleanTranscript,
} from './transcription';

// ── Core utilities (health + providers) ──────────────────────────────────────

const BASE_URL = import.meta.env.VITE_API_URL || '';

export async function fetchProviders() {
  const res = await fetch(`${BASE_URL}/api/providers`);
  if (!res.ok) throw new Error('Failed to load providers');
  return res.json();
}

export async function healthCheck() {
  try {
    const res = await fetch(`${BASE_URL}/api/health`);
    if (!res.ok) throw new Error('Health check failed');
    return res.json();
  } catch {
    return { status: 'unreachable', ollama: false };
  }
}
