"""Analisi delle partite in background: valutazioni, classificazione per perdita di win% e precisione stile Lichess."""

from __future__ import annotations

import json
import logging
import math
import queue
import statistics
import threading
from dataclasses import asdict, dataclass

import chess

from . import db, engine, explain, games, profile
from .themes import META_THEMES

log = logging.getLogger(__name__)

ANALYSIS_DEPTH = 16
ANALYSIS_SECONDS = 0.15
POSITION_DEPTH = 18
POSITION_SECONDS = 0.5
BEST_LINE_PLIES = 8
CLAUDE_MAX_MOVES = 5

# Soglie di perdita di win% (punto di vista di chi muove).
INACCURACY = 10.0
MISTAKE = 20.0
BLUNDER = 30.0
EXCELLENT = 2.0

CLASSIFICATIONS = ("best", "excellent", "good", "inaccuracy", "mistake", "blunder", "forced")
ERROR_CLASSES = ("inaccuracy", "mistake", "blunder")
SERIOUS_CLASSES = ("mistake", "blunder")


@dataclass
class MoveRecord:
    ply: int
    color: str
    numbered: str
    san: str
    uci: str
    fen_before: str
    fen_after: str
    eval_before: int
    eval_after: int
    best_move_uci: str | None
    best_move_san: str | None
    best_line_san: list[str]
    cp_loss: int
    classification: str
    explanation_it: str
    themes: list[str]
    win_loss: float
    explanation_source: str = "heuristic"

    def to_json(self) -> dict[str, object]:
        data = asdict(self)
        del data["numbered"]
        return data


# --- formule ------------------------------------------------------------------
def win_percent(cp_white: int, color: chess.Color = chess.WHITE) -> float:
    """Probabilità di vittoria (0–100) per `color`, formula di Lichess con cp limitati a ±1000."""
    cp = max(-1000, min(1000, cp_white if color == chess.WHITE else -cp_white))
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def move_accuracy(win_before: float, win_after: float) -> float:
    """Precisione di una mossa (Lichess) dalla win% di chi muove prima e dopo."""
    if win_after >= win_before:
        return 100.0
    raw = 103.1668100711649 * math.exp(-0.04354415386753951 * (win_before - win_after)) - 3.166924740191411
    return max(0.0, min(100.0, raw + 1))


def classify(win_loss: float, is_best: bool, forced: bool) -> str:
    if forced:
        return "forced"
    if is_best:
        return "best"
    if win_loss >= BLUNDER:
        return "blunder"
    if win_loss >= MISTAKE:
        return "mistake"
    if win_loss >= INACCURACY:
        return "inaccuracy"
    if win_loss < EXCELLENT:
        return "excellent"
    return "good"


