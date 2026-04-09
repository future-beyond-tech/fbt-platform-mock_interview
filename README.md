# Sheikh Mock — AI Interview Simulator

An immersive mock interview app for JavaScript/React roles with real-time AI evaluation. Supports **5 LLM providers**: Ollama (local/free), Groq, Google Gemini, OpenAI, and Anthropic.

## Architecture

```
React (Vite)  ──▶  FastAPI  ──▶  Ollama / Groq / Gemini / OpenAI / Anthropic
  :5173            :8000          (your choice)
```

## Quick Start

### 1. Start the backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 2. Start the frontend

```bash
npm install
npm run dev
```

### 3. Configure your provider

Click the **settings gear** in the top-right corner of the app to:

- Pick a provider (Ollama, Groq, Gemini, OpenAI, or Anthropic)
- Enter your API key for cloud providers, or set backend env vars instead
- Choose a model

Keys entered in the UI are stored locally in your browser and sent to your configured backend only when a provider request is made.

Optional backend env vars:

- `GROQ_API_KEY`
- `GEMINI_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`

**For local/free use:** Install [Ollama](https://ollama.com), run `ollama pull llama3`, and select "Ollama (Local)" in settings.

## Features

- Animated AI interviewer avatar with speech/thinking/reaction states
- Typewriter effect for questions being asked
- Voice input with Groq Whisper or browser speech fallback
- Cinematic dark UI with particle background
- Animated score reveal with ring counter
- In-app settings drawer with per-provider saved models and keys
- 68 curated senior-level JS/React questions across 3 days
- PDF/image upload flow for one tailored question
- Multi-provider support with model selection

## Project Structure

```
sheikh-mock/
├── backend/
│   ├── main.py           # FastAPI — routes + health
│   ├── providers.py       # Ollama / Groq / Gemini / OpenAI / Anthropic adapters
│   ├── questions.py       # 68-question bank
│   └── requirements.txt
├── src/
│   ├── api.js            # Frontend API client
│   ├── App.jsx           # Main app state + routing
│   ├── components/
│   │   ├── Avatar.jsx          # Animated SVG interviewer
│   │   ├── Particles.jsx       # Floating particle background
│   │   ├── ScoreReveal.jsx     # Animated score ring
│   │   ├── WaveformVisualizer.jsx  # Voice waveform
│   │   ├── SettingsDrawer.jsx  # Provider + API key config
│   │   ├── StatusBar.jsx       # Connection status
│   │   ├── StartScreen.jsx
│   │   ├── SessionScreen.jsx
│   │   └── DoneScreen.jsx
│   ├── hooks/
│   │   ├── useVoice.js        # Groq Whisper + Web Speech API
│   │   ├── useTypewriter.js   # Typewriter animation
│   │   └── useSettings.js     # localStorage persistence
│   └── index.css              # Full dark immersive design
├── package.json
└── vite.config.js
```
