import { useState, useRef, useCallback } from 'react';
import { useVoice } from '../hooks/useVoice';
import { useTypewriter } from '../hooks/useTypewriter';
import Avatar from './Avatar';
import ScoreReveal from './ScoreReveal';
import WaveformVisualizer from './WaveformVisualizer';
import InterviewProgress from './InterviewProgress';
import { interviewTurn, evaluateAnswer, endInterview } from '../api';

function appendTranscript(currentText, incomingText) {
  if (!incomingText) return currentText;
  return currentText + (currentText && !currentText.endsWith(' ') ? ' ' : '') + incomingText;
}

export default function InterviewSession({
  sessionId,
  initialQuestion,
  initialSection,
  initialState,
  initialProfile,
  settings,
  groqApiKey,
  onGoStart,
  onComplete,
}) {
  // Current turn state
  const [currentQuestion, setCurrentQuestion] = useState(initialQuestion);
  const [currentSection, setCurrentSection] = useState(initialSection || 'Introduction');
  const [interviewState, setInterviewState] = useState(initialState);
  const [phase, setPhase] = useState('question'); // question | thinking | result
  const [draftAnswer, setDraftAnswer] = useState('');
  const [submittedAnswer, setSubmittedAnswer] = useState('');
  const [result, setResult] = useState(null);
  const [showIdeal, setShowIdeal] = useState(false);
  const [error, setError] = useState('');
  const [loadingNext, setLoadingNext] = useState(false);
  const [history, setHistory] = useState([
    { role: 'assistant', section: initialSection || 'Introduction', text: initialQuestion },
  ]);

  const draftRef = useRef('');
  draftRef.current = draftAnswer;

  const updateDraft = useCallback((nextValue) => {
    const resolved = typeof nextValue === 'function' ? nextValue(draftRef.current) : nextValue;
    draftRef.current = resolved;
    setDraftAnswer(resolved);
  }, []);

  const handleTranscript = useCallback((text) => {
    updateDraft(current => appendTranscript(current, text));
  }, [updateDraft]);

  const {
    isRecording, isTranscribing, hasMic, label,
    error: voiceError, mode, toggle, finish, cancel,
  } = useVoice(handleTranscript, groqApiKey);

  const { displayed: typedQuestion, done: typingDone, skip: skipTyping } = useTypewriter(
    currentQuestion || '',
    22,
  );

  const handleSubmit = async () => {
    await finish();
    const text = draftRef.current.trim();
    if (!text) {
      setError('Write or speak an answer first.');
      return;
    }

    setError('');
    setSubmittedAnswer(text);
    setPhase('thinking');

    let evalResult;
    try {
      evalResult = await evaluateAnswer(
        `interview-${interviewState.questionCount}`,
        text,
        settings.provider,
        settings.apiKey,
        settings.model,
        {
          questionText: currentQuestion,
          section: currentSection,
          interviewSessionId: sessionId,
          profile: initialProfile,
        },
      );
      evalResult.score = Math.max(0, Math.min(100, Math.round(evalResult.score)));
    } catch (e) {
      evalResult = {
        score: 0,
        verdict: 'incorrect',
        strength: 'Evaluation error — try again.',
        missing: e.message?.slice(0, 200) || 'Unknown error',
        hint: '',
        ideal: '',
      };
    }

    setResult(evalResult);
    setPhase('result');
  };

  const handleNext = async () => {
    await cancel();
    const answerForTurn = submittedAnswer;
    setLoadingNext(true);
    setError('');
    try {
      const data = await interviewTurn(
        sessionId,
        answerForTurn,
        settings.provider,
        settings.apiKey,
        settings.model,
      );
      // Append candidate answer + interviewer response to history
      setHistory(prev => [
        ...prev,
        { role: 'user', text: answerForTurn, score: result?.score },
        { role: 'assistant', section: data.section, text: data.question },
      ]);
      setCurrentQuestion(data.question);
      setCurrentSection(data.section);
      setInterviewState(data.state);
      setDraftAnswer('');
      setSubmittedAnswer('');
      setResult(null);
      setShowIdeal(false);
      setPhase('question');

      if (data.state.completed) {
        onComplete?.();
      }
    } catch (e) {
      setError(e.message || 'Failed to fetch the next question.');
    } finally {
      setLoadingNext(false);
    }
  };

  const handleRetry = async () => {
    await cancel();
    setDraftAnswer('');
    setSubmittedAnswer('');
    setResult(null);
    setShowIdeal(false);
    setPhase('question');
  };

  const handleGoStart = async () => {
    await cancel();
    if (sessionId) await endInterview(sessionId);
    onGoStart();
  };

  // Note: we deliberately do NOT call endInterview() on unmount.
  // React StrictMode double-mounts in dev, which would delete the session
  // immediately. Sessions live in memory on the backend and are best-effort
  // cleaned up when the user clicks "End Interview".

  const avatarState =
    phase === 'thinking' ? 'thinking'
      : phase === 'result' && result?.verdict === 'correct' ? 'happy'
        : phase === 'result' && result?.verdict === 'incorrect' ? 'disappointed'
          : (!typingDone && phase === 'question') ? 'speaking'
            : 'idle';

  return (
    <div className="interview-screen slide-up">
      <div className="interview-top">
        <button className="ghost-btn" type="button" onClick={() => void handleGoStart()}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><polyline points="15 18 9 12 15 6" /></svg>
          End Interview
        </button>
        <div className="interview-meta">
          <span className="meta-section">{currentSection}</span>
          <span className="meta-divider">·</span>
          <span className="meta-progress">Q{interviewState.questionCount}</span>
        </div>
      </div>

      <InterviewProgress state={interviewState} profile={initialProfile} />

      {/* Conversation history (collapsed bubbles for previous turns) */}
      {history.length > 1 && (
        <div className="iv-history">
          {history.slice(0, -1).map((m, i) => (
            <div key={i} className={`iv-bubble ${m.role}`}>
              {m.role === 'assistant' && m.section && (
                <span className="iv-bubble-tag">{m.section}</span>
              )}
              <p>{m.text}</p>
              {m.role === 'user' && typeof m.score === 'number' && (
                <span className={`iv-bubble-score score-${m.score >= 75 ? 'good' : m.score >= 30 ? 'mid' : 'bad'}`}>
                  {m.score}/100
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="interviewer-area">
        <Avatar state={avatarState} size={72} />
        <div className="interviewer-bubble">
          <div className="bubble-tags">
            <span className="bubble-tag">{currentSection}</span>
            <span className="bubble-tag">⭐ Lvl {interviewState.difficultyLevel}</span>
          </div>
          <p className="bubble-text" onClick={!typingDone ? skipTyping : undefined}>
            {typedQuestion}
            {!typingDone && <span className="cursor-blink">|</span>}
          </p>
          {!typingDone && <p className="tap-hint">tap to skip animation</p>}
        </div>
      </div>

      {phase === 'question' && (
        <div className="answer-area slide-up">
          <div className="voice-controls">
            <WaveformVisualizer active={isRecording} />
            <span className="voice-label" aria-live="polite">
              {isTranscribing ? 'Transcribing...' : label}
            </span>
            {mode !== 'none' && hasMic && (
              <div className="voice-right">
                <span className="voice-mode-badge">
                  {mode === 'whisper' ? '⚡ Whisper' : '🌐 Browser'}
                </span>
                <button
                  type="button"
                  className={`voice-toggle${isRecording ? ' active' : ''}${isTranscribing ? ' transcribing' : ''}`}
                  onClick={toggle}
                  disabled={isTranscribing}
                >
                  {isTranscribing ? '...' : isRecording ? '⏹ Stop' : '🎤 Voice'}
                </button>
              </div>
            )}
          </div>
          {voiceError && <div className="inline-error">{voiceError}</div>}
          <textarea
            key={interviewState.questionCount}
            className="answer-input"
            placeholder="Type or speak your answer..."
            autoFocus
            value={draftAnswer}
            onChange={e => updateDraft(e.target.value)}
          />
          {error && <div className="inline-error">{error}</div>}
          <div className="answer-actions">
            <button className="action-btn primary" type="button" onClick={() => void handleSubmit()}>
              Submit Answer
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
            </button>
          </div>
        </div>
      )}

      {phase === 'thinking' && (
        <div className="thinking-area slide-up">
          <div className="your-answer-box">
            <span className="ya-label">Your answer</span>
            <p className="ya-text">{submittedAnswer}</p>
          </div>
          <div className="thinking-indicator">
            <div className="think-dots"><span /><span /><span /></div>
            <span>Evaluating your answer...</span>
          </div>
        </div>
      )}

      {phase === 'result' && result && (
        <div className="result-area slide-up">
          <div className="your-answer-box">
            <span className="ya-label">Your answer</span>
            <p className="ya-text">{submittedAnswer}</p>
          </div>

          <div className={`result-panel ${result.verdict}`}>
            <div className="result-top">
              <ScoreReveal score={result.score} verdict={result.verdict} />
              <div className="result-verdict-info">
                <span className="verdict-text">
                  {result.verdict === 'correct' ? 'Correct' : result.verdict === 'partial' ? 'Partially Correct' : 'Incorrect'}
                </span>
                <span className="semantic-note">Semantically evaluated</span>
              </div>
            </div>

            <div className="score-bar-wrap">
              <div className="score-bar">
                <div className={`score-bar-fill ${result.verdict}`} style={{ width: `${result.score}%` }} />
              </div>
              <span className="score-bar-label">{result.score}/100</span>
            </div>

            <div className="concept-grid">
              {result.strength && result.strength !== 'Nothing significant' && (
                <div className="concept-card covered">
                  <span className="concept-icon">✓</span>
                  <div>
                    <span className="concept-label">What you covered</span>
                    <p className="concept-text">{result.strength}</p>
                  </div>
                </div>
              )}
              {result.missing && result.missing !== 'None' && (
                <div className="concept-card missing">
                  <span className="concept-icon">✗</span>
                  <div>
                    <span className="concept-label">What was missing</span>
                    <p className="concept-text">{result.missing}</p>
                  </div>
                </div>
              )}
            </div>

            {result.hint && (
              <div className="hint-box">
                <span className="hint-icon">💡</span>
                <p>{result.hint}</p>
              </div>
            )}

            <button className="ideal-btn" type="button" onClick={() => setShowIdeal(v => !v)}>
              {showIdeal ? 'Hide ideal answer ▲' : 'Show ideal answer ▼'}
            </button>
            {showIdeal && result.ideal && (
              <div className="ideal-answer">{result.ideal}</div>
            )}
          </div>

          {error && <div className="inline-error">{error}</div>}

          <div className="answer-actions">
            {result.verdict !== 'correct' && (
              <button className="action-btn outline" type="button" onClick={() => void handleRetry()}>
                ↺ Try Again
              </button>
            )}
            <button
              className="action-btn primary"
              type="button"
              onClick={() => void handleNext()}
              disabled={loadingNext}
            >
              {loadingNext ? (
                <>
                  <span className="think-dots" style={{ display: 'inline-flex', gap: 3 }}><span /><span /><span /></span>
                  Next question…
                </>
              ) : (
                <>
                  Next Question
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
