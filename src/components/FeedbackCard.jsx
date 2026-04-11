/**
 * Per-question feedback: senior-tech tone layout (✓ / ◎ / → + strong answer toggle).
 */

function deriveGapLines(result) {
  if (!result) return [];
  const g = result.gaps;
  if (Array.isArray(g) && g.length > 0) {
    return g.map((s) => String(s).trim()).filter(Boolean).slice(0, 2);
  }
  const m = result.missing;
  if (!m || m === 'None') return [];
  if (m.includes(' · ')) {
    return m.split(' · ').map((s) => s.trim()).filter(Boolean).slice(0, 2);
  }
  return [m];
}

function shouldShowStrength(strength) {
  if (!strength || typeof strength !== 'string') return false;
  const t = strength.trim();
  if (!t || t === 'Nothing significant') return false;
  if (/^evaluation error/i.test(t)) return false;
  return true;
}

export default function FeedbackCard({
  questionIndex,
  sectionLabel,
  score,
  result,
  showIdeal,
  onToggleIdeal,
}) {
  if (!result) return null;

  const gaps = deriveGapLines(result);
  const showCovered = shouldShowStrength(result.strength);
  const hint = (result.hint || '').trim();
  const hasIdeal = Boolean(result.ideal && String(result.ideal).trim());

  return (
    <div className="feedback-card">
      <div className="feedback-card-header">
        <span className="feedback-card-meta">
          Q{questionIndex}
          <span className="feedback-card-dot"> · </span>
          {sectionLabel || 'Interview'}
          <span className="feedback-card-dot"> · </span>
          {score}/100
        </span>
      </div>

      <div className="feedback-card-body">
        {showCovered && (
          <p className="feedback-line feedback-line-covered">
            <span className="feedback-glyph" aria-hidden>✓</span>
            <span>{result.strength.trim()}</span>
          </p>
        )}

        {gaps.map((line, i) => (
          <p key={`gap-${i}`} className="feedback-line feedback-line-gap">
            <span className="feedback-glyph" aria-hidden>◎</span>
            <span>{line}</span>
          </p>
        ))}

        {hint && (
          <p className="feedback-line feedback-line-redirect">
            <span className="feedback-glyph" aria-hidden>→</span>
            <span>{hint}</span>
          </p>
        )}
      </div>

      {hasIdeal && (
        <div className="feedback-strong-wrap">
          <button
            type="button"
            className="feedback-strong-btn"
            onClick={onToggleIdeal}
            aria-expanded={showIdeal}
          >
            {showIdeal ? '− Hide' : '+ See what a strong answer looks like'}
          </button>
          {showIdeal && (
            <div className="ideal-answer feedback-strong-answer">{result.ideal}</div>
          )}
        </div>
      )}
    </div>
  );
}
