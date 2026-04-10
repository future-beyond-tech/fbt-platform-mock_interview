import { useSelector } from 'react-redux';
import {
  selectAnswers,
  selectOverallScore,
  selectCategoryScores,
  selectSessionDuration,
} from '../store/interviewSelectors';

function getMotivation(score) {
  if (score >= 85) return {
    emoji: '\uD83C\uDF1F',
    headline: 'Outstanding Performance!',
    message: "You're clearly operating at a high level. Companies would be lucky to have you. Keep this momentum going!",
    color: '#64ffda',
  };
  if (score >= 70) return {
    emoji: '\uD83D\uDE80',
    headline: 'Strong Performance!',
    message: "You've got solid fundamentals and real depth. A few focused improvements and you'll be absolutely interview-ready.",
    color: '#3B82F6',
  };
  if (score >= 55) return {
    emoji: '\uD83D\uDCAA',
    headline: 'Good Start \u2014 Keep Pushing!',
    message: "You showed real potential today. Every expert was once a beginner. The gaps identified are your roadmap \u2014 work them.",
    color: '#ffd93d',
  };
  return {
    emoji: '\uD83D\uDD25',
    headline: 'Every Expert Started Here!',
    message: "This is just the beginning. The fact that you showed up and practiced puts you ahead of 90% of candidates. Review the feedback and come back stronger.",
    color: '#ff6b6b',
  };
}

function getHireBadge(rec) {
  const map = {
    'Strong Hire': { icon: '\u2705', cls: 'hire-strong' },
    'Hire':        { icon: '\uD83D\uDC4D', cls: 'hire-yes' },
    'Maybe':       { icon: '\uD83E\uDD14', cls: 'hire-maybe' },
    'No Hire':     { icon: '\u274C', cls: 'hire-no' },
  };
  return map[rec] || map['Maybe'];
}

