import { useState } from 'react';
import { useSelector } from 'react-redux';
import ScoreReveal from './ScoreReveal';
import {
  selectAnswers,
  selectOverallScore,
  selectCategoryScores,
  selectSessionDuration,
} from '../store/interviewSelectors';

function formatLabel(s) {
  if (!s) return '';
  return String(s).replace(/_/g, ' ');
}

function getTagline(score) {
  if (score >= 85) return "You're interview ready.";
  if (score >= 70) return "You're getting there.";
  if (score >= 55) return 'Solid start. Keep going.';
  return 'First session down. Many wins ahead.';
}

function getStatusLabel(score) {
  if (score >= 80) return 'Strong';
  if (score >= 60) return 'Good';
  if (score >= 40) return 'Needs work';
  return 'Focus here';
}

function getStatusCls(score) {
  if (score >= 80) return 'strong';
  if (score >= 60) return 'good';
  if (score >= 40) return 'needs';
  return 'focus';
}

function scoreToVerdict(score) {
  if (score >= 70) return 'correct';
  if (score >= 40) return 'partial';
  return 'incorrect';
}

/** Prefer LLM category_scores (0–10); else Redux-derived rows. */
function buildPerfRows(report, fallbackRows) {
  const cs = report?.category_scores;
  if (cs && typeof cs === 'object' && !Array.isArray(cs) && Object.keys(cs).length > 0) {
    return Object.entries(cs).map(([name, val]) => {
      const raw = typeof val === 'object' && val !== null ? val : { score: val };
      const s10 = Number(raw.score);
      const pct = Number.isFinite(s10)
        ? Math.min(100, Math.max(0, Math.round(s10 * 10)))
        : 0;
      return {
        name,
        score: pct,
        feedback: typeof raw.feedback === 'string' ? raw.feedback : '',
      };
    });
  }
  return fallbackRows.map((r) => ({ name: r.name, score: r.score, feedback: '' }));
}

function hireToneClass(hireText) {
  if (!hireText) return 'report-hire--neutral';
  const t = String(hireText).toLowerCase();
  if (t.includes('no hire')) return 'report-hire--caution';
  if (t.includes('maybe')) return 'report-hire--maybe';
  if (t.includes('strong') || t.includes('hire')) return 'report-hire--positive';
  return 'report-hire--neutral';
}

