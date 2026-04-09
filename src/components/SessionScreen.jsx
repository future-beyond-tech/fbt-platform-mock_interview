import { useState, useRef, useCallback } from 'react';
import { useVoice } from '../hooks/useVoice';
import { useTypewriter } from '../hooks/useTypewriter';
import Avatar from './Avatar';
import ScoreReveal from './ScoreReveal';
import WaveformVisualizer from './WaveformVisualizer';

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
    onNext();
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

  return (
    <div className="interview-screen slide-up">
      <div className="interview-top">
        <button className="ghost-btn" type="button" onClick={() => void handleGoStart()}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><polyline points="15 18 9 12 15 6" /></svg>
          Back
        </button>
        <div className="interview-meta">
          <span className="meta-section">{q.s}</span>
          <span className="meta-divider">·</span>
          <span className="meta-progress">Q{idx + 1}/{session.length}</span>
          {attempts > 1 && <span className="meta-attempt">Attempt {attempts}</span>}
        </div>
        {stats.answered > 0 && <span className="avg-badge">{stats.avg}%</span>}
      </div>

      <div className="progress-bar">
        <div className="progress-fill" style={{ width: `${prog}%` }} />
      </div>

      <div className="interviewer-area">
        <Avatar state={avatarState} size={72} />
        <div className="interviewer-bubble">
          <div className="bubble-tags">
            <span className="bubble-tag">{q.s}</span>
            <span className="bubble-tag">Day {q.day}</span>
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
            key={q.id}
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
            <button className="action-btn ghost" type="button" onClick={() => void handleSkip()}>Skip</button>
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
              <button className="action-btn outline" type="button" onClick={() => void handleRetry()}>↺ Try Again</button>
            )}
            <button className="action-btn primary" type="button" onClick={() => void handleNext()}>
              {idx + 1 >= session.length ? 'Finish Session' : 'Next Question →'}
            </button>
            {result.verdict !== 'correct' && (
              <button className="action-btn ghost ml-auto" type="button" onClick={() => void handleSkip()}>Skip</button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
