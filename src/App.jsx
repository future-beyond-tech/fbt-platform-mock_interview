import { useCallback, useEffect, lazy, Suspense } from 'react';
import { useDispatch } from 'react-redux';
import { fetchQuestions, fetchProviders, evaluateAnswer, generateQuestions, startInterview, healthCheck, cleanTranscript } from './api';
import { useSettings } from './store/useSettingsStore';
import { useSessionStore } from './store/useSessionStore';
import { setBlueprint, addQuestion, resetInterview } from './store/interviewSlice';
import ErrorBoundary from './components/ErrorBoundary';
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

export default function App() {
  const { settings, update: updateSettings } = useSettings();
  const dispatch = useDispatch();

  // ── Session store ──────────────────────────────────────────────────────────
  const {
    phase,
    session,
    idx,
    draftAnswer,
    submittedAnswer,
    result,
    history,
    attempts,
    showIdeal,
    providers,
    health,
    loading,
    settingsOpen,
    errorMessage,
    interviewSession,
    setLoading,
    setInitialData,
    setError,
    dismissError,
    openSettings,
    closeSettings,
    goStart,
    startSession,
    startAISession,
    retryAll,
    setInterviewSession,
    clearInterviewSession,
    setDraftAnswer,
    setResult,
    skipQ,
    nextQ,
    retryQ,
    toggleIdeal,
    getStats,
    setPhase,
    setSubmittedAnswer,
  } = useSessionStore();

  // ── Initial data load ──────────────────────────────────────────────────────
  const loadInitialData = useCallback(async () => {
    setLoading(true);
    try {
      const [qData, pData, healthData] = await Promise.all([
        fetchQuestions(),
        fetchProviders(),
        healthCheck(),
      ]);
      setInitialData({
        questions: qData.questions,
        sessions: qData.sessions,
        providers: pData.providers,
        health: healthData,
      });
    } catch {
      setError('Could not connect to the backend. Start the API server and retry.');
    }
  }, [setLoading, setInitialData, setError]);

  useEffect(() => { void loadInitialData(); }, [loadInitialData]);

  // ── Current provider info ──────────────────────────────────────────────────
  const currentProvider = providers.find(p => p.id === settings.provider);

  // ── File-based interview start ─────────────────────────────────────────────
  const startFileSession = useCallback(async (file) => {
    setLoading(true);
    try {
      const data = await startInterview(file, settings.provider, settings.apiKey, settings.model);

      dispatch(resetInterview());
      dispatch(setBlueprint(data.blueprint));
      dispatch(addQuestion({
        question: data.question,
        category: data.category,
        section: data.section,
        questionNumber: data.question_number,
      }));

      setInterviewSession({
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
      });
    } catch (e) {
      setLoading(false);
      throw e;
    }
  }, [settings, dispatch, setLoading, setInterviewSession]);

  // ── AI question generation ─────────────────────────────────────────────────
  const startAIQuestions = useCallback(async (topic, count) => {
    setLoading(true);
    try {
      const data = await generateQuestions(settings.provider, settings.apiKey, settings.model, topic, count);
      startAISession(data.questions);
    } catch (e) {
      useSessionStore.getState().setError(`Failed to generate questions: ${e.message}`);
    }
  }, [settings, startAISession]);

  // ── Answer submission ──────────────────────────────────────────────────────
  const submitAnswer = useCallback(async (text) => {
    const q = session[idx];
    if (!q) return;

    setPhase('thinking');
    setSubmittedAnswer(text);

    // Clean up voice transcription before scoring.
    const cleaned = await cleanTranscript(text, settings.provider, settings.apiKey, settings.model);
    if (cleaned && cleaned !== text) setSubmittedAnswer(cleaned);
    const answerToEval = cleaned || text;

    let evalResult;
    try {
      evalResult = await evaluateAnswer(q.id, answerToEval, settings.provider, settings.apiKey, settings.model);
      evalResult.score = Math.max(0, Math.min(100, Math.round(evalResult.score)));
    } catch (e) {
      evalResult = { score: 0, verdict: 'incorrect', strength: '', gaps: [], missing: e.message.slice(0, 200), hint: '', ideal: '' };
    }

    setResult(evalResult);
  }, [session, idx, settings, setPhase, setSubmittedAnswer, setResult]);

  const stats = getStats();

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
            health={health}
            onOpenSettings={openSettings}
          />
        </header>

        <main id="main-content" className="app-main t-anim-fade" tabIndex={-1}>
          {errorMessage && (
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
                {errorMessage}
              </Alert>
              <button type="button" className="t-sr-only" onClick={dismissError}>Dismiss error</button>
            </div>
          )}

          {loading && <LaunchLoader label="Preparing your interview" />}

          {!loading && phase === 'start' && (
            <UploadPage onGenerateFromFile={startFileSession} />
          )}

          {!loading && phase === 'interview' && interviewSession && (
            <ErrorBoundary feature="Interview Session" onReset={clearInterviewSession}>
              <Suspense fallback={<SessionScreenSkeleton />}>
                <InterviewSession
                  sessionId={interviewSession.sessionId}
                  initialQuestion={interviewSession.question}
                  initialSection={interviewSession.section}
                  initialCategory={interviewSession.category}
                  initialQuestionNumber={interviewSession.questionNumber}
                  totalQuestions={interviewSession.totalQuestions}
                  initialWhatToEvaluate={interviewSession.whatToEvaluate}
                  initialState={interviewSession.state}
                  initialProfile={interviewSession.profile}
                  initialBlueprint={interviewSession.blueprint}
                  settings={settings}
                  groqApiKey={settings.provider === 'groq' ? settings.apiKey : (import.meta.env.VITE_GROQ_API_KEY || '')}
                  onGoStart={clearInterviewSession}
                  onComplete={clearInterviewSession}
                />
              </Suspense>
            </ErrorBoundary>
          )}

          {!loading && phase === 'done' && (
            <ErrorBoundary feature="Results" onReset={goStart}>
              <Suspense fallback={<SessionScreenSkeleton />}>
                <DoneScreen
                  stats={stats}
                  onNewSession={goStart}
                  onRetry={retryAll}
                />
              </Suspense>
            </ErrorBoundary>
          )}

          {!loading && ['question', 'thinking', 'result'].includes(phase) && (
            <ErrorBoundary feature="Practice Session" onReset={goStart}>
              <Suspense fallback={<SessionScreenSkeleton />}>
                <SessionScreen
                  session={session}
                  idx={idx}
                  phase={phase}
                  draftAnswer={draftAnswer}
                  submittedAnswer={submittedAnswer}
                  result={result}
                  showIdeal={showIdeal}
                  attempts={attempts}
                  stats={stats}
                  onDraftChange={setDraftAnswer}
                  onSubmit={submitAnswer}
                  onNext={nextQ}
                  onSkip={skipQ}
                  onRetry={retryQ}
                  onToggleIdeal={toggleIdeal}
                  onGoStart={goStart}
                  groqApiKey={settings.provider === 'groq' ? settings.apiKey : ''}
                />
              </Suspense>
            </ErrorBoundary>
          )}
        </main>
      </div>

      {settingsOpen && (
        <Suspense fallback={null}>
          <SettingsDrawer
            open={settingsOpen}
            onClose={closeSettings}
            settings={settings}
            onUpdate={updateSettings}
            providers={providers}
          />
        </Suspense>
      )}
    </div>
  );
}