export default function InterviewReport({ report, blueprint, onNewInterview }) {
  const [view, setView] = useState('summary');
  const answers = useSelector(selectAnswers);
  const overallScore = useSelector(selectOverallScore);
  const categoryScores = useSelector(selectCategoryScores);
  const duration = useSelector(selectSessionDuration);
  const [expandedQ, setExpandedQ] = useState({});

  if (!report) return null;

  const score = report.overall_score ?? overallScore;
  const name = blueprint?.candidate_name || 'Candidate';
  const domain = blueprint?.primary_domain || '';
  const answeredCount = answers.length;
  const totalQ = 12;

  const sorted = [...categoryScores].sort((a, b) => b.score - a.score);
  const strongest = sorted[0];
  const weakest = sorted[sorted.length - 1];
  const strongCount = sorted.filter((c) => c.score >= 60).length;
  const weakCount = sorted.filter((c) => c.score < 60).length;

  const highlights = [...answers]
    .filter((a) => a.score >= 50 && a.answer)
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
    .slice(0, 2);

  const nextSteps = report.next_steps || [];
  const strengths = Array.isArray(report.strengths) ? report.strengths.filter(Boolean) : [];
  const summaryText = typeof report.summary === 'string' ? report.summary.trim() : '';
  const grade = typeof report.grade === 'string' ? report.grade.trim() : '';
  const hireRec = typeof report.hire_recommendation === 'string' ? report.hire_recommendation.trim() : '';

  const perfRows = buildPerfRows(report, categoryScores);
  const qb = Array.isArray(report.question_breakdown) ? report.question_breakdown : [];

  const toggleQ = (i) => setExpandedQ((prev) => ({ ...prev, [i]: !prev[i] }));

  return (
    <div className="db report-debrief slide-up">
      <div className="report-toolbar">
        <div className="report-toolbar-inner">
          <span className="report-toolbar-label">View</span>
          <div className="db-toggle report-segment">
            <button
              className={`db-toggle-btn${view === 'summary' ? ' active' : ''}`}
              type="button"
              onClick={() => setView('summary')}
            >
              Summary
            </button>
            <button
              className={`db-toggle-btn${view === 'detail' ? ' active' : ''}`}
              type="button"
              onClick={() => setView('detail')}
            >
              Full report
            </button>
          </div>
        </div>
      </div>

      {view === 'summary' && (
        <>
          <header className="report-hero">
            <div className="report-hero-ring">
              <ScoreReveal score={Math.round(score)} verdict={scoreToVerdict(score)} />
            </div>
            <div className="report-hero-copy">
              <p className="report-kicker">Session debrief</p>
              <h2 className="report-name">{name}</h2>
              <p className="report-meta">
                {domain || 'Interview candidate'}
                {duration > 0 ? ` · ${duration} min` : ''}
              </p>
              <div className="report-badges">
                {grade && <span className="report-badge report-badge--grade">{grade}</span>}
                {hireRec && (
                  <span className={`report-badge report-hire ${hireToneClass(hireRec)}`}>{hireRec}</span>
                )}
              </div>
              <p className="report-tagline">{getTagline(score)}</p>
              <div className="report-quick">
                {strongest && strongCount > 0 && (
                  <span className="report-quick-item report-quick-item--up">
                    {strongCount} strong {strongCount === 1 ? 'area' : 'areas'}
                  </span>
                )}
                {weakest && weakCount > 0 && weakest.score < 60 && (
                  <span className="report-quick-item report-quick-item--focus">
                    {weakCount} to sharpen
                  </span>
                )}
              </div>
            </div>
          </header>

          {summaryText && (
            <section className="report-exec" aria-label="Executive summary">
              <h3 className="report-exec-title">Summary</h3>
              <p className="report-exec-body">{summaryText}</p>
            </section>
          )}

          {strengths.length > 0 && (
            <section className="report-strengths-block" aria-label="Key strengths">
              <h3 className="report-section-heading">Standout strengths</h3>
              <ul className="report-chip-list">
                {strengths.slice(0, 5).map((s, i) => (
                  <li key={i} className="report-chip">
                    {s}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <div className="report-metrics">
            <div className="report-metric">
              <span className="report-metric-value">
                {answeredCount}
                <span className="report-metric-denom">/{totalQ}</span>
              </span>
              <span className="report-metric-label">Questions answered</span>
            </div>
            <div className="report-metric">
              <span className="report-metric-value report-metric-value--sm">
                {strongest ? formatLabel(strongest.name) : '—'}
              </span>
              <span className="report-metric-label">
                {strongest ? `${strongest.score}% · strongest` : 'Strongest area'}
              </span>
            </div>
            <div className="report-metric">
              <span className="report-metric-value report-metric-value--sm">
                {weakest ? formatLabel(weakest.name) : '—'}
              </span>
              <span className="report-metric-label">
                {weakest ? `${weakest.score}% · grow next` : 'Focus next'}
              </span>
            </div>
          </div>

          {highlights.length > 0 && (
            <section className="report-highlights" aria-label="Answer highlights">
              <h3 className="report-section-heading">Answer highlights</h3>
              <div className="report-highlight-grid">
                {highlights.map((h, i) => (
                  <article key={i} className="report-highlight-card">
                    <div className="report-hl-top">
                      <span className="report-hl-badge">
                        Q{h.questionIndex || i + 1}
                      </span>
                      <span className="report-hl-cat">
                        {formatLabel(h.section || h.category)}
                      </span>
                    </div>
                    <blockquote className="report-hl-quote">
                      “{h.answer?.slice(0, 160)}
                      {h.answer?.length > 160 ? '…' : ''}”
                    </blockquote>
                    {h.strength && <p className="report-hl-note">{h.strength}</p>}
                  </article>
                ))}
              </div>
            </section>
          )}

          {nextSteps.length > 0 && (
            <section className="report-next" aria-label="Next steps">
              <h3 className="report-next-title">What to do next</h3>
              <ol className="db-next-list report-next-list">
                {nextSteps.slice(0, 4).map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ol>
            </section>
          )}
        </>
      )}

      {view === 'detail' && (
        <>
          {qb.length > 0 && (
            <section className="db-section report-glance">
              <h3 className="db-section-title">At a glance</h3>
              <ul className="report-qb">
                {qb.map((row, i) => (
                  <li key={i} className="report-qb-row">
                    <span className="report-qb-n">Q{row.question_number ?? i + 1}</span>
                    <span className="report-qb-score">{row.score ?? '—'}</span>
                    <span className="report-qb-note">{row.one_line_feedback || row.category || ''}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {perfRows.length > 0 && (
            <section className="db-section">
              <h3 className="db-section-title">Performance breakdown</h3>
              {perfRows.map((cat) => (
                <div key={cat.name} className="report-perf-block">
                  <div className="db-perf-row">
                    <span className="db-perf-name">{formatLabel(cat.name)}</span>
                    <div className="db-perf-track">
                      <div
                        className={`db-perf-fill ${getStatusCls(cat.score)}`}
                        style={{ width: `${cat.score}%` }}
                      />
                    </div>
                    <span className="db-perf-pct">{cat.score}%</span>
                    <span className={`db-perf-label ${getStatusCls(cat.score)}`}>
                      {getStatusLabel(cat.score)}
                    </span>
                  </div>
                  {cat.feedback && <p className="report-perf-fb">{cat.feedback}</p>}
                </div>
              ))}
            </section>
          )}

          {answers.length > 0 && (
            <section className="db-section">
              <h3 className="db-section-title">Question by question</h3>
              <div className="db-q-list">
                {answers.map((a, i) => {
                  const open = !!expandedQ[i];
                  return (
                    <div key={i} className={`db-q-card${open ? ' open' : ''}`}>
                      <button
                        className="db-q-toggle"
                        type="button"
                        onClick={() => toggleQ(i)}
                        aria-expanded={open}
                      >
                        <span className="db-q-arrow" aria-hidden>
                          {open ? '▼' : '▶'}
                        </span>
                        <span className="db-q-num">Q{a.questionIndex || i + 1}</span>
                        <span className="db-q-cat">{formatLabel(a.category)}</span>
                        <span className={`db-q-score ${getStatusCls(a.score ?? 0)}`}>
                          {a.score ?? '—'}%
                        </span>
                        <span className="db-q-preview">
                          {a.question?.slice(0, 56)}
                          {a.question?.length > 56 ? '…' : ''}
                        </span>
                      </button>
                      {open && (
                        <div className="db-q-body">
                          <p className="db-q-full">{a.question}</p>
                          <div className="db-q-answer">
                            <span className="db-q-answer-label">Your answer</span>
                            <p>“{a.answer}”</p>
                          </div>
                          {a.strength && (
                            <div className="db-q-covered">
                              <span>Covered</span>
                              <p>{a.strength}</p>
                            </div>
                          )}
                          {a.missing && a.missing !== 'None' && (
                            <div className="db-q-missed">
                              <span>Gap</span>
                              <p>{a.missing}</p>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {(report.improvement_areas?.length > 0 || nextSteps.length > 0) && (
            <section className="db-section">
              <h3 className="db-section-title">Growth path</h3>
              <div className="report-growth">
                <div className="report-growth-start">Now</div>
                {(report.improvement_areas || nextSteps).slice(0, 4).map((item, i) => (
                  <div key={i} className="report-growth-step">
                    <span className="report-growth-num">{i + 1}</span>
                    <p className="report-growth-text">{item}</p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {report.improvement_areas?.length > 0 && (
            <section className="db-section">
              <h3 className="db-section-title">Before your next session</h3>
              <div className="report-study-grid">
                {report.improvement_areas.slice(0, 4).map((topic, i) => (
                  <div key={i} className="report-study-card">
                    <span className="report-study-icon" aria-hidden>
                      ◆
                    </span>
                    <div>
                      <div className="report-study-topic">{topic}</div>
                      <div className="report-study-meta">Suggested focus · ~20 min</div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
      )}

      <footer className="report-actions db-actions">
        <button className="action-btn primary" type="button" onClick={onNewInterview}>
          Start new interview
        </button>
        <button className="action-btn outline" type="button" onClick={() => window.print()}>
          Print / save as PDF
        </button>
      </footer>
    </div>
  );
}
