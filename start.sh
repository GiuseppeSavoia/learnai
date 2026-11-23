#!/usr/bin/env bash
# Avvia LearnAI: backend (FastAPI + Stockfish, :8000) e frontend (Vite, :5173) insieme.
# Ctrl+C chiude entrambi. Imposta CHESSAI_NO_OPEN=1 per non aprire il browser automaticamente.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT=8000
FRONTEND_PORT=5173
URL="http://localhost:${FRONTEND_PORT}"

# --- controlli preliminari ------------------------------------------------------------
if [ ! -x "$ROOT/backend/.venv/bin/uvicorn" ]; then
  echo "Manca l'ambiente Python del backend. Esegui prima (vedi README.md):"
  echo "  cd backend && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  # nvm non è caricato nelle shell non interattive: proviamo a caricarlo
  if [ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]; then
    # shellcheck disable=SC1091
    . "${NVM_DIR:-$HOME/.nvm}/nvm.sh" >/dev/null
  fi
fi
if ! command -v node >/dev/null 2>&1; then
  echo "Node.js non trovato. Installa Node.js 20+ (es. 'brew install node')."
  exit 1
fi

if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "Installo le dipendenze del frontend (solo la prima volta)..."
  (cd "$ROOT/frontend" && npm install)
fi

if ! command -v stockfish >/dev/null 2>&1 && [ ! -x /opt/homebrew/bin/stockfish ] && [ ! -x /usr/local/bin/stockfish ]; then
  echo "Attenzione: Stockfish non trovato. Installa con 'brew install stockfish' (gioco e analisi non funzioneranno)."
fi

for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "La porta $port è già occupata (LearnAI è già avviato?). Chiudi il processo e riprova:"
    lsof -nP -iTCP:"$port" -sTCP:LISTEN
    exit 1
  fi
done

# --- avvio -------------------------------------------------------------------------------
PIDS=()
cleanup() {
  trap - INT TERM EXIT
  echo
  echo "Chiudo LearnAI..."
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  echo "Fatto."
}
trap cleanup INT TERM EXIT

echo "Avvio il backend su http://localhost:${BACKEND_PORT} ..."
"$ROOT/backend/run.sh" &
PIDS+=($!)

echo "Avvio il frontend su ${URL} ..."
# vite lanciato direttamente (senza il wrapper npm) così il segnale di chiusura gli arriva sicuramente
(cd "$ROOT/frontend" && exec node node_modules/vite/bin/vite.js --port "$FRONTEND_PORT" --strictPort) &
PIDS+=($!)

# attende che entrambi rispondano (max ~30 s), poi apre il browser
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/api/engine/status" >/dev/null 2>&1 &&
     curl -fsS "$URL" >/dev/null 2>&1; then
    echo
    echo "LearnAI è pronto: ${URL}  (Ctrl+C per chiudere)"
    if [ -z "${CHESSAI_NO_OPEN:-}" ]; then
      if command -v open >/dev/null 2>&1; then open "$URL"; elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"; fi
    fi
    break
  fi
  sleep 0.5
done

# se uno dei due processi termina, chiude anche l'altro
while true; do
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "Un processo è terminato: chiudo anche l'altro."
      exit 1
    fi
  done
  sleep 1
done