export default function InterviewReport({ report, blueprint, onNewInterview }) {
  const reduxAnswers    = useSelector(selectAnswers);
  const overallScore    = useSelector(selectOverallScore);
  const categoryScores  = useSelector(selectCategoryScores);
  const duration        = useSelector(selectSessionDuration);

  if (!report) return null;

  const score = report.overall_score ?? overallScore;
  const motivation = getMotivation(score);
  const hireBadge = getHireBadge(report.hire_recommendation);
  const catScores = report.category_scores || {};
  const answers = reduxAnswers.length > 0 ? reduxAnswers : [];

  return (
    <div className="rpt slide-up">

      {/* Header */}
      <div className="rpt-header">
        <h2 className="rpt-title">Interview Complete</h2>
        {blueprint && (
          <p className="rpt-sub">
            {blueprint.candidate_name || 'Candidate'} · {blueprint.primary_domain} · {duration > 0 ? `${duration} mins` : ''}
          </p>
        )}
      </div>

      {/* Motivation Banner */}
      <div className="rpt-motivation" style={{ borderColor: motivation.color }}>
        <span className="rpt-motivation-emoji">{motivation.emoji}</span>
        <div>
          <h3 className="rpt-motivation-headline" style={{ color: motivation.color }}>
            {motivation.headline}
          </h3>
          <p className="rpt-motivation-msg">{motivation.message}</p>
        </div>
      </div>

      {/* Score + Grade + Hire */}
      <div className="rpt-score-row">
        <div className="rpt-ring">
          <svg width="130" height="130" viewBox="0 0 130 130">
            <circle cx="65" cy="65" r="55" fill="none" stroke="var(--bg-3)" strokeWidth="10" />
            <circle cx="65" cy="65" r="55" fill="none"
              stroke={motivation.color} strokeWidth="10"
              strokeDasharray={`${(score / 100) * 345.6} 345.6`}
              strokeLinecap="round" transform="rotate(-90 65 65)"
              style={{ transition: 'stroke-dasharray 1s ease' }}
            />
            <text x="65" y="60" textAnchor="middle" fill={motivation.color} fontSize="28" fontWeight="800">{score}</text>
            <text x="65" y="80" textAnchor="middle" fill="var(--text-3)" fontSize="11">out of 100</text>
          </svg>
        </div>

        <div className="rpt-grade-block">
          <div className="rpt-grade" style={{ color: motivation.color }}>
            {report.grade || '\u2014'}
          </div>
          <div className="rpt-grade-label">Grade</div>
        </div>

        <div className={`rpt-hire-badge ${hireBadge.cls}`}>
          <span>{hireBadge.icon}</span>
          <div>
            <div className="rpt-hire-label">Recommendation</div>
            <div className="rpt-hire-value">{report.hire_recommendation || '\u2014'}</div>
          </div>
        </div>
      </div>

      {/* Summary */}
      {report.summary && (
        <div className="rpt-card rpt-summary-card">
          <p className="rpt-summary-text">{report.summary}</p>
        </div>
      )}

      {/* Category Breakdown */}
      {(Object.keys(catScores).length > 0 || categoryScores.length > 0) && (
        <div className="rpt-card">
          <h3 className="rpt-card-title">Performance Breakdown</h3>
          {(categoryScores.length > 0 ? categoryScores : Object.entries(catScores).map(([k, v]) => ({ name: k, score: (v?.score ?? 0) * 10 }))).map(cat => (
            <div key={cat.name} className="rpt-bar-row">
              <span className="rpt-bar-name">{cat.name.replace(/_/g, ' ')}</span>
              <div className="rpt-bar-track">
                <div
                  className="rpt-bar-fill"
                  style={{
                    width: `${cat.score}%`,
                    background: cat.score >= 70 ? 'var(--accent)' : cat.score >= 50 ? 'var(--yellow)' : 'var(--red)',
                  }}
                />
              </div>
              <span className="rpt-bar-pct">{cat.score}%</span>
            </div>
          ))}
        </div>
      )}

      {/* Strengths */}
      {report.strengths?.length > 0 && (
        <div className="rpt-card">
          <h3 className="rpt-card-title">Your Strengths</h3>
          <ul className="rpt-list rpt-list--good">
            {report.strengths.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      )}

      {/* Improvement Areas */}
      {report.improvement_areas?.length > 0 && (
        <div className="rpt-card">
          <h3 className="rpt-card-title">Areas to Improve</h3>
          <p className="rpt-improve-note">These aren't weaknesses — they're your next milestones. Every one is learnable.</p>
          <ul className="rpt-list rpt-list--improve">
            {report.improvement_areas.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      )}

      {/* Question by Question */}
      {answers.length > 0 && (
        <div className="rpt-card">
          <h3 className="rpt-card-title">Question by Question</h3>
          <div className="rpt-qlist">
            {answers.map((a, i) => (
              <div key={i} className="rpt-qitem">
                <div className="rpt-qitem-header">
                  <span className="rpt-qitem-num">Q{a.questionIndex || i + 1}</span>
                  <span className="rpt-qitem-cat">{(a.category || '').replace(/_/g, ' ')}</span>
                  <span className={`rpt-qitem-score ${(a.score ?? 0) >= 70 ? 'good' : (a.score ?? 0) >= 40 ? 'mid' : 'bad'}`}>
                    {a.score ?? '\u2014'}/100
                  </span>
                </div>
                <p className="rpt-qitem-q">{a.question}</p>
                <p className="rpt-qitem-a"><strong>Your answer:</strong> {a.answer}</p>
                {a.strength && <p className="rpt-qitem-fb">Covered: {a.strength}</p>}
                {a.missing && a.missing !== 'None' && <p className="rpt-qitem-miss">Missed: {a.missing}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Next Steps / Action Plan */}
      {report.next_steps?.length > 0 && (
        <div className="rpt-card rpt-action-card">
          <h3 className="rpt-card-title">Your Action Plan</h3>
          <ol className="rpt-steps">
            {report.next_steps.map((s, i) => <li key={i}>{s}</li>)}
          </ol>
        </div>
      )}

      {/* Final Motivation */}
      <div className="rpt-final">
        <p className="rpt-quote">"The expert in anything was once a beginner."</p>
        <p className="rpt-quote-sub">Every interview you practice makes the real one easier.</p>
      </div>

      {/* Actions */}
      <div className="rpt-actions">
        <button className="action-btn primary" type="button" onClick={onNewInterview}>
          Start New Interview
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
        </button>
        <button className="action-btn outline" type="button" onClick={() => window.print()}>
          Download Report
        </button>
      </div>
    </div>
  );
}
