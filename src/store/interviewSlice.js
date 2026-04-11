import { createSlice } from '@reduxjs/toolkit';

const initialState = {
  blueprint: null,
  questions: [],
  answers: [],         // { questionIndex, question, answer, score, category, tier, topic }
  sessionStartTime: null,
  sessionEndTime: null,
  isComplete: false,
  report: null,
};

const interviewSlice = createSlice({
  name: 'interview',
  initialState,
  reducers: {
    setBlueprint: (state, action) => {
      state.blueprint = action.payload;
      state.questions = [];
      state.answers = [];
      state.report = null;
      state.isComplete = false;
      state.sessionEndTime = null;
      state.sessionStartTime = new Date().toISOString();
    },

    addQuestion: (state, action) => {
      state.questions.push(action.payload);
    },

    submitAnswer: (state, action) => {
      const existing = state.answers.findIndex(
        a => a.questionIndex === action.payload.questionIndex
      );
      if (existing >= 0) {
        state.answers[existing] = action.payload;
      } else {
        state.answers.push(action.payload);
      }
    },

    setReport: (state, action) => {
      state.report = action.payload;
      state.sessionEndTime = new Date().toISOString();
      state.isComplete = true;
    },

    resetInterview: () => initialState,
  },
});

export const {
  setBlueprint,
  addQuestion,
  submitAnswer,
  setReport,
  resetInterview,
} = interviewSlice.actions;

export default interviewSlice.reducer;
