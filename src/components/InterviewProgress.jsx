// Maps each question position (1-12) to its type for display.
const Q_LABELS = [
  { short: 'I',  label: 'Intro' },          // Q1
  { short: 'R',  label: 'Resume' },         // Q2
  { short: 'T1', label: 'Tier 1' },         // Q3
  { short: 'T1', label: 'Tier 1' },         // Q4
  { short: 'P',  label: 'Project' },        // Q5
  { short: 'T2', label: 'Tier 2' },         // Q6
  { short: 'T2', label: 'Tier 2' },         // Q7
  { short: 'B',  label: 'Behavioral' },     // Q8
  { short: 'T2', label: 'Tier 2' },         // Q9
  { short: 'T3', label: 'Tier 3' },         // Q10
  { short: 'T3', label: 'Tier 3' },         // Q11
  { short: 'W',  label: 'Wrap' },           // Q12
];

const TIER_COLORS = {
  T1: 'var(--accent)',
  T2: '#ffd93d',
  T3: '#ff6b6b',
};

export default function InterviewProgress({ questionNumber, totalQuestions, category, profile, blueprint }) {
  const progress = ((questionNumber - 1) / Math.max(totalQuestions - 1, 1)) * 100;

  return (
    <div className="iv-progress">
      {(profile || blueprint) && (
        <div className="iv-profile-row">
          <div className="iv-profile-block">
            <span className="iv-profile-role">
              {blueprint?.candidate_name || profile?.roles?.[0] || 'Candidate'}
            </span>
            <span className="iv-profile-meta">
              {blueprint?.primary_domain || profile?.domain || 'General'}
              {' · '}
              {blueprint?.seniority_level || profile?.experienceLevel || 'mid'}
              {' · '}
              {blueprint?.experience_years ?? profile?.yearsOfExperience ?? 0} yrs
            </span>
          </div>
        </div>
      )}

      {/* Progress bar */}
      <div className="iv-progress-bar-wrap">
        <div className="iv-progress-bar">
          <div className="iv-progress-fill" style={{ width: `${progress}%` }} />
        </div>
        <span className="iv-progress-label">Q{questionNumber} of {totalQuestions}</span>
      </div>

      {/* Question dots with tier labels */}
      <div className="iv-dots-row">
        {Array.from({ length: totalQuestions }, (_, i) => {
          const qNum = i + 1;
          const isActive = qNum === questionNumber;
          const isPast = qNum < questionNumber;
          const meta = Q_LABELS[i] || { short: `${qNum}`, label: `Q${qNum}` };
          const tierColor = TIER_COLORS[meta.short] || undefined;
          return (
            <div
              key={i}
              className={`iv-dot${isActive ? ' active' : ''}${isPast ? ' past' : ''}`}
              title={`Q${qNum}: ${meta.label}`}
              style={isActive && tierColor ? { borderColor: tierColor, boxShadow: `0 0 0 3px ${tierColor}22` } : undefined}
            >
              <span
                className="iv-dot-num"
                style={isActive && tierColor ? { color: tierColor } : undefined}
              >
                {meta.short}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
