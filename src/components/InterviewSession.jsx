import { useState, useRef, useCallback } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useVoice } from '../hooks/useVoice';
import { useTypewriter } from '../hooks/useTypewriter';
import Avatar from './Avatar';
import ScoreReveal from './ScoreReveal';
import FeedbackCard from './FeedbackCard';
import WaveformVisualizer from './WaveformVisualizer';
import InterviewProgress from './InterviewProgress';
import InterviewReport from './InterviewReport';
import { interviewTurn, evaluateAnswer, endInterview, getInterviewReport, enqueueInterviewProbe } from '../api';
import {
  submitAnswer as dispatchAnswer,
  addQuestion,
  setReport as dispatchReport,
} from '../store/interviewSlice';
import { selectAnswers as selectReduxAnswers } from '../store/interviewSelectors';

function appendTranscript(currentText, incomingText) {
  if (!incomingText) return currentText;
  return currentText + (currentText && !currentText.endsWith(' ') ? ' ' : '') + incomingText;
}

export default function InterviewSession({
  sessionId,
  initialQuestion,
  initialSection,
  initialCategory,
  initialQuestionNumber,
  totalQuestions,
  initialWhatToEvaluate,
  initialState,
  initialProfile,
  initialBlueprint,
  settings,
  groqApiKey,
  onGoStart,
  onComplete,
}) {
  const [currentQuestion, setCurrentQuestion] = useState(initialQuestion);
  const [currentSection, setCurrentSection] = useState(initialSection || 'Introduction');
  const [currentCategory, setCurrentCategory] = useState(initialCategory || 'intro');
  const [questionNumber, setQuestionNumber] = useState(initialQuestionNumber || 1);
  const [whatToEvaluate, setWhatToEvaluate] = useState(initialWhatToEvaluate || '');
  const [interviewState, setInterviewState] = useState(initialState);
  const [phase, setPhase] = useState('question'); // question | thinking | result | report
  const [draftAnswer, setDraftAnswer] = useState('');
  const [submittedAnswer, setSubmittedAnswer] = useState('');
  const [result, setResult] = useState(null);
  const [showIdeal, setShowIdeal] = useState(false);
  const [error, setError] = useState('');
  const [loadingNext, setLoadingNext] = useState(false);
  const [report, setReport] = useState(null);
  const dispatch = useDispatch();
  const reduxAnswers = useSelector(selectReduxAnswers);
  const [loadingReport, setLoadingReport] = useState(false);
  const [history, setHistory] = useState([
    { role: 'assistant', section: initialSection || 'Introduction', category: initialCategory || 'intro', text: initialQuestion },
  ]);

  // Track answers for the report.
  const answersRef = useRef([]);

  const draftRef = useRef('');
  draftRef.current = draftAnswer;

  const updateDraft = useCallback((nextValue) => {
    const resolved = typeof nextValue === 'function' ? nextValue(draftRef.current) : nextValue;
    draftRef.current = resolved;
    setDraftAnswer(resolved);
  }, []);

  const handleTranscript = useCallback(
    (text) => {
      updateDraft((current) => appendTranscript(current, text));
    },
    [updateDraft],
  );

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

    // Record this answer locally.
    answersRef.current.push({
      question: currentQuestion,
      answer: text,
      category: currentCategory,
      questionNumber,
    });

    let evalResult;
    try {
      evalResult = await evaluateAnswer(
        `interview-${questionNumber}`,
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
        strength: '',
        missing: e.message?.slice(0, 200) || 'Unknown error',
        gaps: [],
        hint: '',
        ideal: '',
      };
    }

    // Save score to the answers ref for the report.
    const lastAnswer = answersRef.current[answersRef.current.length - 1];
    if (lastAnswer) {
      lastAnswer.score = evalResult.score;
      lastAnswer.feedback = evalResult.strength;
    }

    // Dispatch to Redux store.
    dispatch(dispatchAnswer({
      questionIndex: questionNumber,
      question: currentQuestion,
      answer: text,
      score: evalResult.score,
      verdict: evalResult.verdict,
      strength: evalResult.strength,
      missing: evalResult.missing,
      gaps: evalResult.gaps ?? [],
      hint: evalResult.hint,
      ideal: evalResult.ideal,
      category: currentCategory,
      section: currentSection,
    }));

    // Tier 1–3 only: must finish enqueueing the probe BEFORE showing the result screen so "Next"
    // cannot call interview_turn while dynamic_queue is still empty (otherwise the blueprint advances first).
    const sc = evalResult.score;
    const tierOk = ['tier_1', 'tier_2', 'tier_3'].includes(currentCategory);
    const slotsUsed = interviewState?.dynamic_slots_used ?? 0;
    if (sc >= 41 && sc <= 70 && tierOk && slotsUsed < 2) {
      try {
        const probeData = await enqueueInterviewProbe(
          sessionId,
          currentQuestion,
          text,
          currentCategory,
          settings.provider,
          settings.apiKey,
          settings.model,
        );
        if (probeData?.state) setInterviewState(probeData.state);
      } catch {
        // Non-fatal: user proceeds without a queued probe for this turn.
      }
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

      // Append to history.
      setHistory(prev => [
        ...prev,
        { role: 'user', text: answerForTurn, score: result?.score, category: currentCategory },
        ...(data.question ? [{ role: 'assistant', section: data.section, category: data.category, text: data.question }] : []),
      ]);

      if (data.completed || !data.question) {
        // Interview complete — show the report.
        setInterviewState(data.state);
        setLoadingNext(false);
        await handleGenerateReport();
        return;
      }

      // Dispatch new question to Redux.
      dispatch(addQuestion({
        question: data.question,
        category: data.category,
        section: data.section,
        questionNumber: data.question_number,
      }));

      setCurrentQuestion(data.question);
      setCurrentSection(data.section);
      setCurrentCategory(data.category || 'domain_concept');
      setQuestionNumber(data.question_number);
      setWhatToEvaluate(data.what_to_evaluate || '');
      setInterviewState(data.state);
      setDraftAnswer('');
      setSubmittedAnswer('');
      setResult(null);
      setShowIdeal(false);
      setPhase('question');
    } catch (e) {
      setError(e.message || 'Failed to fetch the next question.');
    } finally {
      setLoadingNext(false);
    }
  };

  const handleGenerateReport = async () => {
    setLoadingReport(true);
    setPhase('report');
    try {
      const data = await getInterviewReport(
        sessionId,
        settings.provider,
        settings.apiKey,
        settings.model,
        reduxAnswers,
      );
      setReport(data.report);
      dispatch(dispatchReport(data.report));
    } catch (e) {
      setError(e.message || 'Failed to generate report.');
    } finally {
      setLoadingReport(false);
    }
  };

  const handleRetry = async () => {
    await cancel();
    // Remove the last recorded answer since we're retrying.
    answersRef.current.pop();
    setDraftAnswer('');
    setSubmittedAnswer('');
    setResult(null);
    setShowIdeal(false);
    setPhase('question');
  };

  const handleGoStart = async () => {
    await cancel();
    // If we have answers, show the report before leaving.
    if (answersRef.current.length > 0 && phase !== 'report') {
      await handleGenerateReport();
      return;
    }
    if (sessionId) await endInterview(sessionId);
    onGoStart();
  };

  const avatarState =
    phase === 'thinking' ? 'thinking'
      : phase === 'result' && result?.verdict === 'correct' ? 'happy'
        : phase === 'result' && result?.verdict === 'incorrect' ? 'disappointed'
          : (!typingDone && phase === 'question') ? 'speaking'
            : 'idle';

  // Report screen.
  if (phase === 'report') {
    return (
      <div className="interview-screen slide-up">
        <div className="interview-top">
          <button className="ghost-btn" type="button" onClick={() => void handleGoStart()}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><polyline points="15 18 9 12 15 6" /></svg>
            New Interview
          </button>
          <div className="interview-meta">
            <span className="meta-section">Interview Report</span>
          </div>
        </div>

        {loadingReport && (
          <div className="loading" style={{ padding: '48px 0' }}>
            <div className="think-dots"><span /><span /><span /></div>
            <p>Generating your interview report...</p>
          </div>
        )}

        {error && !loadingReport && <div className="inline-error" style={{ margin: '24px 0' }}>{error}</div>}

        {report && !loadingReport && (
          <InterviewReport
            report={report}
            blueprint={initialBlueprint}
            onNewInterview={() => void handleGoStart()}
          />
        )}
      </div>
    );
  }

  // Robot loader is now shown INLINE inside the main screen (see below),
  // not as a full-page replacement.

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
          <span className="meta-progress">Q{questionNumber}/{totalQuestions}</span>
        </div>
      </div>

      <InterviewProgress
        questionNumber={questionNumber}
        totalQuestions={totalQuestions}
        category={currentCategory}
        profile={initialProfile}
        blueprint={initialBlueprint}
      />

      {/* Conversation history */}
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
            <span className="bubble-tag">Q{questionNumber}/{totalQuestions}</span>
          </div>
          <p className="bubble-text" onClick={!typingDone ? skipTyping : undefined}>
            {typedQuestion}
            {!typingDone && <span className="cursor-blink">|</span>}
          </p>
          {whatToEvaluate && typingDone && (
            <p className="bubble-eval-hint">Evaluating: {whatToEvaluate}</p>
          )}
          {!typingDone && <p className="tap-hint">tap to skip animation</p>}
        </div>
      </div>

      {phase === 'question' && (
        <div className="answer-area slide-up">
          <div className="voice-controls">
            <WaveformVisualizer active={isRecording} />
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
          {voiceError && <div className="inline-error">{voiceError}</div>}
          <textarea
            key={questionNumber}
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

            <FeedbackCard
              questionIndex={questionNumber}
              sectionLabel={currentSection}
              score={result.score}
              result={result}
              showIdeal={showIdeal}
              onToggleIdeal={() => setShowIdeal((v) => !v)}
            />
          </div>

          {error && <div className="inline-error">{error}</div>}

          {!loadingNext && (
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
              >
                {questionNumber >= totalQuestions ? 'Finish & See Report' : 'Next Question'}
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
              </button>
            </div>
          )}

          {loadingNext && (
            <div className="thinking-loader slide-up">
              <div className="thinking-loader-dots">
                <span /><span /><span />
              </div>
              <p className="thinking-loader-text">
                Preparing question {questionNumber + 1} of {totalQuestions}...
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
