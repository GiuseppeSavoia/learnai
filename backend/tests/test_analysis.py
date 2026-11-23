from __future__ import annotations

import chess
import pytest

from app import analysis


@pytest.mark.parametrize(
    ("loss", "expected"),
    [
        (0.0, "excellent"),
        (1.9, "excellent"),
        (5.0, "good"),
        (9.99, "good"),
        (10.0, "inaccuracy"),
        (19.99, "inaccuracy"),
        (20.0, "mistake"),
        (29.99, "mistake"),
        (30.0, "blunder"),
        (80.0, "blunder"),
    ],
)
def test_classification_thresholds(loss: float, expected: str) -> None:
    assert analysis.classify(loss, is_best=False, forced=False) == expected


def test_best_and_forced_override_loss() -> None:
    assert analysis.classify(50.0, is_best=True, forced=False) == "best"
    assert analysis.classify(50.0, is_best=False, forced=True) == "forced"


def test_win_percent() -> None:
    assert analysis.win_percent(0) == pytest.approx(50.0)
    assert analysis.win_percent(300) == pytest.approx(100 - analysis.win_percent(-300))
    assert analysis.win_percent(300, chess.BLACK) == pytest.approx(analysis.win_percent(-300))
    assert analysis.win_percent(10000) == analysis.win_percent(1000)


def test_move_accuracy() -> None:
    assert analysis.move_accuracy(50, 60) == 100.0
    assert analysis.move_accuracy(60, 40) < analysis.move_accuracy(60, 55)
    assert analysis.move_accuracy(100, 0) == 0.0


def test_game_accuracy_perfect_and_blundering() -> None:
    steady = [20] * 41
    white, black = analysis.game_accuracy(steady, chess.WHITE)
    assert white == pytest.approx(100.0) and black == pytest.approx(100.0)
    # Il Bianco regala tutto alla mossa 10 (ply 19).
    evals = [20] * 19 + [-900] * 22
    white, black = analysis.game_accuracy(evals, chess.WHITE)
    assert white is not None and black is not None
    assert white < black
