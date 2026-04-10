export default function InterviewReport({ report, blueprint, onNewInterview }) {
  if (!report) return null;

  const gradeColor = {
    'A+': '#64ffda', 'A': '#64ffda', 'B+': '#ffd93d', 'B': '#ffd93d',
    'C+': '#ffa726', 'C': '#ffa726', 'D': '#ff6b6b', 'F': '#ff6b6b',
  };

  const hireColor = {
    'Strong Hire': '#64ffda', 'Hire': '#64ffda',
    'Maybe': '#ffd93d', 'No Hire': '#ff6b6b',
  };

  const catScores = report.category_scores || {};

  return (
    <div className="iv-report slide-up">
      {/* Header */}
      <div className="iv-report-header">
        <h2 className="iv-report-title">Interview Report</h2>
        {blueprint && (
          <p className="iv-report-sub">
            {blueprint.candidate_name || 'Candidate'} · {blueprint.primary_domain} · {blueprint.seniority_level} · {blueprint.experience_years} yrs
          </p>
        )}
      </div>

      {/* Overall score */}
      <div className="iv-report-overall">
        <div className="iv-report-score-circle">
          <span className="iv-report-score-num">{report.overall_score ?? '—'}</span>
          <span className="iv-report-score-label">/100</span>
        </div>
        <div className="iv-report-grade-block">
          <span className="iv-report-grade" style={{ color: gradeColor[report.grade] || 'var(--text-1)' }}>
            {report.grade || '—'}
          </span>
          <span className="iv-report-hire" style={{ color: hireColor[report.hire_recommendation] || 'var(--text-2)' }}>
            {report.hire_recommendation || '—'}
          </span>
        </div>
      </div>

      {/* Summary */}
      {report.summary && (
        <div className="iv-report-section">
          <p className="iv-report-summary">{report.summary}</p>
        </div>
      )}

      {/* Category scores */}
      {Object.keys(catScores).length > 0 && (
        <div className="iv-report-section">
          <h3 className="iv-report-section-title">Category Scores</h3>
          <div className="iv-report-cat-grid">
            {Object.entries(catScores).map(([key, val]) => (
              <div key={key} className="iv-report-cat-card">
                <div className="iv-report-cat-header">
                  <span className="iv-report-cat-name">{key.replace(/_/g, ' ')}</span>
                  <span className="iv-report-cat-score">{val?.score ?? '—'}/10</span>
                </div>
                {val?.feedback && <p className="iv-report-cat-feedback">{val.feedback}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Strengths + Improvement */}
      <div className="iv-report-two-col">
        {report.strengths?.length > 0 && (
          <div className="iv-report-section">
            <h3 className="iv-report-section-title">Strengths</h3>
            <ul className="iv-report-list iv-report-list--good">
              {report.strengths.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        )}
        {report.improvement_areas?.length > 0 && (
          <div className="iv-report-section">
            <h3 className="iv-report-section-title">Areas to Improve</h3>
            <ul className="iv-report-list iv-report-list--bad">
              {report.improvement_areas.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        )}
      </div>

      {/* Question breakdown */}
      {report.question_breakdown?.length > 0 && (
        <div className="iv-report-section">
          <h3 className="iv-report-section-title">Question Breakdown</h3>
          <div className="iv-report-qb">
            {report.question_breakdown.map((q, i) => (
              <div key={i} className="iv-report-qb-row">
                <span className="iv-report-qb-num">Q{q.question_number || i + 1}</span>
                <span className="iv-report-qb-cat">{(q.category || '').replace(/_/g, ' ')}</span>
                <span className={`iv-report-qb-score ${(q.score ?? 0) >= 70 ? 'good' : (q.score ?? 0) >= 40 ? 'mid' : 'bad'}`}>
                  {q.score ?? '—'}/100
                </span>
                <span className="iv-report-qb-fb">{q.one_line_feedback || ''}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Next steps */}
      {report.next_steps?.length > 0 && (
        <div className="iv-report-section">
          <h3 className="iv-report-section-title">Next Steps</h3>
          <ol className="iv-report-steps">
            {report.next_steps.map((s, i) => <li key={i}>{s}</li>)}
          </ol>
        </div>
      )}

      <div className="iv-report-actions">
        <button className="action-btn primary" type="button" onClick={onNewInterview}>
          Start New Interview
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
        </button>
      </div>
    </div>
  );
}
