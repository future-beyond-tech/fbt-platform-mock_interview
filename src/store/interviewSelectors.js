export const selectBlueprint  = state => state.interview.blueprint;
export const selectQuestions  = state => state.interview.questions;
export const selectAnswers    = state => state.interview.answers;
export const selectReport     = state => state.interview.report;
export const selectIsComplete = state => state.interview.isComplete;

export const selectOverallScore = state => {
  const answers = state.interview.answers;
  if (!answers.length) return 0;
  const total = answers.reduce((sum, a) => sum + (a.score ?? 0), 0);
  return Math.round(total / answers.length);
};

export const selectCategoryScores = state => {
  const answers = state.interview.answers;
  const categories = {};

  answers.forEach(a => {
    const cat = a.category || 'general';
    if (!categories[cat]) categories[cat] = { total: 0, count: 0 };
    categories[cat].total += a.score ?? 0;
    categories[cat].count += 1;
  });

  return Object.entries(categories).map(([name, data]) => ({
    name,
    score: Math.round(data.total / data.count),
    count: data.count,
  }));
};

export const selectSessionDuration = state => {
  const { sessionStartTime, sessionEndTime } = state.interview;
  if (!sessionStartTime || !sessionEndTime) return 0;
  const diff = new Date(sessionEndTime) - new Date(sessionStartTime);
  return Math.round(diff / 60000);
};
