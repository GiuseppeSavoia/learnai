"""Accesso a SQLite per i dati utente (backend/data/chessai.db)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    puzzle_rating REAL NOT NULL,
    puzzle_rd REAL NOT NULL,
    puzzle_vol REAL NOT NULL,
    game_rating REAL NOT NULL,
    game_rd REAL NOT NULL,
    game_vol REAL NOT NULL,
    initial_rating INTEGER NOT NULL,
    target_elo INTEGER NOT NULL,
    puzzles_solved INTEGER NOT NULL DEFAULT 0,
    puzzles_failed INTEGER NOT NULL DEFAULT 0,
    games_played INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS rating_history (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    day TEXT NOT NULL,
    puzzle_rating REAL NOT NULL,
    game_rating REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS puzzle_served (
    puzzle_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    served_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS puzzle_attempts (
    id INTEGER PRIMARY KEY,
    puzzle_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    day TEXT NOT NULL,
    mode TEXT NOT NULL,
    success INTEGER NOT NULL,
    time_ms INTEGER NOT NULL,
    hints_used INTEGER NOT NULL,
    rated INTEGER NOT NULL,
    delta REAL NOT NULL,
    themes TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempts_day ON puzzle_attempts(day);
CREATE INDEX IF NOT EXISTS idx_attempts_puzzle ON puzzle_attempts(puzzle_id);
CREATE TABLE IF NOT EXISTS theme_stats (
    theme TEXT PRIMARY KEY,
    puzzle_attempts INTEGER NOT NULL DEFAULT 0,
    puzzle_errors INTEGER NOT NULL DEFAULT 0,
    game_errors INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    source TEXT NOT NULL,
    bot_elo INTEGER,
    color TEXT NOT NULL,
    start_fen TEXT NOT NULL,
    moves_uci TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    result TEXT,
    termination TEXT,
    last_bot_move TEXT,
    headers TEXT NOT NULL DEFAULT '{}',
    analysis_status TEXT,
    analysis_progress REAL NOT NULL DEFAULT 0,
    analysis TEXT,
    accuracy_white REAL,
    accuracy_black REAL,
    analyzed_at TEXT
);
CREATE TABLE IF NOT EXISTS daily_plans (
    day TEXT PRIMARY KEY,
    plan TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS study_questions (
    id INTEGER PRIMARY KEY,
    exam TEXT NOT NULL,
    topic TEXT NOT NULL,
    difficulty INTEGER NOT NULL,
    rating REAL NOT NULL,
    vignette TEXT NOT NULL DEFAULT '',
    stem TEXT NOT NULL,
    choices TEXT NOT NULL,
    answer INTEGER NOT NULL,
    explanation TEXT NOT NULL,
    created_at TEXT NOT NULL,
    flagged INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_study_q_exam_topic ON study_questions(exam, topic);
CREATE TABLE IF NOT EXISTS study_attempts (
    id INTEGER PRIMARY KEY,
    question_id INTEGER NOT NULL,
    exam TEXT NOT NULL,
    topic TEXT NOT NULL,
    ts TEXT NOT NULL,
    day TEXT NOT NULL,
    choice INTEGER NOT NULL,
    correct INTEGER NOT NULL,
    time_ms INTEGER NOT NULL,
    rated INTEGER NOT NULL,
    delta REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_study_att_q ON study_attempts(question_id);
CREATE TABLE IF NOT EXISTS study_ratings (
    exam TEXT PRIMARY KEY,
    rating REAL NOT NULL,
    rd REAL NOT NULL,
    vol REAL NOT NULL,
    answered INTEGER NOT NULL DEFAULT 0,
    correct INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS study_lessons_done (
    exam TEXT NOT NULL,
    topic TEXT NOT NULL,
    done_at TEXT NOT NULL,
    PRIMARY KEY (exam, topic)
);
CREATE TABLE IF NOT EXISTS study_topic_stats (
    exam TEXT NOT NULL,
    topic TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (exam, topic)
);
"""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today() -> str:
    return date.today().isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.USER_DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Connessione con commit automatico all'uscita (rollback in caso di eccezione)."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    config.ensure_data_dir()
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Colonne aggiunte dopo la prima versione delle tabelle (CREATE TABLE IF NOT EXISTS non le aggiunge)."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(study_questions)")}
    if "seed_id" not in cols:
        conn.execute("ALTER TABLE study_questions ADD COLUMN seed_id TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_study_q_seed ON study_questions(seed_id)")


def get_setting(key: str) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
