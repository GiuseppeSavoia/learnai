"""Archivio dei puzzle: database SQLite importato da Lichess, oppure set JSON integrato di riserva."""

from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS puzzles (
    id TEXT PRIMARY KEY,
    fen TEXT NOT NULL,
    moves TEXT NOT NULL,
    rating INTEGER NOT NULL,
    rating_dev INTEGER NOT NULL,
    popularity INTEGER NOT NULL,
    nb_plays INTEGER NOT NULL,
    themes TEXT NOT NULL,
    opening_tags TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS puzzle_themes (
    theme TEXT NOT NULL,
    rating INTEGER NOT NULL,
    puzzle_id TEXT NOT NULL,
    PRIMARY KEY (theme, rating, puzzle_id)
) WITHOUT ROWID;
"""
INDEXES = "CREATE INDEX IF NOT EXISTS idx_puzzles_rating ON puzzles(rating);"

CANDIDATES_PER_QUERY = 25


@dataclass(frozen=True)
class Puzzle:
    id: str
    fen: str
    moves: list[str]
    rating: int
    rating_dev: int
    themes: list[str]


class SqlitePuzzleStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row(row: sqlite3.Row) -> Puzzle:
        return Puzzle(
            id=row["id"],
            fen=row["fen"],
            moves=row["moves"].split(),
            rating=row["rating"],
            rating_dev=row["rating_dev"],
            themes=row["themes"].split(),
        )

    def count(self) -> int:
        with self._conn() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM puzzles").fetchone()[0])

    def get(self, puzzle_id: str) -> Puzzle | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM puzzles WHERE id = ?", (puzzle_id,)).fetchone()
        return self._row(row) if row else None

    def candidates(self, lo: int, hi: int, theme: str | None) -> list[Puzzle]:
        with self._conn() as conn:
            if theme:
                rows = conn.execute(
                    "SELECT p.* FROM puzzle_themes t JOIN puzzles p ON p.id = t.puzzle_id "
                    "WHERE t.theme = ? AND t.rating BETWEEN ? AND ? ORDER BY RANDOM() LIMIT ?",
                    (theme, lo, hi, CANDIDATES_PER_QUERY),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM puzzles WHERE rating BETWEEN ? AND ? ORDER BY RANDOM() LIMIT ?",
                    (lo, hi, CANDIDATES_PER_QUERY),
                ).fetchall()
        return [self._row(r) for r in rows]

    def theme_counts(self) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute("SELECT theme, COUNT(*) AS n FROM puzzle_themes GROUP BY theme").fetchall()
        return {r["theme"]: int(r["n"]) for r in rows}


class MemoryPuzzleStore:
    """Set di riserva caricato dal JSON integrato (usato finché il database Lichess non è importato)."""

    def __init__(self, puzzles: list[Puzzle]) -> None:
        self.puzzles = {p.id: p for p in puzzles}

    @classmethod
    def from_json(cls, path: Path) -> MemoryPuzzleStore:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            [
                Puzzle(
                    id=d["id"],
                    fen=d["fen"],
                    moves=d["moves"].split(),
                    rating=d["rating"],
                    rating_dev=d["rating_dev"],
                    themes=d["themes"].split(),
                )
                for d in data
            ]
        )

    def count(self) -> int:
        return len(self.puzzles)

    def get(self, puzzle_id: str) -> Puzzle | None:
        return self.puzzles.get(puzzle_id)

    def candidates(self, lo: int, hi: int, theme: str | None) -> list[Puzzle]:
        found = [p for p in self.puzzles.values() if lo <= p.rating <= hi and (theme is None or theme in p.themes)]
        random.shuffle(found)
        return found[:CANDIDATES_PER_QUERY]

    def theme_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for p in self.puzzles.values():
            for t in p.themes:
                counts[t] = counts.get(t, 0) + 1
        return counts


PuzzleStore = SqlitePuzzleStore | MemoryPuzzleStore


def _sqlite_ready(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        return SqlitePuzzleStore(path).count() > 0
    except sqlite3.Error:
        return False


@lru_cache(maxsize=1)
def get_store() -> PuzzleStore:
    if _sqlite_ready(config.PUZZLE_DB_PATH):
        return SqlitePuzzleStore(config.PUZZLE_DB_PATH)
    return MemoryPuzzleStore.from_json(config.FALLBACK_PUZZLES_PATH)
