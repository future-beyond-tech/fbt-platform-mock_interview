import { useState, useEffect } from 'react';

/**
 * Animated score counter that counts up from 0 to the final score.
 */
export default function ScoreReveal({ score, verdict }) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    let current = 0;
    const step = Math.max(1, Math.ceil(score / 30));
    const timer = setInterval(() => {
      current += step;
      if (current >= score) {
        current = score;
        clearInterval(timer);
      }
      setDisplay(current);
    }, 25);
    return () => clearInterval(timer);
  }, [score]);

  const color = verdict === 'correct' ? '#64ffda' : verdict === 'partial' ? '#ffd93d' : '#ff6b6b';

  return (
    <div className="score-reveal">
      <svg viewBox="0 0 120 120" width="120" height="120">
        {/* Background ring */}
        <circle cx="60" cy="60" r="52" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="6" />
        {/* Animated progress ring */}
        <circle
          cx="60" cy="60" r="52"
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={`${(display / 100) * 327} 327`}
          transform="rotate(-90 60 60)"
          style={{ transition: 'stroke-dasharray 0.1s ease' }}
        />
        {/* Score text */}
        <text x="60" y="55" textAnchor="middle" fill={color} fontSize="28" fontWeight="700" fontFamily="inherit">
          {display}
        </text>
        <text x="60" y="74" textAnchor="middle" fill="rgba(255,255,255,0.4)" fontSize="11" fontFamily="inherit">
          SCORE
        </text>
      </svg>
    </div>
  );
}
