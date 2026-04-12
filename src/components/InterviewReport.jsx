import { useState, useMemo } from 'react';
import { useSelector } from 'react-redux';
import { selectAnswers as selectReduxAnswers, selectSessionDuration } from '../store/interviewSelectors';
import ScoreReveal from './ScoreReveal';
import Badge from './ui/Badge';
import {
  normalizeReport,
  formatCategoryLabel,
  verdictFromOverallScore,
  breakdownByQuestionNumber,
} from '../utils/reportNormalize';

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

function buildCategoryScores(answers) {
  const categories = {};

  answers.forEach((answer) => {
    const category = answer.category || 'general';
    if (!categories[category]) categories[category] = { total: 0, count: 0 };
    categories[category].total += answer.score ?? 0;
    categories[category].count += 1;
  });

  return Object.entries(categories).map(([name, data]) => ({
    name,
    score: Math.round(data.total / data.count),
    count: data.count,
  }));
}

function getAverageScore(answers) {
  if (!answers.length) return 0;
  const total = answers.reduce((sum, answer) => sum + (answer.score ?? 0), 0);
  return Math.round(total / answers.length);
}

function gapLinesFromAnswer(a) {
  if (!a) return [];
  if (Array.isArray(a.gaps) && a.gaps.length > 0) {
    return a.gaps.map((s) => String(s).trim()).filter(Boolean).slice(0, 2);
  }
  const m = a.missing;
  if (!m || m === 'None') return [];
  if (m.includes(' · ')) {
    return m.split(' · ').map((s) => s.trim()).filter(Boolean).slice(0, 2);
  }
  return [m];
}

function showStrengthLine(strength) {
  if (!strength || typeof strength !== 'string') return false;
  const t = strength.trim();
  if (!t || t === 'Nothing significant') return false;
  if (/^evaluation error/i.test(t)) return false;
  return true;
}

function hireBadgeTone(hire) {
  const h = (hire || '').toLowerCase();
  if (h.includes('strong')) return 'success';
  if (h.startsWith('hire') && !h.includes('no')) return 'accent';
  if (h.includes('maybe')) return 'warning';
  if (h.includes('no')) return 'danger';
  return 'info';
}

const NEXT_STEPS_INITIAL = 5;

