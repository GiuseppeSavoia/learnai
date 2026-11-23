"""Selezione dei puzzle (riscaldamento / mirati / normali) e registrazione dei tentativi."""

from __future__ import annotations

import random
from typing import Literal

from . import curriculum, db, explain, profile
from .puzzle_store import Puzzle, get_store
from .themes import label_it, labels_it

Mode = Literal["warmup", "focus", "normal"]

WINDOWS = (50, 100, 200, 400, 800, 3000)


class PuzzleNotFoundError(LookupError):
    pass


def _attempted_ids() -> set[str]:
    with db.connect() as conn:
        return {r["puzzle_id"] for r in conn.execute("SELECT DISTINCT puzzle_id FROM puzzle_attempts")}


def _find(target: int, theme: str | None, first_window: int) -> Puzzle | None:
    store = get_store()
    seen = _attempted_ids()
    fallback: Puzzle | None = None
    for window in (w for w in WINDOWS if w >= first_window):
        candidates = store.candidates(target - window, target + window, theme)
        fresh = [p for p in candidates if p.id not in seen]
        if fresh:
            return min(fresh, key=lambda p: abs(p.rating - target))
        if candidates and fallback is None:
            fallback = candidates[0]
    return fallback


def next_puzzle(theme: str | None, mode: Mode, rng: random.Random | None = None) -> dict[str, object]:
    rng = rng or random.Random()
    p = profile.load()
    if mode == "warmup":
        target, window = round(p.puzzle.rating + curriculum.WARMUP_OFFSET), 50
    elif mode == "focus":
        target, window = round(p.puzzle.rating), 50
        if theme is None:
            theme = rng.choice(curriculum.stored_plan().focus_themes)
    else:
        target, window = round(p.puzzle.rating), 100
        if theme is None:
            theme = curriculum.weighted_theme(rng)

    puzzle = _find(target, theme, window) or _find(target, None, window)
    if puzzle is None:
        raise PuzzleNotFoundError("Nessun puzzle disponibile.")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO puzzle_served(puzzle_id, mode, served_at) VALUES (?, ?, ?) "
            "ON CONFLICT(puzzle_id) DO UPDATE SET mode = excluded.mode, served_at = excluded.served_at",
            (puzzle.id, mode, db.now_iso()),
        )
    return {
        "id": puzzle.id,
        "fen": puzzle.fen,
        "moves": puzzle.moves,
        "rating": puzzle.rating,
        "themes": puzzle.themes,
        "themes_it": labels_it(puzzle.themes),
    }


def attempt_score(success: bool, hints_used: int) -> float:
    """1 = risolto da solo, 0.5 = risolto con aiuti, 0 = sbagliato."""
    if not success:
        return 0.0
    return 1.0 if hints_used == 0 else 0.5


def record_attempt(puzzle_id: str, success: bool, time_ms: int, hints_used: int) -> dict[str, object]:
    puzzle = get_store().get(puzzle_id)
    if puzzle is None:
        raise PuzzleNotFoundError(f"Puzzle {puzzle_id} non trovato.")
    with db.connect() as conn:
        served = conn.execute("SELECT mode FROM puzzle_served WHERE puzzle_id = ?", (puzzle_id,)).fetchone()
        rated = conn.execute("SELECT 1 FROM puzzle_attempts WHERE puzzle_id = ?", (puzzle_id,)).fetchone() is None
    mode = served["mode"] if served else "normal"

    new_rating, delta = profile.apply_puzzle_result(
        puzzle.rating, puzzle.rating_dev, attempt_score(success, hints_used), rated, success
    )
    if rated:
        profile.record_puzzle_themes(puzzle.themes, success)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO puzzle_attempts(puzzle_id, ts, day, mode, success, time_ms, hints_used, rated, delta, themes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (puzzle_id, db.now_iso(), db.today(), mode, int(success), time_ms, hints_used, int(rated), delta, " ".join(puzzle.themes)),
        )
    return {
        "puzzle_rating": round(new_rating),
        "delta": round(delta, 1),
        "explanation_it": explain.explain_puzzle(puzzle.fen, puzzle.moves, puzzle.themes, success),
    }


def themes_response() -> list[dict[str, object]]:
    counts = get_store().theme_counts()
    return [
        {"theme": theme, "label_it": label_it(theme), "count": n}
        for theme, n in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    ]