def game_accuracy(evals: list[int], start_color: chess.Color) -> tuple[float | None, float | None]:
    """Precisione per colore come su Lichess: media tra media pesata per volatilità e media armonica."""
    wins = [win_percent(cp) for cp in evals]
    n_moves = len(wins) - 1
    if n_moves < 1:
        return None, None
    window = max(2, min(8, n_moves // 10))
    head = [wins[:window]] * max(0, min(window, len(wins)) - 2)
    windows = head + [wins[i : i + window] for i in range(max(1, len(wins) - window + 1))]
    weights = [max(0.5, min(12.0, statistics.pstdev(w))) if len(w) > 1 else 0.5 for w in windows]

    per_color: dict[chess.Color, list[tuple[float, float]]] = {chess.WHITE: [], chess.BLACK: []}
    for i, weight in zip(range(n_moves), weights, strict=False):
        color = start_color if i % 2 == 0 else not start_color
        prev, nxt = wins[i], wins[i + 1]
        before, after = (prev, nxt) if color == chess.WHITE else (100 - prev, 100 - nxt)
        per_color[color].append((move_accuracy(before, after), weight))

    def combine(items: list[tuple[float, float]]) -> float | None:
        if not items:
            return None
        weighted = sum(a * w for a, w in items) / sum(w for _, w in items)
        harmonic = len(items) / sum(1 / max(1.0, a) for a, _ in items)
        return (weighted + harmonic) / 2

    return combine(per_color[chess.WHITE]), combine(per_color[chess.BLACK])


# --- valutazione di posizioni -----------------------------------------------------
def terminal_eval(board: chess.Board) -> int | None:
    if board.is_checkmate():
        return -engine.MATE_SCORE if board.turn == chess.WHITE else engine.MATE_SCORE
    if board.is_stalemate() or board.is_insufficient_material():
        return 0
    return None


def evaluate(board: chess.Board) -> tuple[int, list[chess.Move]]:
    terminal = terminal_eval(board)
    if terminal is not None:
        return terminal, []
    info = engine.analyse(board, depth=ANALYSIS_DEPTH, seconds=ANALYSIS_SECONDS)[0]
    return engine.score_to_cp(info["score"]), list(info.get("pv", []))


def analyse_position(fen: str, multipv: int) -> dict[str, object]:
    try:
        board = chess.Board(fen)
    except ValueError as exc:
        raise games.GameError("FEN non valida.") from exc
    if not board.is_valid():
        raise games.GameError("Posizione non valida.")
    terminal = terminal_eval(board)
    if terminal is not None or board.is_game_over():
        value = terminal or 0
        return {"eval": value, "lines": [], "explanation_it": explain.explain_position(board, value, [])}
    infos = engine.analyse(board, depth=POSITION_DEPTH, seconds=POSITION_SECONDS, multipv=multipv)
    lines = [(engine.score_to_cp(info["score"]), list(info.get("pv", []))) for info in infos]
    best_eval, best_pv = lines[0]
    return {
        "eval": best_eval,
        "lines": [
            {"eval": cp, "moves_san": explain.line_san(board, pv), "moves_uci": [m.uci() for m in pv]} for cp, pv in lines
        ],
        "explanation_it": explain.explain_position(board, best_eval, best_pv),
    }


# --- analisi di una partita -------------------------------------------------------
def _set_status(game_id: int, status: str, progress: float) -> None:
    with db.connect() as conn:
        conn.execute("UPDATE games SET analysis_status = ?, analysis_progress = ? WHERE id = ?", (status, progress, game_id))


def run_analysis(game_id: int) -> None:
    game = games.load(game_id)
    _set_status(game_id, "running", 0.0)
    board = chess.Board(game.start_fen)
    start_color = board.turn
    boards = [board.copy(stack=False)]
    for uci in game.moves_uci:
        board.push_uci(uci)
        boards.append(board.copy(stack=False))

    evals: list[int] = []
    pvs: list[list[chess.Move]] = []
    total = len(boards)
    for i, b in enumerate(boards):
        cp, pv = evaluate(b)
        evals.append(cp)
        pvs.append(pv)
        if i % 4 == 0 or i == total - 1:
            _set_status(game_id, "running", round(0.95 * (i + 1) / total, 3))

    moves: list[MoveRecord] = []
    for ply, uci in enumerate(game.moves_uci):
        before = boards[ply]
        move = chess.Move.from_uci(uci)
        mover = before.turn
        win_before = win_percent(evals[ply], mover)
        win_after = win_percent(evals[ply + 1], mover)
        best_pv = pvs[ply]
        best = best_pv[0] if best_pv else None
        classification = classify(win_before - win_after, best == move, before.legal_moves.count() == 1)
        pov = 1 if mover == chess.WHITE else -1
        cp_loss = max(0, pov * (max(-1000, min(1000, evals[ply])) - max(-1000, min(1000, evals[ply + 1]))))
        ctx = explain.MoveContext(before, move, best_pv, pvs[ply + 1], evals[ply], evals[ply + 1], classification)
        text, themes = explain.explain_move(ctx, win_before, win_after)
        moves.append(
            MoveRecord(
                ply=ply + 1,
                color="white" if mover == chess.WHITE else "black",
                numbered=explain.numbered_san(before, move),
                san=before.san(move),
                uci=uci,
                fen_before=before.fen(),
                fen_after=boards[ply + 1].fen(),
                eval_before=evals[ply],
                eval_after=evals[ply + 1],
                best_move_uci=best.uci() if best else None,
                best_move_san=before.san(best) if best else None,
                best_line_san=explain.line_san(before, best_pv[:BEST_LINE_PLIES]),
                cp_loss=cp_loss,
                classification=classification,
                explanation_it=text,
                themes=themes,
                win_loss=round(win_before - win_after, 1),
            )
        )

    user = "white" if game.user_color == chess.WHITE else "black"
    user_moves = [m for m in moves if m.color == user]
    _enrich(user_moves)
    acc_white, acc_black = game_accuracy(evals, start_color)
    counts = {c: sum(1 for m in user_moves if m.classification == c) for c in CLASSIFICATIONS}
    counts_by_color = {
        color: {c: sum(1 for m in moves if m.color == color and m.classification == c) for c in CLASSIFICATIONS}
        for color in ("white", "black")
    }
    worst = max((m for m in user_moves if m.classification in ERROR_CLASSES), key=lambda m: m.win_loss, default=None)
    error_themes = [t for m in user_moves if m.classification in SERIOUS_CLASSES for t in m.themes]
    ranked_themes = sorted({t for t in error_themes if t not in META_THEMES}, key=error_themes.count, reverse=True)
    summary = explain.summarize_game(
        game.user_color,
        acc_white if user == "white" else acc_black,
        counts,
        (worst.numbered, worst.classification) if worst else None,
        ranked_themes,
    )

    profile.record_game_errors(error_themes)
    payload = {
        "summary_it": summary,
        "counts": counts,
        "counts_by_color": counts_by_color,
        "moves": [m.to_json() for m in moves],
    }
    with db.connect() as conn:
        conn.execute(
            "UPDATE games SET analysis_status = 'done', analysis_progress = 1, analysis = ?, accuracy_white = ?, "
            "accuracy_black = ?, analyzed_at = ? WHERE id = ?",
            (json.dumps(payload), acc_white, acc_black, db.now_iso(), game_id),
        )


def _enrich(user_moves: list[MoveRecord]) -> None:
    """Se ANTHROPIC_API_KEY è impostata, riscrive con Claude le spiegazioni dei peggiori errori dell'utente."""
    if not explain.claude_enabled():
        return
    errors = [m for m in user_moves if m.classification in SERIOUS_CLASSES]
    for m in sorted(errors, key=lambda m: m.win_loss, reverse=True)[:CLAUDE_MAX_MOVES]:
        text = explain.enrich_with_claude(
            explain.ClaudeRequest(
                fen_before=m.fen_before,
                played_san=m.san,
                best_line_san=m.best_line_san,
                eval_before=m.eval_before,
                eval_after=m.eval_after,
                classification=m.classification,
                heuristic=m.explanation_it,
            )
        )
        if text:
            m.explanation_it = text
            m.explanation_source = "claude"


# --- coda in background -----------------------------------------------------------
class AnalysisWorker:
    def __init__(self) -> None:
        self._queue: queue.Queue[int] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()

    def _ensure_thread(self) -> None:
        with self._start_lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="analysis", daemon=True)
                self._thread.start()

    def _run(self) -> None:
        while True:
            game_id = self._queue.get()
            try:
                run_analysis(game_id)
            except Exception:
                log.exception("Analisi della partita %s non riuscita", game_id)
                _set_status(game_id, "error", 0.0)
            finally:
                self._queue.task_done()

    def submit(self, game_id: int) -> dict[str, object]:
        game = games.load(game_id)
        if game.status != "finished":
            raise games.GameError("La partita è ancora in corso: analizzala quando è terminata.")
        if game.analysis_status in ("queued", "running", "done"):
            return {"status": game.analysis_status, "progress": game.analysis_progress}
        _set_status(game_id, "queued", 0.0)
        self._ensure_thread()
        self._queue.put(game_id)
        return {"status": "queued", "progress": 0.0}

    def resume_pending(self) -> None:
        """Rimette in coda le analisi interrotte da un riavvio del server."""
        with db.connect() as conn:
            rows = conn.execute("SELECT id FROM games WHERE analysis_status IN ('queued', 'running') ORDER BY id").fetchall()
        for row in rows:
            _set_status(row["id"], "queued", 0.0)
            self._ensure_thread()
            self._queue.put(row["id"])

    def wait_idle(self) -> None:
        self._queue.join()


worker = AnalysisWorker()


def analysis_response(game_id: int) -> dict[str, object] | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT analysis_status, analysis_progress, analysis, accuracy_white, accuracy_black FROM games WHERE id = ?",
            (game_id,),
        ).fetchone()
    if row is None:
        raise games.GameNotFoundError(f"Partita {game_id} non trovata.")
    if row["analysis_status"] is None:
        return None
    data = json.loads(row["analysis"]) if row["analysis"] else {}
    summary = data.get("summary_it")
    if row["analysis_status"] == "error":
        summary = "L'analisi non è riuscita: riprova."
    return {
        "status": row["analysis_status"],
        "progress": row["analysis_progress"],
        "accuracy_white": round(row["accuracy_white"], 1) if row["accuracy_white"] is not None else None,
        "accuracy_black": round(row["accuracy_black"], 1) if row["accuracy_black"] is not None else None,
        "summary_it": summary,
        "counts": data.get("counts", {}),
        "counts_by_color": data.get("counts_by_color", {}),
        "moves": data.get("moves", []),
    }
