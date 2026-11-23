"""Partite contro il bot e partite importate: persistenza, mosse, fine partita, PGN, suggerimenti."""

from __future__ import annotations

import io
import json
import random
import sqlite3
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

import chess
import chess.pgn

from . import db, engine, explain, profile

ColorChoice = Literal["white", "black", "random"]

TERMINATIONS_IT = {
    chess.Termination.CHECKMATE: "Scacco matto",
    chess.Termination.STALEMATE: "Stallo",
    chess.Termination.INSUFFICIENT_MATERIAL: "Materiale insufficiente",
    chess.Termination.SEVENTYFIVE_MOVES: "Regola delle 75 mosse",
    chess.Termination.FIVEFOLD_REPETITION: "Ripetizione quintupla",
    chess.Termination.FIFTY_MOVES: "Regola delle 50 mosse",
    chess.Termination.THREEFOLD_REPETITION: "Triplice ripetizione",
}
RESIGN_IT = "Abbandono"
IMPORTED_IT = "Partita importata"
RESULTS = {"1-0", "0-1", "1/2-1/2"}

HINT_DEPTH = 16
HINT_SECONDS = 0.3

_locks: defaultdict[int, threading.Lock] = defaultdict(threading.Lock)


class GameError(ValueError):
    """Richiesta non valida su una partita (→ HTTP 400)."""


class GameNotFoundError(LookupError):
    pass


@dataclass
class Game:
    id: int
    created_at: str
    finished_at: str | None
    source: str
    bot_elo: int | None
    color: str
    start_fen: str
    moves_uci: list[str]
    status: str
    result: str | None
    termination: str | None
    last_bot_move: str | None
    headers: dict[str, str]
    analysis_status: str | None
    analysis_progress: float
    accuracy_white: float | None
    accuracy_black: float | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Game:
        return cls(
            id=row["id"],
            created_at=row["created_at"],
            finished_at=row["finished_at"],
            source=row["source"],
            bot_elo=row["bot_elo"],
            color=row["color"],
            start_fen=row["start_fen"],
            moves_uci=row["moves_uci"].split(),
            status=row["status"],
            result=row["result"],
            termination=row["termination"],
            last_bot_move=row["last_bot_move"],
            headers=json.loads(row["headers"]),
            analysis_status=row["analysis_status"],
            analysis_progress=row["analysis_progress"],
            accuracy_white=row["accuracy_white"],
            accuracy_black=row["accuracy_black"],
        )

    @property
    def user_color(self) -> chess.Color:
        return chess.WHITE if self.color == "white" else chess.BLACK

    @property
    def user_accuracy(self) -> float | None:
        return self.accuracy_white if self.user_color == chess.WHITE else self.accuracy_black

    def board(self) -> chess.Board:
        board = chess.Board(self.start_fen)
        for uci in self.moves_uci:
            board.push_uci(uci)
        return board


def load(game_id: int) -> Game:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if row is None:
        raise GameNotFoundError(f"Partita {game_id} non trovata.")
    return Game.from_row(row)


def _save(game: Game) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE games SET moves_uci = ?, status = ?, result = ?, termination = ?, last_bot_move = ?, finished_at = ? "
            "WHERE id = ?",
            (" ".join(game.moves_uci), game.status, game.result, game.termination, game.last_bot_move, game.finished_at, game.id),
        )


def pgn(game: Game) -> str:
    board = game.board()
    pgn_game = chess.pgn.Game.from_board(board)
    for key, value in game.headers.items():
        pgn_game.headers[key] = value
    if game.source == "bot":
        bot = f"Stockfish ({game.bot_elo})"
        pgn_game.headers["Event"] = "ChessAI: partita contro il bot"
        pgn_game.headers["Date"] = game.created_at[:10].replace("-", ".")
        pgn_game.headers["White"] = "Tu" if game.color == "white" else bot
        pgn_game.headers["Black"] = bot if game.color == "white" else "Tu"
    pgn_game.headers["Result"] = game.result or "*"
    if game.termination:
        pgn_game.headers["Termination"] = game.termination
    return str(pgn_game)


def state(game: Game) -> dict[str, object]:
    board = chess.Board(game.start_fen)
    sans: list[str] = []
    for uci in game.moves_uci:
        move = chess.Move.from_uci(uci)
        sans.append(board.san(move))
        board.push(move)
    return {
        "id": game.id,
        "fen": board.fen(),
        "pgn": pgn(game),
        "moves_san": sans,
        "moves_uci": game.moves_uci,
        "color": game.color,
        "bot_elo": game.bot_elo,
        "status": game.status,
        "result": game.result,
        "termination": game.termination,
        "last_bot_move": game.last_bot_move,
    }


def _finish(game: Game, result: str, termination: str) -> None:
    game.status = "finished"
    game.result = result
    game.termination = termination
    game.finished_at = db.now_iso()
    if game.source == "bot" and game.bot_elo is not None:
        if result == "1/2-1/2":
            score = 0.5
        else:
            score = 1.0 if (result == "1-0") == (game.user_color == chess.WHITE) else 0.0
        profile.apply_game_result(game.bot_elo, score)


