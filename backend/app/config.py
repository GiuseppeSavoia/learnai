"""Percorsi e impostazioni globali del backend (sovrascrivibili via variabili d'ambiente).

Variabili d'ambiente riconosciute:

- ``CHESSAI_DATA_DIR``     cartella dei dati utente (``chessai.db``). Default: ``backend/data``
                           in sviluppo, ``~/Library/Application Support/ChessAI`` nel server congelato.
- ``CHESSAI_PUZZLES_DB``   database dei puzzle (aperto in sola lettura, può stare dentro il bundle
                           dell'app). Accettato anche il vecchio nome ``CHESSAI_PUZZLE_DB``.
                           Default: ``<CHESSAI_DATA_DIR>/puzzles.db``.
- ``CHESSAI_STATIC_DIR``   build del frontend da servire su ``/``. Default: ``frontend/dist`` se esiste.
- ``CHESSAI_HOST`` / ``CHESSAI_PORT``  indirizzo del server (default ``127.0.0.1:8000``).
- ``STOCKFISH_PATH``       eseguibile di Stockfish (altrimenti PATH e percorsi Homebrew).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

#: True quando il backend gira come eseguibile PyInstaller (app per Mac).
FROZEN = bool(getattr(sys, "frozen", False))

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


def _default_data_dir() -> Path:
    if FROZEN:
        return Path.home() / "Library" / "Application Support" / "ChessAI"
    return BACKEND_DIR / "data"


def _env_path(*names: str) -> Path | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return Path(value).expanduser()
    return None


DATA_DIR = _env_path("CHESSAI_DATA_DIR") or _default_data_dir()
USER_DB_PATH = DATA_DIR / "chessai.db"
PUZZLE_DB_PATH = _env_path("CHESSAI_PUZZLES_DB", "CHESSAI_PUZZLE_DB") or DATA_DIR / "puzzles.db"
FALLBACK_PUZZLES_PATH = Path(__file__).resolve().parent / "resources" / "fallback_puzzles.json"


def _default_static_dir() -> Path | None:
    env = _env_path("CHESSAI_STATIC_DIR")
    if env is not None:
        return env
    candidate = PROJECT_DIR / "frontend" / "dist"
    return None if FROZEN else candidate


#: Build del frontend servita da FastAPI su "/" (ignorata se manca index.html).
STATIC_DIR: Path | None = _default_static_dir()

HOST = os.environ.get("CHESSAI_HOST", "127.0.0.1")
PORT = int(os.environ.get("CHESSAI_PORT", "8000"))

ENGINE_IDLE_SECONDS = float(os.environ.get("CHESSAI_ENGINE_IDLE_SECONDS", "300"))

CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

CLAUDE_MODEL = "claude-opus-5-5"


def stockfish_path() -> str | None:
    """Percorso di Stockfish: env STOCKFISH_PATH, poi PATH, poi Homebrew."""
    env = os.environ.get("STOCKFISH_PATH")
    if env:
        return env if Path(env).is_file() else None
    found = shutil.which("stockfish")
    if found:
        return found
    for candidate in ("/opt/homebrew/bin/stockfish", "/usr/local/bin/stockfish", "/usr/games/stockfish"):
        if Path(candidate).is_file():
            return candidate
    return None


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
