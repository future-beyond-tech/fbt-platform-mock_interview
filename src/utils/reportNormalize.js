/**
 * Defensive parsing for POST /api/interview/report payloads.
 * LLM shape is defined in backend build_session_report_prompt; models may omit or vary fields.
 */

/** Human-readable labels for session category slugs and similar. */
export function formatCategoryLabel(slug) {
  if (!slug || typeof slug !== 'string') return 'General';
  const s = slug.trim();
  const map = {
    tier_1: 'Tier 1 — Foundations',
    tier_2: 'Tier 2 — Advanced',
    tier_3: 'Tier 3 — Expert',
    domain_concept: 'Domain concepts',
    project_based: 'Project depth',
    behavioral: 'Behavioral',
    intro: 'Introduction',
    completed: 'Completed',
  };
  if (map[s]) return map[s];
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function asTrimmedString(v) {
  if (v == null) return '';
  const t = String(v).trim();
  return t;
}

/** Split summary into short paragraphs for readability. */
export function normalizeSummaryParagraphs(summary) {
  const raw = asTrimmedString(summary);
  if (!raw) return [];
  const byDouble = raw.split(/\n\n+/).map((p) => p.trim()).filter(Boolean);
  if (byDouble.length > 1) return byDouble;
  const bySingle = raw.split(/\n/).map((p) => p.trim()).filter(Boolean);
  if (bySingle.length > 1) return bySingle;
  return [raw];
}

function asStringArray(v, max = 20) {
  if (!Array.isArray(v)) return [];
  return v
    .map((x) => (typeof x === 'string' ? x.trim() : asTrimmedString(x)))
    .filter(Boolean)
    .slice(0, max);
}

/**
 * Model returns category_scores as object of { score: 0-10, feedback: "..." }.
 * Bars use 0-100 scale (score * 10) to align visually with overall_score; label shows x/10.
 */
export function normalizeCategoryDimensions(categoryScores) {
  if (!categoryScores || typeof categoryScores !== 'object' || Array.isArray(categoryScores)) {
    return [];
  }
  const out = [];
  for (const [key, raw] of Object.entries(categoryScores)) {
    if (!raw || typeof raw !== 'object') continue;
    const n = Number(raw.score);
    const score0to10 = Number.isFinite(n) ? Math.max(0, Math.min(10, n)) : 0;
    const feedback = asTrimmedString(raw.feedback);
    const label = formatCategoryLabel(key);
    out.push({
      key,
      label,
      score0to10,
      /** For progress bars: same scale as overall % (10 pt rubric → 0-100). */
      pctForBar: Math.round(score0to10 * 10),
      feedback,
    });
  }
  return out.sort((a, b) => b.score0to10 - a.score0to10);
}

export function normalizeQuestionBreakdown(v) {
  if (!Array.isArray(v)) return [];
  return v
    .map((row, i) => {
      if (!row || typeof row !== 'object') return null;
      const qn = Number(row.question_number);
      const score = Number(row.score);
      return {
        question_number: Number.isFinite(qn) ? qn : i + 1,
        category: asTrimmedString(row.category),
        score: Number.isFinite(score) ? Math.max(0, Math.min(100, Math.round(score))) : null,
        one_line_feedback: asTrimmedString(row.one_line_feedback),
      };
    })
    .filter(Boolean);
}

/** Build lookup: question_number -> one_line_feedback (first wins). */
export function breakdownByQuestionNumber(breakdown) {
  const map = new Map();
  for (const row of breakdown) {
    if (!map.has(row.question_number)) map.set(row.question_number, row);
  }
  return map;
}

export function normalizeReport(report) {
  if (!report || typeof report !== 'object') {
    return {
      summaryParagraphs: [],
      grade: null,
      hireRecommendation: null,
      strengths: [],
      nextSteps: [],
      improvementAreas: [],
      categoryDimensions: [],
      questionBreakdown: [],
    };
  }

  const grade = asTrimmedString(report.grade) || null;
  const hireRecommendation = asTrimmedString(report.hire_recommendation) || null;

  return {
    summaryParagraphs: normalizeSummaryParagraphs(report.summary),
    grade,
    hireRecommendation,
    strengths: asStringArray(report.strengths, 8),
    nextSteps: asStringArray(report.next_steps, 12),
    improvementAreas: asStringArray(report.improvement_areas, 12),
    categoryDimensions: normalizeCategoryDimensions(report.category_scores),
    questionBreakdown: normalizeQuestionBreakdown(report.question_breakdown),
  };
}

/** Verdict for ScoreReveal stroke color from overall 0-100 score. */
export function verdictFromOverallScore(score) {
  const s = Number(score);
  if (!Number.isFinite(s)) return 'partial';
  if (s >= 75) return 'correct';
  if (s >= 45) return 'partial';
  return 'incorrect';
}