export default function InterviewReport({ report, blueprint, answers: persistedAnswers = [], onNewInterview }) {
  const [view, setView] = useState('summary');
  const [nextStepsExpanded, setNextStepsExpanded] = useState(false);
  const reduxAnswers = useSelector(selectReduxAnswers);
  const duration = useSelector(selectSessionDuration);
  const answers = persistedAnswers.length > 0 ? persistedAnswers : reduxAnswers;
  const categoryScoresFromAnswers = buildCategoryScores(answers);
  const [expandedQ, setExpandedQ] = useState({});

  const normalized = useMemo(() => normalizeReport(report), [report]);
  const breakdownMap = useMemo(
    () => breakdownByQuestionNumber(normalized.questionBreakdown),
    [normalized.questionBreakdown],
  );

  if (!report) return null;

  const score = report.overall_score ?? getAverageScore(answers);
  const name = blueprint?.candidate_name || 'Candidate';
  const domain = blueprint?.primary_domain || '';
  const answeredCount = answers.length;
  const totalQ = 14;

  const sortedAnswerCats = [...categoryScoresFromAnswers].sort((a, b) => b.score - a.score);
  const strongest = sortedAnswerCats[0];
  const weakest = sortedAnswerCats[sortedAnswerCats.length - 1];

  const dims = normalized.categoryDimensions;
  const bestDim = dims[0];
  const worstDim = dims.length ? dims[dims.length - 1] : null;

  const highlights = [...answers]
    .filter((a) => a.score >= 50 && a.answer)
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
    .slice(0, 2);

  const nextSteps = normalized.nextSteps;
  const nextStepsVisible = nextStepsExpanded ? nextSteps : nextSteps.slice(0, NEXT_STEPS_INITIAL);
  const hasMoreNextSteps = nextSteps.length > NEXT_STEPS_INITIAL;

  const toggleQ = (i) => setExpandedQ((prev) => ({ ...prev, [i]: !prev[i] }));

  const useDimensionBreakdown = dims.length > 0;

  return (
    <div className="db db-report slide-up">

      {view === 'summary' && (
        <>
          <div className="db-hero">
            <div className="db-hero-main">
              <ScoreReveal score={Math.round(score)} verdict={verdictFromOverallScore(score)} />
              <div className="db-hero-copy">
                <h2 className="db-name">{name}</h2>
                <p className="db-meta">
                  {domain}
                  {duration > 0 ? ` · ${duration} mins` : ''}
                </p>
                <div className="db-hero-scoreline">
                  <span className="db-hero-score-num">{Math.round(score)}</span>
                  <span className="db-hero-score-suffix">/ 100</span>
                </div>
                <p className="db-tagline">{getTagline(score)}</p>
                <div className="db-badge-row">
                  {normalized.grade && (
                    <Badge tone="info" className="db-chip">
                      Grade {normalized.grade}
                    </Badge>
                  )}
                  {normalized.hireRecommendation && (
                    <Badge tone={hireBadgeTone(normalized.hireRecommendation)} className="db-chip">
                      {normalized.hireRecommendation}
                    </Badge>
                  )}
                </div>
              </div>
            </div>
            <div className="db-quick-stats">
              {strongest && (
                <span className="db-qs good">
                  ✓ {sortedAnswerCats.filter((c) => c.score >= 60).length} strong answers
                </span>
              )}
              {weakest && weakest.score < 60 && (
                <span className="db-qs improve">
                  → {sortedAnswerCats.filter((c) => c.score < 60).length} areas to level up
                </span>
              )}
            </div>
          </div>

          {normalized.summaryParagraphs.length > 0 && (
            <div className="db-summary-card">
              <h3 className="db-summary-title">Executive summary</h3>
              {normalized.summaryParagraphs.map((p, i) => (
                <p key={i} className="db-summary-p">{p}</p>
              ))}
            </div>
          )}

          <div className="db-stat-row">
            <div className="db-stat-card">
              <div className="db-stat-value">
                {answeredCount}
                {' '}
                <span className="db-stat-muted">/ {totalQ}</span>
              </div>
              <div className="db-stat-label">Questions answered</div>
            </div>
            <div className="db-stat-card">
              {useDimensionBreakdown && bestDim ? (
                <>
                  <div className="db-stat-value" title={bestDim.feedback || undefined}>
                    {bestDim.label}
                  </div>
                  <div className="db-stat-label">
                    Strongest dimension · {bestDim.score0to10}/10
                  </div>
                </>
              ) : (
                <>
                  <div className="db-stat-value">
                    {strongest ? formatCategoryLabel(strongest.name) : '—'}
                  </div>
                  <div className="db-stat-label">
                    {strongest ? `${strongest.score}% avg` : 'Strongest topic'}
                  </div>
                </>
              )}
            </div>
            <div className="db-stat-card">
              {useDimensionBreakdown && worstDim ? (
                <>
                  <div className="db-stat-value" title={worstDim.feedback || undefined}>
                    {worstDim.label}
                  </div>
                  <div className="db-stat-label">
                    Focus next · {worstDim.score0to10}/10
                  </div>
                </>
              ) : (
                <>
                  <div className="db-stat-value">
                    {weakest ? formatCategoryLabel(weakest.name) : '—'}
                  </div>
                  <div className="db-stat-label">
                    {weakest ? `${weakest.score}% avg` : 'Growth area'}
                  </div>
                </>
              )}
            </div>
          </div>

          {normalized.strengths.length > 0 && (
            <div className="db-strengths-card">
              <h3 className="db-strengths-title">What you showed well</h3>
              <ul className="db-strengths-list">
                {normalized.strengths.slice(0, 5).map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          )}

          {highlights.length > 0 && (
            <div className="db-highlights">
              {highlights.map((h, i) => (
                <div key={i} className="db-highlight-card">
                  <div className="db-hl-header">
                    Q{h.questionIndex || i + 1}
                    {' · '}
                    {formatCategoryLabel(h.section || h.category || '')}
                  </div>
                  <p className="db-hl-quote">
                    &ldquo;{h.answer?.slice(0, 120)}
                    {h.answer?.length > 120 ? '…' : ''}
                    &rdquo;
                  </p>
                  {showStrengthLine(h.strength) && (
                    <p className="db-hl-why">✓ {h.strength}</p>
                  )}
                </div>
              ))}
            </div>
          )}

          {nextSteps.length > 0 && (
            <div className="db-next">
              <h3 className="db-next-title">What to do next</h3>
              <ol className="db-next-list">
                {nextStepsVisible.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ol>
              {hasMoreNextSteps && (
                <button
                  type="button"
                  className="db-next-toggle"
                  onClick={() => setNextStepsExpanded((e) => !e)}
                >
                  {nextStepsExpanded ? 'Show fewer' : `Show all (${nextSteps.length})`}
                </button>
              )}
            </div>
          )}
        </>
      )}

      {view === 'detail' && (
        <>
          {useDimensionBreakdown ? (
            <div className="db-section">
              <h3 className="db-section-title">Performance by dimension</h3>
              <p className="db-section-hint">Scores are out of 10 (rubric from your session report).</p>
              {dims.map((d) => (
                <div key={d.key} className="db-dim-row">
                  <div className="db-dim-head">
                    <span className="db-dim-label">{d.label}</span>
                    <span className={`db-dim-score ${getStatusCls(d.pctForBar)}`}>
                      {d.score0to10}/10
                    </span>
                  </div>
                  <div className="db-perf-track">
                    <div
                      className={`db-perf-fill ${getStatusCls(d.pctForBar)}`}
                      style={{ width: `${d.pctForBar}%` }}
                    />
                  </div>
                  {d.feedback && <p className="db-dim-feedback">{d.feedback}</p>}
                </div>
              ))}
            </div>
          ) : (
            categoryScoresFromAnswers.length > 0 && (
              <div className="db-section">
                <h3 className="db-section-title">Performance breakdown</h3>
                <p className="db-section-hint">Averages from your per-question scores.</p>
                {categoryScoresFromAnswers.map((cat) => (
                  <div key={cat.name} className="db-perf-row">
                    <span className="db-perf-name">{formatCategoryLabel(cat.name)}</span>
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
                ))}
              </div>
            )
          )}

          {answers.length > 0 && (
            <div className="db-section">
              <h3 className="db-section-title">Question by question</h3>
              <div className="db-q-list">
                {answers.map((a, i) => {
                  const open = !!expandedQ[i];
                  const qn = a.questionIndex || i + 1;
                  const bd = breakdownMap.get(qn);
                  const coachLine = bd?.one_line_feedback;
                  return (
                    <div key={i} className={`db-q-card${open ? ' open' : ''}`}>
                      <button className="db-q-toggle" type="button" onClick={() => toggleQ(i)}>
                        <span className="db-q-arrow">{open ? '▼' : '▶'}</span>
                        <span className="db-q-num">Q{qn}</span>
                        <span className="db-q-cat">{formatCategoryLabel(a.category || '')}</span>
                        <span className={`db-q-score ${getStatusCls(a.score ?? 0)}`}>
                          {a.score ?? '—'}%
                        </span>
                        <span className="db-q-preview-wrap">
                          <span className="db-q-preview">
                            {a.question?.slice(0, 48)}
                            {a.question?.length > 48 ? '…' : ''}
                          </span>
                          {coachLine && (
                            <span className="db-q-coach">{coachLine}</span>
                          )}
                        </span>
                      </button>
                      {open && (
                        <div className="db-q-body">
                          <p className="db-q-full">{a.question}</p>
                          {coachLine && (
                            <div className="db-q-coach-open">
                              <span className="db-q-coach-label">Session insight</span>
                              <p>{coachLine}</p>
                            </div>
                          )}
                          <div className="db-q-answer">
                            <span className="db-q-answer-label">Your answer</span>
                            <p>&ldquo;{a.answer}&rdquo;</p>
                          </div>
                          {showStrengthLine(a.strength) && (
                            <div className="db-q-covered">
                              <span>✓</span>
                              <p>{a.strength}</p>
                            </div>
                          )}
                          {gapLinesFromAnswer(a).map((line, gi) => (
                            <div key={gi} className="db-q-gap">
                              <span>◎</span>
                              <p>{line}</p>
                            </div>
                          ))}
                          {a.hint && String(a.hint).trim() && (
                            <div className="db-q-redirect">
                              <span>→</span>
                              <p>{a.hint}</p>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {normalized.improvementAreas.length > 0 && (
            <div className="db-section">
              <h3 className="db-section-title">Growth map</h3>
              <p className="db-section-hint">Focus areas from this session (not your action checklist).</p>
              <div className="db-growth">
                <div className="db-growth-start">You are here</div>
                {normalized.improvementAreas.slice(0, 5).map((item, idx) => (
                  <div key={idx} className="db-growth-node">
                    <div className="db-growth-line" />
                    <div className="db-growth-box">{item}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {normalized.improvementAreas.length > 0 && (
            <div className="db-section">
              <h3 className="db-section-title">Before your next session</h3>
              <div className="db-study-list">
                {normalized.improvementAreas.slice(0, 4).map((topic, idx) => (
                  <div key={idx} className="db-study-card">
                    <div className="db-study-topic">{topic}</div>
                    <div className="db-study-meta">Focus area · ~20 mins</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      <div className="db-actions">
        <button className="action-btn primary" type="button" onClick={onNewInterview}>
          Start New Interview
        </button>
        <button className="action-btn outline" type="button" onClick={() => window.print()}>
          Download Report
        </button>
      </div>

      <div className="db-toggle-wrap">
        <div className="db-toggle">
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
            Full Report
          </button>
        </div>
      </div>
    </div>
  );
}
