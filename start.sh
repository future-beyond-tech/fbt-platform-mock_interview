#!/usr/bin/env bash
# ─────────────────────────────────────────────────
# Sheikh Mock — Start both backend and frontend
# Usage:  ./start.sh
# ─────────────────────────────────────────────────

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT=8000
FRONTEND_PORT=5173

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

cleanup() {
  echo ""
  echo -e "${YELLOW}Shutting down...${NC}"
  kill $BACKEND_PID 2>/dev/null || true
  kill $FRONTEND_PID 2>/dev/null || true
  wait $BACKEND_PID 2>/dev/null || true
  wait $FRONTEND_PID 2>/dev/null || true
  echo -e "${GREEN}Done.${NC}"
  exit 0
}
trap cleanup SIGINT SIGTERM

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  Sheikh Mock — AI Interview Simulator${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ── Check prerequisites ──
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
  echo -e "${RED}✗ Python 3 not found. Install it from https://python.org${NC}"
  exit 1
fi
PYTHON=$(command -v python3 || command -v python)

if ! command -v node &>/dev/null; then
  echo -e "${RED}✗ Node.js not found. Install it from https://nodejs.org${NC}"
  exit 1
fi

if ! command -v npm &>/dev/null; then
  echo -e "${RED}✗ npm not found.${NC}"
  exit 1
fi

echo -e "${GREEN}✓ Python:  $($PYTHON --version)${NC}"
echo -e "${GREEN}✓ Node:    $(node --version)${NC}"
echo -e "${GREEN}✓ npm:     $(npm --version)${NC}"

# Check Ollama (optional)
if command -v ollama &>/dev/null; then
  echo -e "${GREEN}✓ Ollama:  installed${NC}"
  if curl -s http://localhost:11434/api/tags &>/dev/null; then
    echo -e "${GREEN}✓ Ollama:  running${NC}"
  else
    echo -e "${YELLOW}⚠ Ollama installed but not running. Start it with: ollama serve${NC}"
  fi
else
  echo -e "${YELLOW}⚠ Ollama not installed (optional — use a cloud provider instead)${NC}"
fi

echo ""

# ── Install backend dependencies ──
echo -e "${CYAN}Installing backend dependencies...${NC}"
cd "$ROOT/backend"
if ! $PYTHON -m pip install -r requirements.txt; then
  echo -e "${RED}✗ Backend dependency install failed${NC}"
  exit 1
fi
echo -e "${GREEN}✓ Backend dependencies ready${NC}"

# ── Install frontend dependencies ──
echo -e "${CYAN}Installing frontend dependencies...${NC}"
cd "$ROOT"
if [ -f "package-lock.json" ]; then
  if ! npm ci; then
    echo -e "${RED}✗ Frontend dependency install failed${NC}"
    exit 1
  fi
else
  if ! npm install; then
    echo -e "${RED}✗ Frontend dependency install failed${NC}"
    exit 1
  fi
fi
echo -e "${GREEN}✓ Frontend dependencies ready${NC}"
echo ""

# ── Start backend ──
echo -e "${CYAN}Starting backend on port $BACKEND_PORT...${NC}"
cd "$ROOT/backend"
$PYTHON -m uvicorn main:app --host 0.0.0.0 --port $BACKEND_PORT --reload &
BACKEND_PID=$!
sleep 2

if kill -0 $BACKEND_PID 2>/dev/null; then
  echo -e "${GREEN}✓ Backend running  →  http://localhost:$BACKEND_PORT${NC}"
else
  echo -e "${RED}✗ Backend failed to start${NC}"
  exit 1
fi

# ── Start frontend ──
echo -e "${CYAN}Starting frontend on port $FRONTEND_PORT...${NC}"
cd "$ROOT"
npx vite --port $FRONTEND_PORT &
FRONTEND_PID=$!
sleep 2

if kill -0 $FRONTEND_PID 2>/dev/null; then
  echo -e "${GREEN}✓ Frontend running →  http://localhost:$FRONTEND_PORT${NC}"
else
  echo -e "${RED}✗ Frontend failed to start${NC}"
  kill $BACKEND_PID 2>/dev/null || true
  exit 1
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Ready! Open http://localhost:$FRONTEND_PORT${NC}"
echo -e "${GREEN}  Click the ⚙ gear to configure your LLM provider${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Press ${YELLOW}Ctrl+C${NC} to stop both servers"
echo ""

# Wait for either process to exit
wait $BACKEND_PID $FRONTEND_PID
