import { useState } from 'react';
import Avatar from './Avatar';

const AI_TOPICS = [
  { value: '', label: 'Mixed (surprise me)' },
  { value: 'JavaScript closures, scope, and hoisting', label: 'JS Closures & Scope' },
  { value: 'React hooks — useState, useEffect, useRef, useMemo, useCallback', label: 'React Hooks' },
  { value: 'async/await, promises, and the event loop', label: 'Async & Promises' },
  { value: 'React performance optimisation — memo, lazy, Suspense', label: 'React Performance' },
  { value: 'JavaScript arrays and objects — map, reduce, filter, deep copy', label: 'Arrays & Objects' },
  { value: 'CSS layout — flexbox, grid, responsive design', label: 'CSS Layout' },
  { value: 'system design for a senior frontend engineer', label: 'Frontend System Design' },
];

export default function StartScreen({ sessions, onStart, onGenerateAI, onUpload, errorMessage, onRetryInit }) {
  const [showAIPanel, setShowAIPanel] = useState(false);
  const [topic, setTopic] = useState('');
  const [count] = useState(3);

  const handleGenerate = () => {
    onGenerateAI(topic, count);
  };

  return (
    <div className="start-screen slide-up">
      <div className="start-hero">
        <Avatar state="idle" size={90} />
        <h1 className="hero-title">FBT Mock</h1>
        <p className="hero-sub">AI-Powered Interview Simulation</p>
        <p className="hero-desc">
          Practice JavaScript & React interview questions with real-time AI evaluation.
          Choose a session to begin.
        </p>
      </div>

      {errorMessage && (
        <div className="notice-card" role="status">
          <p>{errorMessage}</p>
          {onRetryInit && (
            <button className="action-btn outline" type="button" onClick={onRetryInit}>
              Retry Connection
            </button>
          )}
        </div>
      )}

      <div className="session-grid">
        {sessions.map((s, i) => (
          <button
            key={s.id}
            type="button"
            className="session-tile"
            style={{ '--accent': s.col, animationDelay: `${i * 0.08}s` }}
            onClick={() => onStart(s.id)}
          >
            <div className="tile-glow" />
            <div className="tile-content">
              <div className="tile-dot" style={{ background: s.col }} />
              <div className="tile-name">{s.name}</div>
              <div className="tile-sub">{s.sub}</div>
            </div>
            <svg className="tile-arrow" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><polyline points="9 18 15 12 9 6" /></svg>
          </button>
        ))}

        {/* AI Generated session tile */}
        <button
          type="button"
          className={`session-tile ai-tile${showAIPanel ? ' ai-tile--open' : ''}`}
          style={{ '--accent': '#a78bfa', animationDelay: `${sessions.length * 0.08}s` }}
          onClick={() => setShowAIPanel(v => !v)}
        >
          <div className="tile-glow" style={{ background: 'radial-gradient(ellipse at 20% 50%, rgba(167,139,250,0.12), transparent 70%)' }} />
          <div className="tile-content">
            <div className="tile-dot" style={{ background: '#a78bfa' }} />
            <div className="tile-name">✨ AI Generated</div>
            <div className="tile-sub">3 fresh questions · powered by your LLM</div>
          </div>
          <svg className={`tile-arrow${showAIPanel ? ' rotated' : ''}`} width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><polyline points="9 18 15 12 9 6" /></svg>
        </button>

        {/* Expandable AI panel */}
        {showAIPanel && (
          <div className="ai-panel slide-up">
            <label className="ai-panel-label">Topic focus</label>
            <select
              className="ai-topic-select"
              value={topic}
              onChange={e => setTopic(e.target.value)}
            >
              {AI_TOPICS.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
            <p className="ai-panel-hint">
              The AI will generate <strong>3 unique questions</strong> tailored to this topic using your selected provider.
            </p>
            <button className="action-btn primary ai-gen-btn" type="button" onClick={handleGenerate}>
              ✨ Generate Questions
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
            </button>
          </div>
        )}

        {/* Upload from file tile */}
        <button
          type="button"
          className="session-tile upload-tile"
          style={{ '--accent': '#34d399', animationDelay: `${(sessions.length + 1) * 0.08}s` }}
          onClick={onUpload}
        >
          <div className="tile-glow" style={{ background: 'radial-gradient(ellipse at 20% 50%, rgba(52,211,153,0.12), transparent 70%)' }} />
          <div className="tile-content">
            <div className="tile-dot" style={{ background: '#34d399' }} />
            <div className="tile-name">📄 From File</div>
            <div className="tile-sub">Upload CV or code · get 1 tailored question</div>
          </div>
          <svg className="tile-arrow" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><polyline points="9 18 15 12 9 6" /></svg>
        </button>
      </div>
    </div>
  );
}
