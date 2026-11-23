from __future__ import annotations

import chess

from app import analysis, explain


def _explain(fen: str, uci: str, classification: str = "blunder") -> tuple[str, list[str]]:
    board = chess.Board(fen)
    move = chess.Move.from_uci(uci)
    eval_before, best_pv = analysis.evaluate(board)
    after = board.copy()
    after.push(move)
    eval_after, reply_pv = analysis.evaluate(after)
    ctx = explain.MoveContext(board, move, best_pv, reply_pv, eval_before, eval_after, classification)
    return explain.explain_move(
        ctx, analysis.win_percent(eval_before, board.turn), analysis.win_percent(eval_after, board.turn)
    )


def test_hanging_queen_blunder_is_explained_in_italian() -> None:
    # 1.e4 e5 2.Cf3 Dg5?? : la Donna va in presa del Cavallo.
    fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"
    text, themes = _explain(fen, "d8g5")
    assert text.startswith("Errore grave: 2...Dg5??")
    assert "la Donna in presa" in text
    assert "Era meglio" in text
    assert "hangingPiece" in themes


def test_allowed_mate_is_explained() -> None:
    # Matto del barbiere: 3...Cf6?? permette 4.Dxf7#.
    fen = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3"
    text, themes = _explain(fen, "g8f6")
    assert "matto in 1" in text
    assert "4.Dxf7#" in text
    assert "mateIn1" in themes


def test_missed_mate_is_explained() -> None:
    # Il Bianco ha 1.Dxf7# ma gioca 1.d3.
    fen = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
    text, _ = _explain(fen, "d2d3", classification="mistake")
    assert "lascia sfuggire il matto" in text
    assert "Dxf7#" in text


def test_italian_notation_and_puzzle_explanation() -> None:
    assert explain.san_it("Nbd7") == "Cbd7"
    assert explain.san_it("exd8=Q+") == "exd8=D+"
    assert explain.san_it("O-O") == "O-O"
    text = explain.explain_puzzle(
        "r1b2bkr/ppp3pp/2n5/3p4/4P2q/6N1/PPP2PPP/R1BQK1NR b KQ - 0 10",
        ["d5e4", "d1d5", "c8e6", "d5e6"],
        ["mateIn2", "short"],
        success=True,
    )
    assert text.startswith("Risolto! Soluzione: 11.Dd5+ Ae6 12.Dxe6#")
    assert "matto in 2" in text


def test_hint_describes_fork() -> None:
    # Cxc7+ fa forchetta a Re e Torre.
    board = chess.Board("r3k3/ppp5/8/1N6/8/8/8/4K3 w - - 0 1")
    text = explain.explain_hint(board, chess.Move.from_uci("b5c7"))
    assert "forchetta" in text
