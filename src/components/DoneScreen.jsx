import { useState, useEffect } from 'react';
import Avatar from './Avatar';
import ScoreReveal from './ScoreReveal';

export default function DoneScreen({ stats, onNewSession, onRetry }) {
  const { avg, answered, correct, partial, incorrect, skipped } = stats;
  const [showContent, setShowContent] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setShowContent(true), 600);
    return () => clearTimeout(t);
  }, []);

  const msg = avg >= 80
    ? 'Outstanding performance!'
    : avg >= 60
      ? 'Good work — review the misses.'
      : avg >= 40
        ? 'Keep drilling — you\'re getting there.'
        : 'More practice needed — consistency is key.';

  return (
    <div className="done-screen slide-up">
      <Avatar state={avg >= 60 ? 'happy' : 'idle'} size={80} />

      <div className="done-score-area">
        <ScoreReveal score={avg} verdict={avg >= 70 ? 'correct' : avg >= 40 ? 'partial' : 'incorrect'} />
      </div>

      <p className="done-msg">{msg}</p>
      <p className="done-sub">{answered} question{answered !== 1 ? 's' : ''} answered</p>

      {showContent && (
        <div className="done-stats slide-up">
          <div className="stat-row">
            <StatPill value={correct} label="Correct" color="#64ffda" />
            <StatPill value={partial} label="Partial" color="#ffd93d" />
            <StatPill value={incorrect} label="Wrong" color="#ff6b6b" />
            <StatPill value={skipped} label="Skipped" color="rgba(255,255,255,0.25)" />
          </div>

          <div className="done-actions">
            <button className="action-btn primary" onClick={onNewSession}>New Session</button>
            <button className="action-btn outline" onClick={onRetry}>Retry Same</button>
          </div>
        </div>
      )}
    </div>
  );
}

function StatPill({ value, label, color }) {
  return (
    <div className="stat-pill">
      <span className="stat-val" style={{ color }}>{value}</span>
      <span className="stat-lbl">{label}</span>
    </div>
  );
}
