const PHASES = [
  { id: 'introduction', label: 'Intro' },
  { id: 'project_deep_dive', label: 'Projects' },
  { id: 'skill_basic', label: 'Core' },
  { id: 'skill_intermediate', label: 'Intermediate' },
  { id: 'skill_advanced', label: 'Advanced' },
  { id: 'wrap_up', label: 'Wrap' },
];

export default function InterviewProgress({ state, profile }) {
  const activeIndex = PHASES.findIndex(p => p.id === state.phase);

  return (
    <div className="iv-progress">
      {profile && (
        <div className="iv-profile-row">
          <div className="iv-profile-block">
            <span className="iv-profile-role">{profile.roles?.[0] || 'Professional'}</span>
            <span className="iv-profile-meta">
              {profile.domain} · {profile.experienceLevel} · {profile.yearsOfExperience} yrs
              {profile.isTechnical ? ' · technical' : ' · non-technical'}
            </span>
          </div>
        </div>
      )}

      <div className="iv-phase-bar">
        {PHASES.map((p, i) => {
          const isActive = i === activeIndex;
          const isPast = i < activeIndex;
          return (
            <div
              key={p.id}
              className={`iv-phase-chip${isActive ? ' active' : ''}${isPast ? ' past' : ''}`}
            >
              <span className="iv-phase-dot" />
              <span className="iv-phase-label">{p.label}</span>
            </div>
          );
        })}
      </div>

      <div className="iv-meta-row">
        <div className="iv-difficulty" title="Difficulty level">
          {'⭐'.repeat(state.difficultyLevel)}
          <span className="iv-difficulty-text">Lvl {state.difficultyLevel}</span>
        </div>

        {state.extractedSkills.length > 0 && (
          <div className="iv-skills">
            <span className="iv-skills-label">Skills:</span>
            {state.extractedSkills.slice(0, 6).map(skill => (
              <span key={skill} className="iv-skill-tag">{skill}</span>
            ))}
            {state.extractedSkills.length > 6 && (
              <span className="iv-skill-tag iv-skill-more">+{state.extractedSkills.length - 6}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
