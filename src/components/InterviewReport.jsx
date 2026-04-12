import { useState } from 'react';
import { useSelector } from 'react-redux';
import {
  selectAnswers,
  selectOverallScore,
  selectCategoryScores,
  selectSessionDuration,
} from '../store/interviewSelectors';

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
  const totalQ = 14; // 12 blueprint + up to 2 extra tier probes

  // Find strongest & weakest categories.
  const sorted = [...categoryScores].sort((a, b) => b.score - a.score);
  const strongest = sorted[0];
  const weakest = sorted[sorted.length - 1];

  // Pick 2 best answers for highlight reel.
  const highlights = [...answers]
    .filter(a => a.score >= 50 && a.answer)
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
    .slice(0, 2);

  const nextSteps = report.next_steps || [];

  const toggleQ = (i) => setExpandedQ(prev => ({ ...prev, [i]: !prev[i] }));

  return (
    <div className="db slide-up">

      {/* ── Summary View ── */}
      {view === 'summary' && (
        <>
          {/* Headline Block */}
          <div className="db-headline">
            <h2 className="db-name">{name}</h2>
            <p className="db-meta">{domain}{duration > 0 ? ` \u00B7 ${duration} mins` : ''}</p>
            <div className="db-score">{score}</div>
            <p className="db-tagline">{getTagline(score)}</p>
            <div className="db-quick-stats">
              {strongest && <span className="db-qs good">{'\u2713'} {sorted.filter(c => c.score >= 60).length} questions strong</span>}
              {weakest && weakest.score < 60 && <span className="db-qs improve">{'\u2192'} {sorted.filter(c => c.score < 60).length} areas to level up</span>}
            </div>
          </div>

          {/* 3 Stat Cards */}
          <div className="db-stat-row">
            <div className="db-stat-card">
              <div className="db-stat-value">{answeredCount} / {totalQ}</div>
              <div className="db-stat-label">answered</div>
            </div>
            <div className="db-stat-card">
              <div className="db-stat-value">{strongest?.name?.replace(/_/g, ' ') || '\u2014'}</div>
              <div className="db-stat-label">{strongest ? `${strongest.score}%` : 'strongest'}</div>
            </div>
            <div className="db-stat-card">
              <div className="db-stat-value">{weakest?.name?.replace(/_/g, ' ') || '\u2014'}</div>
              <div className="db-stat-label">{weakest ? `${weakest.score}%` : 'focus here'}</div>
            </div>
          </div>

          {/* Highlight Reel */}
          {highlights.length > 0 && (
            <div className="db-highlights">
              {highlights.map((h, i) => (
                <div key={i} className="db-highlight-card">
                  <div className="db-hl-header">
                    Q{h.questionIndex || i + 1} {'\u00B7'} {(h.section || h.category || '').replace(/_/g, ' ')}
                  </div>
                  <p className="db-hl-quote">"{h.answer?.slice(0, 120)}{h.answer?.length > 120 ? '...' : ''}"</p>
                  {showStrengthLine(h.strength) && (
                    <p className="db-hl-why">{'\u2713'} {h.strength}</p>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Next Steps */}
          {nextSteps.length > 0 && (
            <div className="db-next">
              <h3 className="db-next-title">What to do next</h3>
              <ol className="db-next-list">
                {nextSteps.slice(0, 3).map((s, i) => <li key={i}>{s}</li>)}
              </ol>
            </div>
          )}
        </>
      )}

      {/* ── Detail View ── */}
      {view === 'detail' && (
        <>
          {/* Performance Breakdown */}
          {categoryScores.length > 0 && (
            <div className="db-section">
              <h3 className="db-section-title">Performance Breakdown</h3>
              {categoryScores.map(cat => (
                <div key={cat.name} className="db-perf-row">
                  <span className="db-perf-name">{cat.name.replace(/_/g, ' ')}</span>
                  <div className="db-perf-track">
                    <div className={`db-perf-fill ${getStatusCls(cat.score)}`} style={{ width: `${cat.score}%` }} />
                  </div>
                  <span className="db-perf-pct">{cat.score}%</span>
                  <span className={`db-perf-label ${getStatusCls(cat.score)}`}>{getStatusLabel(cat.score)}</span>
                </div>
              ))}
            </div>
          )}

          {/* Question by Question — collapsible */}
          {answers.length > 0 && (
            <div className="db-section">
              <h3 className="db-section-title">Question by Question</h3>
              <div className="db-q-list">
                {answers.map((a, i) => {
                  const open = !!expandedQ[i];
                  return (
                    <div key={i} className={`db-q-card${open ? ' open' : ''}`}>
                      <button className="db-q-toggle" type="button" onClick={() => toggleQ(i)}>
                        <span className="db-q-arrow">{open ? '\u25BC' : '\u25B6'}</span>
                        <span className="db-q-num">Q{a.questionIndex || i + 1}</span>
                        <span className="db-q-cat">{(a.category || '').replace(/_/g, ' ')}</span>
                        <span className={`db-q-score ${getStatusCls(a.score ?? 0)}`}>{a.score ?? '\u2014'}%</span>
                        <span className="db-q-preview">{a.question?.slice(0, 50)}{a.question?.length > 50 ? '...' : ''}</span>
                      </button>
                      {open && (
                        <div className="db-q-body">
                          <p className="db-q-full">{a.question}</p>
                          <div className="db-q-answer">
                            <span className="db-q-answer-label">Your answer</span>
                            <p>"{a.answer}"</p>
                          </div>
                          {showStrengthLine(a.strength) && (
                            <div className="db-q-covered">
                              <span>{'\u2713'}</span>
                              <p>{a.strength}</p>
                            </div>
                          )}
                          {gapLinesFromAnswer(a).map((line, gi) => (
                            <div key={gi} className="db-q-gap">
                              <span>{'\u25CE'}</span>
                              <p>{line}</p>
                            </div>
                          ))}
                          {a.hint && String(a.hint).trim() && (
                            <div className="db-q-redirect">
                              <span>{'\u2192'}</span>
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

          {/* Growth Map */}
          {(report.improvement_areas?.length > 0 || nextSteps.length > 0) && (
            <div className="db-section">
              <h3 className="db-section-title">Growth Map</h3>
              <div className="db-growth">
                <div className="db-growth-start">You are here</div>
                {(report.improvement_areas || nextSteps).slice(0, 3).map((item, i) => (
                  <div key={i} className="db-growth-node">
                    <div className="db-growth-line" />
                    <div className="db-growth-box">{item}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Study List */}
          {report.improvement_areas?.length > 0 && (
            <div className="db-section">
              <h3 className="db-section-title">Before your next session</h3>
              <div className="db-study-list">
                {report.improvement_areas.slice(0, 4).map((topic, i) => (
                  <div key={i} className="db-study-card">
                    <div className="db-study-topic">{topic}</div>
                    <div className="db-study-meta">Focus area {'\u00B7'} ~20 mins</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Actions */}
      <div className="db-actions">
        <button className="action-btn primary" type="button" onClick={onNewInterview}>
          Start New Interview
        </button>
        <button className="action-btn outline" type="button" onClick={() => window.print()}>
          Download Report
        </button>
      </div>

      {/* Toggle Pill — fixed bottom */}
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
