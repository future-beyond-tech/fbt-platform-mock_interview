/**
 * store/useSessionStore.js — Zustand store for the practice-session state.
 *
 * Extracts the 15-field useState from App.jsx into a global store so
 * App.jsx becomes a thin phase-router.  All session logic (start, skip,
 * submit, done) lives here as actions rather than inline callbacks.
 */

import { create } from 'zustand';

function getStats(history) {
  const ans = history.filter(h => h.verdict !== 'skipped');
  const avg = ans.length
    ? Math.round(ans.reduce((a, b) => a + b.score, 0) / ans.length)
    : 0;
  return {
    correct: history.filter(h => h.verdict === 'correct').length,
    partial:  history.filter(h => h.verdict === 'partial').length,
    incorrect: history.filter(h => h.verdict === 'incorrect').length,
    skipped: history.filter(h => h.verdict === 'skipped').length,
    avg,
    answered: ans.length,
  };
}

const INITIAL = {
  phase: 'start',         // 'start' | 'question' | 'thinking' | 'result' | 'done' | 'interview'
  session: [],            // questions in the current practice round
  sessions: [],           // available session descriptors (from API)
  questions: [],          // full question catalogue (from API)
  providers: [],          // provider list (from API)
  health: null,
  idx: 0,
  draftAnswer: '',
  submittedAnswer: '',
  result: null,
  history: [],
  attempts: 0,
  showIdeal: false,
  retrySession: [],
  loading: true,
  settingsOpen: false,
  errorMessage: '',
  interviewSession: null, // { sessionId, question, section, state, … }
};

export const useSessionStore = create((set, get) => ({
  ...INITIAL,

  // ── Data loading ────────────────────────────────────────────────────────────

  setLoading: (loading) => set({ loading }),

  setInitialData: ({ questions, sessions, providers, health }) =>
    set({ questions, sessions, providers, health, loading: false, errorMessage: '' }),

  setError: (errorMessage) =>
    set({ health: { status: 'unreachable', ollama: false }, loading: false, errorMessage }),

  dismissError: () => set({ errorMessage: '' }),

  // ── Settings drawer ─────────────────────────────────────────────────────────

  openSettings:  () => set({ settingsOpen: true }),
  closeSettings: () => set({ settingsOpen: false }),

  // ── Phase transitions ───────────────────────────────────────────────────────

  goStart: () =>
    set({ phase: 'start', draftAnswer: '', submittedAnswer: '', result: null, showIdeal: false, errorMessage: '' }),

  setInterviewSession: (interviewSession) =>
    set({ phase: 'interview', interviewSession, loading: false }),

  clearInterviewSession: () =>
    set({ phase: 'start', interviewSession: null }),

  // ── Practice session ────────────────────────────────────────────────────────

  startSession: (sessionId) => {
    const { sessions, questions } = get();
    const sess = sessions.find(x => x.id === sessionId);
    if (!sess) {
      set({ errorMessage: 'That session is no longer available. Refresh and try again.' });
      return;
    }
    const qs = sess.filter
      ? questions.filter(q => q.day === sess.filter)
      : questions.slice();

    set({
      phase: 'question',
      session: qs,
      retrySession: qs.slice(),
      idx: 0,
      draftAnswer: '',
      submittedAnswer: '',
      result: null,
      history: [],
      attempts: 0,
      showIdeal: false,
      errorMessage: '',
    });
  },

  startAISession: (questions) =>
    set({
      phase: 'question',
      session: questions,
      retrySession: questions.slice(),
      idx: 0,
      draftAnswer: '',
      history: [],
      attempts: 0,
      submittedAnswer: '',
      result: null,
      showIdeal: false,
    }),

  retryAll: () => {
    const { retrySession } = get();
    set({
      phase: 'question',
      session: retrySession,
      idx: 0,
      history: [],
      attempts: 0,
      draftAnswer: '',
      submittedAnswer: '',
      result: null,
      showIdeal: false,
    });
  },

  setDraftAnswer: (draftAnswer) => set({ draftAnswer }),

  setSubmittedAnswer: (submittedAnswer) => set({ submittedAnswer }),

  setPhase: (phase) => set({ phase }),

  setResult: (result, attempts) => {
    const { history, session, idx } = get();
    const q = session[idx];
    const newAttempts = attempts ?? get().attempts + 1;
    const entry = { qId: q.id, verdict: result.verdict, score: result.score, attempts: newAttempts };
    const next = [...history];
    const ei = next.findIndex(h => h.qId === q.id);
    if (ei >= 0) next[ei] = entry; else next.push(entry);
    set({ result, history: next, attempts: newAttempts, phase: 'result' });
  },

  skipQ: () => {
    const { session, idx, history } = get();
    const q = session[idx];
    const entry = { qId: q.id, verdict: 'skipped', score: 0, attempts: 0 };
    const next = [...history];
    const ei = next.findIndex(h => h.qId === entry.qId);
    if (ei >= 0) next[ei] = entry; else next.push(entry);

    if (idx + 1 >= session.length) {
      set({ history: next, phase: 'done', retrySession: session.slice() });
    } else {
      set({ history: next, idx: idx + 1, attempts: 0, draftAnswer: '', submittedAnswer: '', result: null, showIdeal: false, phase: 'question' });
    }
  },

  nextQ: () => {
    const { session, idx } = get();
    if (idx + 1 >= session.length) {
      set({ phase: 'done', retrySession: session.slice() });
    } else {
      set({ idx: idx + 1, attempts: 0, draftAnswer: '', submittedAnswer: '', result: null, showIdeal: false, phase: 'question' });
    }
  },

  retryQ: () =>
    set({ draftAnswer: '', submittedAnswer: '', result: null, showIdeal: false, phase: 'question' }),

  toggleIdeal: () => set(state => ({ showIdeal: !state.showIdeal })),

  // ── Derived ─────────────────────────────────────────────────────────────────

  getStats: () => getStats(get().history),
}));
