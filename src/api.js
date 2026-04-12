/**
 * api.js — Backward-compatibility barrel.
 *
 * Phase 8: API functions have been split into src/api/ feature modules.
 * This file re-exports everything so existing imports (App.jsx, hooks, etc.)
 * continue to work without change.
 *
 * Prefer importing directly from the feature modules in new code:
 *   import { evaluateAnswer } from './api/evaluation';
 *   import { interviewTurn }  from './api/interview';
 */

export {
  BASE,
  extractErrorDetail,
  evaluateAnswer,
  generateFollowUp,
  evaluateFollowUp,
  fetchQuestions,
  generateQuestions,
  generateFromFile,
  startInterview,
  enqueueInterviewProbe,
  interviewTurn,
  getInterviewReport,
  endInterview,
  transcribeAudio,
  cleanTranscript,
  fetchProviders,
  healthCheck,
} from './api/index';
