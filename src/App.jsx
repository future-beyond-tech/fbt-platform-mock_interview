import { useState, useCallback, useEffect, lazy, Suspense } from 'react';
import { fetchQuestions, fetchProviders, evaluateAnswer, generateQuestions, startInterview, healthCheck, cleanTranscript } from './api';
import { useSettings } from './hooks/useSettings';
import StatusBar from './components/StatusBar';
import UploadPage from './components/UploadPage';
import { Alert, Button, LaunchLoader, SessionScreenSkeleton } from './components/ui';

// Lazy-load heavy, non-critical route chunks so initial FCP/LCP paints
// structure-only (no canvas, no interview session, no score reveal).
const Particles         = lazy(() => import('./components/Particles'));
const SettingsDrawer    = lazy(() => import('./components/SettingsDrawer'));
const SessionScreen     = lazy(() => import('./components/SessionScreen'));
const DoneScreen        = lazy(() => import('./components/DoneScreen'));
const InterviewSession  = lazy(() => import('./components/InterviewSession'));

function getStats(history) {
  const ans = history.filter(h => h.verdict !== 'skipped');
  const avg = ans.length ? Math.round(ans.reduce((a, b) => a + b.score, 0) / ans.length) : 0;
  return {
    correct: history.filter(h => h.verdict === 'correct').length,
    partial: history.filter(h => h.verdict === 'partial').length,
    incorrect: history.filter(h => h.verdict === 'incorrect').length,
    skipped: history.filter(h => h.verdict === 'skipped').length,
    avg,
    answered: ans.length,
  };
}

const initial = {
  phase: 'start',
  session: [],
  sessions: [],
  questions: [],
  providers: [],
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
  interviewSession: null, // { sessionId, question, section, state }
};

