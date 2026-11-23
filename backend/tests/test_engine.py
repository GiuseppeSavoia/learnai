from __future__ import annotations

import random
import time

import chess
import chess.engine
import pytest

from app import config, engine

POSITIONS = [
    chess.STARTING_FEN,
    "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
    "8/5pk1/6p1/8/3R4/6P1/5PK1/1r6 b - - 0 40",
]
# 1.e4 d6 2.Dg4??: il Nero cattura gratis la Donna con l'Alfiere.
FREE_QUEEN = "rnbqkbnr/ppp1pppp/3p4/8/4P1Q1/8/PPPP1PPP/RNB1KBNR b KQkq - 1 2"


@pytest.mark.parametrize("elo", [400, 800, 1319, 1320, 2000, 3190])
@pytest.mark.parametrize("fen", POSITIONS)
def test_bot_move_is_legal(elo: int, fen: str) -> None:
    board = chess.Board(fen)
    move = engine.bot_move(board, elo, game_id=elo, rng=random.Random(elo))
    assert move in board.legal_moves


def test_weak_skill_parameters_scale_with_elo() -> None:
    skill_400, depth_400, random_400 = engine.weak_skill(400)
    skill_1300, depth_1300, random_1300 = engine.weak_skill(1300)
    assert (skill_400, depth_400) == (0, 1)
    assert skill_1300 == 5 and depth_1300 == 6
    assert random_400 > random_1300
    assert all(0 <= s <= 5 for s, _, _ in map(engine.weak_skill, range(400, 1320, 40)))


def test_bot_movetime_bounds() -> None:
    engine.manager.apply_settings("balanced", None, None)
    assert engine.bot_movetime(400) == pytest.approx(0.1)
    assert engine.bot_movetime(3190) == pytest.approx(0.8)
    assert engine.bot_movetime(1000) < engine.bot_movetime(2000)
    engine.manager.apply_settings("eco", None, None)
    assert engine.bot_movetime(3190) == pytest.approx(0.4)
    engine.manager.apply_settings("balanced", None, None)


def test_strong_bot_takes_free_queen() -> None:
    board = chess.Board(FREE_QUEEN)
    for seed in range(3):
        move = engine.bot_move(board, 2600, game_id=900 + seed, rng=random.Random(seed))
        assert move == chess.Move.from_uci("c8g4")


def test_weak_bot_is_randomised() -> None:
    board = chess.Board(POSITIONS[1])
    moves = {engine.bot_move(board, 400, game_id=1000 + seed, rng=random.Random(seed)) for seed in range(25)}
    assert len(moves) > 1


def test_mate_score_encoding() -> None:
    white_mates = chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE)
    black_mates = chess.engine.PovScore(chess.engine.Mate(2), chess.BLACK)
    assert engine.score_to_cp(white_mates) == 9997
    assert engine.score_to_cp(black_mates) == -9998


def test_engine_shuts_down_when_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    engine.manager.stop()
    monkeypatch.setattr(config, "ENGINE_IDLE_SECONDS", 1.0)
    engine.analyse(chess.Board(), depth=5, seconds=0.05)
    assert engine.manager.running
    deadline = time.monotonic() + 6
    while engine.manager.running and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not engine.manager.running
