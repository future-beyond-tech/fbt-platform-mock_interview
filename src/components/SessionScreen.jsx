import { useState, useRef, useCallback, lazy, Suspense } from 'react';
import { useVoice } from '../hooks/useVoice';
import { useTypewriter } from '../hooks/useTypewriter';
import Avatar from './Avatar';
import { Button, Alert, ProgressBar, Skeleton } from './ui';
import RoboFetch from './RoboFetch';

// Heavy visuals — only needed while recording (waveform) or after evaluation (score).
// Splitting them keeps the initial SessionScreen bundle small.
const WaveformVisualizer = lazy(() => import('./WaveformVisualizer'));
const ScoreReveal        = lazy(() => import('./ScoreReveal'));

function appendTranscript(currentText, incomingText) {
  if (!incomingText) return currentText;
  return currentText + (currentText && !currentText.endsWith(' ') ? ' ' : '') + incomingText;
}

export default function SessionScreen({
  session,
  idx,
  phase,
  draftAnswer,
  submittedAnswer,
  result,
  showIdeal,
  attempts,
  stats,
  onDraftChange,
  onSubmit,
  onNext,
  onSkip,
  onRetry,
  onToggleIdeal,
  onGoStart,
  groqApiKey,
}) {
  const [error, setError] = useState('');
  const [fetchingNext, setFetchingNext] = useState(false);
  const q = session[idx];
  const draftRef = useRef(draftAnswer);
  draftRef.current = draftAnswer;

  const updateDraft = useCallback((nextValue) => {
    const resolved = typeof nextValue === 'function' ? nextValue(draftRef.current) : nextValue;
    draftRef.current = resolved;
    onDraftChange(resolved);
  }, [onDraftChange]);

  const handleTranscript = useCallback((text) => {
    updateDraft(current => appendTranscript(current, text));
  }, [updateDraft]);

  const { isRecording, isTranscribing, hasMic, label, error: voiceError, mode, toggle, finish, cancel } = useVoice(handleTranscript, groqApiKey);
  const { displayed: typedQuestion, done: typingDone, skip: skipTyping } = useTypewriter(
    phase === 'question' || phase === 'thinking' || phase === 'result' ? q.q : '',
    22
  );

  const handleSubmit = async () => {
    await finish();
    const text = draftRef.current.trim();
    if (!text) {
      setError('Write or speak an answer first.');
      return;
    }

    setError('');
    onSubmit(text);
  };

  const handleAnswerKeyDown = (e) => {
    // Doherty: keep submission fast with Cmd/Ctrl+Enter shortcut
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      void handleSubmit();
    }
  };

  const handleRetry = async () => {
    await cancel();
    updateDraft('');
    onRetry();
  };

  const handleSkip = async () => {
    await cancel();
    updateDraft('');
    onSkip();
  };

  const handleNext = async () => {
    await cancel();
    updateDraft('');
    setFetchingNext(true);
    // Small delay so the robot runs before the instant swap.
    setTimeout(() => {
      setFetchingNext(false);
      onNext();
    }, 1800);
  };

  const handleGoStart = async () => {
    await cancel();
    updateDraft('');
    onGoStart();
  };

  const prog = ((idx + (phase === 'result' ? 1 : 0)) / session.length) * 100;

  const avatarState =
    phase === 'thinking' ? 'thinking'
      : phase === 'result' && result?.verdict === 'correct' ? 'happy'
        : phase === 'result' && result?.verdict === 'incorrect' ? 'disappointed'
          : (!typingDone && phase === 'question') ? 'speaking'
            : 'idle';

  if (fetchingNext) {
    return (
      <div className="interview-screen slide-up">
        <RoboFetch questionNumber={idx + 2} total={session.length} />
      </div>
    );
  }

  return (
    <div className="interview-screen slide-up">
      <div className="interview-sticky">
        <div className="interview-top">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void handleGoStart()}
            className="ghost-btn"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><polyline points="15 18 9 12 15 6" /></svg>
            Back
          </Button>
          <div className="interview-meta" aria-live="polite">
            <span className="meta-section">{q.s}</span>
            <span className="meta-divider" aria-hidden="true">·</span>
            <span className="meta-progress">Q{idx + 1}/{session.length}</span>
            {attempts > 1 && <span className="meta-attempt">Attempt {attempts}</span>}
          </div>
          {stats.answered > 0 && <span className="avg-badge" aria-label={`Average score ${stats.avg} percent`}>{stats.avg}%</span>}
        </div>

        <ProgressBar
          value={prog}
          size="sm"
          label={`Session progress: question ${idx + 1} of ${session.length}`}
        />
        <div className="interview-progress-meta">
          <span>Question {idx + 1} of {session.length}</span>
          {stats.answered > 0 && <span>{stats.correct}&nbsp;correct · {stats.partial}&nbsp;partial · {stats.incorrect}&nbsp;incorrect</span>}
        </div>
      </div>

      <div className="interviewer-area">
        <Avatar state={avatarState} size={72} />
        <div className="interviewer-bubble">
          <div className="bubble-tags">
            <span className="bubble-tag">{q.s}</span>
            <span className="bubble-tag">Day {q.day}</span>
          </div>
          <p
            className="bubble-text"
            onClick={!typingDone ? skipTyping : undefined}
            onKeyDown={!typingDone ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); skipTyping(); }
            } : undefined}
            role={!typingDone ? 'button' : undefined}
            tabIndex={!typingDone ? 0 : undefined}
            aria-label={!typingDone ? 'Skip typing animation' : undefined}
          >
            {typedQuestion}
            {!typingDone && <span className="cursor-blink" aria-hidden="true">|</span>}
          </p>
          {!typingDone && <p className="tap-hint">Press Enter or click to skip animation</p>}
        </div>
      </div>

      {phase === 'question' && (
        <div className="answer-area slide-up">
          <div className="voice-controls">
            <Suspense fallback={<Skeleton shape="rect" width="160px" height="24px" />}>
              <WaveformVisualizer active={isRecording} />
            </Suspense>
            <span className="voice-label" aria-live="polite">
              {isRecording && <span className="pulse-dot" />}
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
          {voiceError && <Alert tone="warning">{voiceError}</Alert>}
          <textarea
            key={q.id}
            className="answer-input"
            placeholder="Type or speak your answer..."
            aria-label="Your answer"
            aria-describedby={`${q.id}-shortcut`}
            autoFocus
            value={draftAnswer}
            onChange={e => updateDraft(e.target.value)}
            onKeyDown={handleAnswerKeyDown}
          />
          <p id={`${q.id}-shortcut`} className="answer-shortcut-hint">
            Press <kbd>⌘</kbd><kbd>Enter</kbd> or <kbd>Ctrl</kbd><kbd>Enter</kbd> to submit
          </p>
          {error && <Alert tone="danger">{error}</Alert>}
          <div className="answer-actions">
            <Button variant="primary" onClick={() => void handleSubmit()} className="action-btn primary">
              Submit Answer
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
            </Button>
            <Button variant="ghost" onClick={() => void handleSkip()} className="action-btn ghost">Skip</Button>
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
            <div className="think-dots">
              <span /><span /><span />
            </div>
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
              <Suspense fallback={<Skeleton shape="circle" width="72px" height="72px" />}>
                <ScoreReveal score={result.score} verdict={result.verdict} />
              </Suspense>
              <div className="result-verdict-info">
                <span className="verdict-text">
                  {result.verdict === 'correct' ? 'Correct' : result.verdict === 'partial' ? 'Partially Correct' : 'Incorrect'}
                </span>
                <span className="semantic-note">Semantically evaluated</span>
              </div>
            </div>

            <div className="score-bar-wrap">
              <div className="score-bar">
                <div
                  className={`score-bar-fill ${result.verdict}`}
                  style={{ width: `${result.score}%` }}
                />
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

            <button className="ideal-btn" type="button" onClick={onToggleIdeal}>
              {showIdeal ? 'Hide ideal answer ▲' : 'Show ideal answer ▼'}
            </button>
            {showIdeal && result.ideal && (
              <div className="ideal-answer">{result.ideal}</div>
            )}
          </div>

          <div className="answer-actions">
            {result.verdict !== 'correct' && (
              <Button
                variant="secondary"
                onClick={() => void handleRetry()}
                className="action-btn outline"
              >
                ↺ Try Again
              </Button>
            )}
            <Button
              variant="primary"
              onClick={() => void handleNext()}
              className="action-btn primary"
            >
              {idx + 1 >= session.length ? 'Finish Session' : 'Next Question →'}
            </Button>
            {result.verdict !== 'correct' && (
              <Button
                variant="ghost"
                onClick={() => void handleSkip()}
                className="action-btn ghost ml-auto"
              >
                Skip
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