export default function App() {
  const [s, setS] = useState(initial);
  const { settings, update: updateSettings } = useSettings();

  const loadInitialData = useCallback(async () => {
    setS(prev => ({ ...prev, loading: true, errorMessage: '' }));

    try {
      const [qData, pData, health] = await Promise.all([
        fetchQuestions(),
        fetchProviders(),
        healthCheck(),
      ]);

      setS(prev => ({
        ...prev,
        questions: qData.questions,
        sessions: qData.sessions,
        providers: pData.providers,
        health,
        loading: false,
        errorMessage: '',
      }));
    } catch {
      setS(prev => ({
        ...prev,
        health: { status: 'unreachable', ollama: false },
        loading: false,
        errorMessage: 'Could not connect to the backend. Start the API server and retry.',
      }));
    }
  }, []);

  useEffect(() => {
    void loadInitialData();
  }, [loadInitialData]);

  const currentProvider = s.providers.find(p => p.id === settings.provider);

  const startSession = useCallback((id) => {
    setS(prev => {
      const sess = prev.sessions.find(x => x.id === id);
      if (!sess) {
        return { ...prev, errorMessage: 'That session is no longer available. Refresh and try again.' };
      }

      const questions = sess.filter
        ? prev.questions.filter(q => q.day === sess.filter)
        : prev.questions.slice();

      return {
        ...prev,
        phase: 'question',
        session: questions,
        retrySession: questions.slice(),
        idx: 0,
        draftAnswer: '',
        submittedAnswer: '',
        result: null,
        history: [],
        attempts: 0,
        showIdeal: false,
        errorMessage: '',
      };
    });
  }, []);

  const goStart = useCallback(() => setS(prev => ({
    ...prev,
    phase: 'start',
    draftAnswer: '',
    submittedAnswer: '',
    result: null,
    showIdeal: false,
    errorMessage: '',
  })), []);

  const startFileSession = useCallback(async (file) => {
    setS(prev => ({ ...prev, loading: true, errorMessage: '' }));
    try {
      const data = await startInterview(
        file,
        settings.provider,
        settings.apiKey,
        settings.model,
      );
      setS(prev => ({
        ...prev,
        loading: false,
        phase: 'interview',
        interviewSession: {
          sessionId: data.session_id,
          question: data.question,
          section: data.section,
          category: data.category,
          questionNumber: data.question_number,
          totalQuestions: data.total_questions,
          whatToEvaluate: data.what_to_evaluate,
          state: data.state,
          profile: data.profile,
          blueprint: data.blueprint,
        },
      }));
    } catch (e) {
      setS(prev => ({ ...prev, loading: false }));
      throw e;
    }
  }, [settings]);

  const startAISession = useCallback(async (topic, count) => {
    setS(prev => ({ ...prev, loading: true, errorMessage: '' }));
    try {
      const data = await generateQuestions(
        settings.provider,
        settings.apiKey,
        settings.model,
        topic,
        count,
      );
      setS(prev => ({
        ...prev,
        loading: false,
        phase: 'question',
        session: data.questions,
        retrySession: data.questions.slice(),
        idx: 0,
        draftAnswer: '',
        history: [],
        attempts: 0,
        submittedAnswer: '',
        result: null,
        showIdeal: false,
      }));
    } catch (e) {
      setS(prev => ({
        ...prev,
        loading: false,
        errorMessage: `Failed to generate questions: ${e.message}`,
      }));
    }
  }, [settings]);

  const openSettings = useCallback(() => setS(prev => ({ ...prev, settingsOpen: true })), []);
  const closeSettings = useCallback(() => setS(prev => ({ ...prev, settingsOpen: false })), []);

  const skipQ = useCallback(() => {
    setS(prev => {
      const entry = { qId: prev.session[prev.idx].id, verdict: 'skipped', score: 0, attempts: 0 };
      const history = [...prev.history];
      const existingIndex = history.findIndex(h => h.qId === entry.qId);
      if (existingIndex >= 0) history[existingIndex] = entry; else history.push(entry);

      if (prev.idx + 1 >= prev.session.length) {
        return { ...prev, history, phase: 'done', retrySession: prev.session.slice() };
      }

      return {
        ...prev,
        history,
        idx: prev.idx + 1,
        attempts: 0,
        draftAnswer: '',
        submittedAnswer: '',
        result: null,
        showIdeal: false,
        phase: 'question',
      };
    });
  }, []);

  const nextQ = useCallback(() => {
    setS(prev => {
      if (prev.idx + 1 >= prev.session.length) {
        return { ...prev, phase: 'done', retrySession: prev.session.slice() };
      }

      return {
        ...prev,
        idx: prev.idx + 1,
        attempts: 0,
        draftAnswer: '',
        submittedAnswer: '',
        result: null,
        showIdeal: false,
        phase: 'question',
      };
    });
  }, []);

  const retryQ = useCallback(() => {
    setS(prev => ({ ...prev, draftAnswer: '', submittedAnswer: '', result: null, showIdeal: false, phase: 'question' }));
  }, []);

  const toggleIdeal = useCallback(() => {
    setS(prev => ({ ...prev, showIdeal: !prev.showIdeal }));
  }, []);

  const submitAnswer = useCallback(async (text) => {
    const q = s.session[s.idx];
    if (!q) return;

    setS(prev => ({ ...prev, draftAnswer: text, submittedAnswer: text, phase: 'thinking' }));

    // Clean up voice transcription errors before scoring.
    const cleaned = await cleanTranscript(text, settings.provider, settings.apiKey, settings.model);
    if (cleaned && cleaned !== text) {
      setS(prev => ({ ...prev, submittedAnswer: cleaned }));
    }
    const answerToEval = cleaned || text;

    let result;
    try {
      result = await evaluateAnswer(
        q.id,
        answerToEval,
        settings.provider,
        settings.apiKey,
        settings.model,
      );
      result.score = Math.max(0, Math.min(100, Math.round(result.score)));
    } catch (e) {
      result = {
        score: 0,
        verdict: 'incorrect',
        strength: 'Evaluation error — try again.',
        missing: e.message.slice(0, 200),
        hint: '',
        ideal: '',
      };
    }

    setS(prev => {
      const newAttempts = prev.attempts + 1;
      const history = [...prev.history];
      const entry = { qId: q.id, verdict: result.verdict, score: result.score, attempts: newAttempts };
      const existingIndex = history.findIndex(h => h.qId === q.id);
      if (existingIndex >= 0) history[existingIndex] = entry; else history.push(entry);
      return { ...prev, result, history, attempts: newAttempts, phase: 'result' };
    });
  }, [s.session, s.idx, settings]);

  const stats = getStats(s.history);

  const dismissError = useCallback(
    () => setS(prev => ({ ...prev, errorMessage: '' })),
    [],
  );

  return (
    <div className="app">
      <Suspense fallback={null}>
        <Particles />
      </Suspense>

      <a className="t-skip-link" href="#main-content">Skip to main content</a>

      <div className="app-content">
        <header className="app-header">
          <StatusBar
            provider={currentProvider}
            settings={settings}
            health={s.health}
            onOpenSettings={openSettings}
          />
        </header>

        <main id="main-content" className="app-main t-anim-fade" tabIndex={-1}>
        {s.errorMessage && (
          <div className="app-alert-slot">
            <Alert
              tone="danger"
              title="Something went wrong"
              actions={
                <Button variant="secondary" size="sm" onClick={() => void loadInitialData()}>
                  Retry
                </Button>
              }
            >
              {s.errorMessage}
            </Alert>
            <button type="button" className="t-sr-only" onClick={dismissError}>Dismiss error</button>
          </div>
        )}

        {s.loading && <LaunchLoader label="Preparing your interview" />}

        {!s.loading && s.phase === 'start' && (
          <UploadPage onGenerateFromFile={startFileSession} />
        )}
        {!s.loading && s.phase === 'interview' && s.interviewSession && (
          <Suspense fallback={<SessionScreenSkeleton />}>
            <InterviewSession
              sessionId={s.interviewSession.sessionId}
              initialQuestion={s.interviewSession.question}
              initialSection={s.interviewSession.section}
              initialCategory={s.interviewSession.category}
              initialQuestionNumber={s.interviewSession.questionNumber}
              totalQuestions={s.interviewSession.totalQuestions}
              initialWhatToEvaluate={s.interviewSession.whatToEvaluate}
              initialState={s.interviewSession.state}
              initialProfile={s.interviewSession.profile}
              initialBlueprint={s.interviewSession.blueprint}
              settings={settings}
              groqApiKey={settings.provider === 'groq' ? settings.apiKey : (import.meta.env.VITE_GROQ_API_KEY || '')}
              onGoStart={() => setS(prev => ({ ...prev, phase: 'start', interviewSession: null }))}
              onComplete={() => setS(prev => ({ ...prev, phase: 'start', interviewSession: null }))}
            />
          </Suspense>
        )}
        {!s.loading && s.phase === 'done' && (
          <Suspense fallback={<SessionScreenSkeleton />}>
            <DoneScreen
              stats={stats}
              onNewSession={goStart}
              onRetry={() => setS(prev => ({
                ...prev,
                phase: 'question',
                session: prev.retrySession,
                idx: 0,
                history: [],
                attempts: 0,
                draftAnswer: '',
                submittedAnswer: '',
                result: null,
                showIdeal: false,
              }))}
            />
          </Suspense>
        )}
        {!s.loading && ['question', 'thinking', 'result'].includes(s.phase) && (
          <Suspense fallback={<SessionScreenSkeleton />}>
          <SessionScreen
            session={s.session}
            idx={s.idx}
            phase={s.phase}
            draftAnswer={s.draftAnswer}
            submittedAnswer={s.submittedAnswer}
            result={s.result}
            showIdeal={s.showIdeal}
            attempts={s.attempts}
            stats={stats}
            onDraftChange={(draftAnswer) => setS(prev => ({ ...prev, draftAnswer }))}
            onSubmit={submitAnswer}
            onNext={nextQ}
            onSkip={skipQ}
            onRetry={retryQ}
            onToggleIdeal={toggleIdeal}
            onGoStart={goStart}
            groqApiKey={settings.provider === 'groq' ? settings.apiKey : ''}
          />
          </Suspense>
        )}
        </main>
      </div>

      {s.settingsOpen && (
        <Suspense fallback={null}>
          <SettingsDrawer
            open={s.settingsOpen}
            onClose={closeSettings}
            settings={settings}
            onUpdate={updateSettings}
            providers={s.providers}
          />
        </Suspense>
      )}
    </div>
  );
}