def _check_end(game: Game, board: chess.Board) -> bool:
    outcome = board.outcome(claim_draw=True)
    if outcome is None:
        return False
    _finish(game, outcome.result(), TERMINATIONS_IT[outcome.termination])
    return True


def _bot_reply(game: Game, board: chess.Board) -> None:
    assert game.bot_elo is not None
    move = engine.bot_move(board, game.bot_elo, game.id)
    board.push(move)
    game.moves_uci.append(move.uci())
    game.last_bot_move = move.uci()
    _check_end(game, board)


def create(bot_elo: int | None, color: ColorChoice) -> dict[str, object]:
    if bot_elo is None:
        bot_elo = round(profile.load().game.rating + 100)
    bot_elo = min(max(bot_elo, engine.BOT_ELO_MIN), engine.BOT_ELO_MAX)
    chosen = random.choice(["white", "black"]) if color == "random" else color
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO games(created_at, source, bot_elo, color, start_fen, status) VALUES (?, 'bot', ?, ?, ?, 'active')",
            (db.now_iso(), bot_elo, chosen, chess.STARTING_FEN),
        )
        game_id = int(cur.lastrowid or 0)
    game = load(game_id)
    if chosen == "black":
        with _locks[game_id]:
            _bot_reply(game, game.board())
            _save(game)
    return state(game)


def _parse_user_move(board: chess.Board, uci: str) -> chess.Move:
    try:
        move = chess.Move.from_uci(uci)
    except ValueError as exc:
        raise GameError(f"Mossa non valida: {uci}") from exc
    piece = board.piece_at(move.from_square)
    if (
        move.promotion is None
        and piece is not None
        and piece.piece_type == chess.PAWN
        and chess.square_rank(move.to_square) in (0, 7)
    ):
        move = chess.Move(move.from_square, move.to_square, promotion=chess.QUEEN)
    if move not in board.legal_moves:
        raise GameError(f"Mossa illegale: {uci}")
    return move


def play_move(game_id: int, uci: str) -> dict[str, object]:
    with _locks[game_id]:
        game = load(game_id)
        if game.status != "active":
            raise GameError("La partita è già terminata.")
        board = game.board()
        if board.turn != game.user_color:
            raise GameError("Non è il tuo turno.")
        move = _parse_user_move(board, uci)
        board.push(move)
        game.moves_uci.append(move.uci())
        game.last_bot_move = None
        if not _check_end(game, board):
            _bot_reply(game, board)
        _save(game)
        return state(game)


def resign(game_id: int) -> dict[str, object]:
    with _locks[game_id]:
        game = load(game_id)
        if game.status != "active":
            raise GameError("La partita è già terminata.")
        _finish(game, "0-1" if game.user_color == chess.WHITE else "1-0", RESIGN_IT)
        _save(game)
        return state(game)


def hint(game_id: int) -> dict[str, object]:
    game = load(game_id)
    board = game.board()
    if game.status != "active" or board.is_game_over():
        raise GameError("La partita è terminata: nessun suggerimento disponibile.")
    info = engine.analyse(board, depth=HINT_DEPTH, seconds=HINT_SECONDS)[0]
    move = info["pv"][0]
    return {"uci": move.uci(), "san": board.san(move), "explanation_it": explain.explain_hint(board, move)}


def list_games() -> list[dict[str, object]]:
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM games ORDER BY id DESC").fetchall()
    out = []
    for row in rows:
        game = Game.from_row(row)
        accuracy = game.user_accuracy
        out.append(
            {
                "id": game.id,
                "created_at": game.created_at,
                "bot_elo": game.bot_elo,
                "color": game.color,
                "result": game.result,
                "status": game.status,
                "analyzed": game.analysis_status == "done",
                "accuracy": round(accuracy, 1) if accuracy is not None else None,
            }
        )
    return out


def import_pgn(text: str, color: Literal["white", "black"]) -> int:
    parsed = chess.pgn.read_game(io.StringIO(text))
    if parsed is None or parsed.errors:
        raise GameError("PGN non valido.")
    board = parsed.board()
    start_fen = board.fen()
    moves = []
    for move in parsed.mainline_moves():
        moves.append(move.uci())
        board.push(move)
    if not moves:
        raise GameError("Il PGN non contiene mosse.")
    headers = {k: v for k, v in parsed.headers.items() if k not in ("Result", "FEN", "SetUp")}
    result = parsed.headers.get("Result")
    outcome = board.outcome(claim_draw=True)
    if result not in RESULTS:
        result = outcome.result() if outcome else None
    termination = TERMINATIONS_IT[outcome.termination] if outcome else parsed.headers.get("Termination", IMPORTED_IT)
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO games(created_at, finished_at, source, color, start_fen, moves_uci, status, result, termination, headers) "
            "VALUES (?, ?, 'import', ?, ?, ?, 'finished', ?, ?, ?)",
            (db.now_iso(), db.now_iso(), color, start_fen, " ".join(moves), result, termination, json.dumps(headers)),
        )
        return int(cur.lastrowid or 0)
