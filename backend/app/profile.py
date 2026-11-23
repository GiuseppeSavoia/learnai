"""Stato dell'allievo nel database: rating Glicko-2, storico, contatori e statistiche per tema."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass

from . import db, rating
from .themes import META_THEMES

DEFAULT_RATING = 1200
DEFAULT_TARGET = 2000
BOT_RD = 60.0


@dataclass(frozen=True)
class ProfileState:
    puzzle: rating.Rating
    game: rating.Rating
    initial_rating: int
    target_elo: int
    puzzles_solved: int
    puzzles_failed: int
    games_played: int

    @property
    def strength(self) -> float:
        """Stima di forza complessiva: media pesata (partite 60%, puzzle 40%)."""
        return 0.6 * self.game.rating + 0.4 * self.puzzle.rating


def ensure_profile() -> None:
    with db.connect() as conn:
        exists = conn.execute("SELECT 1 FROM profile WHERE id = 1").fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO profile(id, puzzle_rating, puzzle_rd, puzzle_vol, game_rating, game_rd, game_vol, "
                "initial_rating, target_elo) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    DEFAULT_RATING,
                    rating.MAX_RD,
                    rating.DEFAULT_VOLATILITY,
                    DEFAULT_RATING,
                    rating.MAX_RD,
                    rating.DEFAULT_VOLATILITY,
                    DEFAULT_RATING,
                    DEFAULT_TARGET,
                ),
            )
            _record_history(conn)


def load() -> ProfileState:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    return ProfileState(
        puzzle=rating.Rating(row["puzzle_rating"], row["puzzle_rd"], row["puzzle_vol"]),
        game=rating.Rating(row["game_rating"], row["game_rd"], row["game_vol"]),
        initial_rating=row["initial_rating"],
        target_elo=row["target_elo"],
        puzzles_solved=row["puzzles_solved"],
        puzzles_failed=row["puzzles_failed"],
        games_played=row["games_played"],
    )


def _record_history(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT puzzle_rating, game_rating FROM profile WHERE id = 1").fetchone()
    conn.execute(
        "INSERT INTO rating_history(ts, day, puzzle_rating, game_rating) VALUES (?, ?, ?, ?)",
        (db.now_iso(), db.today(), row["puzzle_rating"], row["game_rating"]),
    )


def update_settings(target_elo: int | None, initial_rating: int | None) -> None:
    """`initial_rating` reimposta entrambi i rating alla stima dichiarata (RD 350)."""
    with db.connect() as conn:
        if target_elo is not None:
            conn.execute("UPDATE profile SET target_elo = ? WHERE id = 1", (target_elo,))
        if initial_rating is not None:
            conn.execute(
                "UPDATE profile SET initial_rating = ?, puzzle_rating = ?, puzzle_rd = ?, puzzle_vol = ?, "
                "game_rating = ?, game_rd = ?, game_vol = ? WHERE id = 1",
                (
                    initial_rating,
                    initial_rating,
                    rating.MAX_RD,
                    rating.DEFAULT_VOLATILITY,
                    initial_rating,
                    rating.MAX_RD,
                    rating.DEFAULT_VOLATILITY,
                ),
            )
            _record_history(conn)


def apply_puzzle_result(puzzle_rating: int, puzzle_rd: int, score: float, rated: bool, success: bool) -> tuple[float, float]:
    """Aggiorna rating e contatori dopo un puzzle. Restituisce (nuovo rating, variazione)."""
    current = load().puzzle
    new = rating.update(current, rating.Rating(puzzle_rating, puzzle_rd), score) if rated else current
    with db.connect() as conn:
        conn.execute(
            "UPDATE profile SET puzzle_rating = ?, puzzle_rd = ?, puzzle_vol = ?, "
            "puzzles_solved = puzzles_solved + ?, puzzles_failed = puzzles_failed + ? WHERE id = 1",
            (new.rating, new.rd, new.volatility, int(success), int(not success)),
        )
        if rated:
            _record_history(conn)
    return new.rating, new.rating - current.rating


def apply_game_result(bot_elo: int, score: float) -> float:
    """Aggiorna il rating partite (Glicko-2 contro l'Elo del bot). Restituisce la variazione."""
    current = load().game
    new = rating.update(current, rating.Rating(bot_elo, BOT_RD), score)
    with db.connect() as conn:
        conn.execute(
            "UPDATE profile SET game_rating = ?, game_rd = ?, game_vol = ?, games_played = games_played + 1 WHERE id = 1",
            (new.rating, new.rd, new.volatility),
        )
        _record_history(conn)
    return new.rating - current.rating


def history() -> list[dict[str, object]]:
    """Un punto per giorno (ultimo valore della giornata)."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT day, puzzle_rating, game_rating FROM rating_history "
            "WHERE id IN (SELECT MAX(id) FROM rating_history GROUP BY day) ORDER BY day"
        ).fetchall()
    return [{"date": r["day"], "puzzle_rating": round(r["puzzle_rating"]), "game_rating": round(r["game_rating"])} for r in rows]


def _tactical(themes: Iterable[str]) -> list[str]:
    return sorted({t for t in themes if t not in META_THEMES})


def record_puzzle_themes(themes: Iterable[str], success: bool) -> None:
    with db.connect() as conn:
        for theme in _tactical(themes):
            conn.execute(
                "INSERT INTO theme_stats(theme, puzzle_attempts, puzzle_errors) VALUES (?, 1, ?) "
                "ON CONFLICT(theme) DO UPDATE SET puzzle_attempts = puzzle_attempts + 1, "
                "puzzle_errors = puzzle_errors + excluded.puzzle_errors",
                (theme, int(not success)),
            )


def record_game_errors(themes: Iterable[str]) -> None:
    """Ogni tema compare una volta per ogni errore (mistake/blunder) commesso in partita."""
    with db.connect() as conn:
        for theme in themes:
            if theme in META_THEMES:
                continue
            conn.execute(
                "INSERT INTO theme_stats(theme, game_errors) VALUES (?, 1) "
                "ON CONFLICT(theme) DO UPDATE SET game_errors = game_errors + 1",
                (theme,),
            )


@dataclass(frozen=True)
class ThemeStat:
    theme: str
    errors: int
    attempts: int

    @property
    def success_rate(self) -> float:
        return 1.0 - self.errors / self.attempts if self.attempts else 1.0


def theme_stats() -> list[ThemeStat]:
    """Errori = puzzle sbagliati + errori in partita; tentativi = puzzle tentati + errori in partita."""
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM theme_stats").fetchall()
    return [
        ThemeStat(
            theme=r["theme"],
            errors=r["puzzle_errors"] + r["game_errors"],
            attempts=r["puzzle_attempts"] + r["game_errors"],
        )
        for r in rows
    ]
