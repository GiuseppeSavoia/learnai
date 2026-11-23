from __future__ import annotations

import json

import chess
from fastapi.testclient import TestClient

from app import config, rating


def test_fallback_puzzles_are_valid() -> None:
    data = json.loads(config.FALLBACK_PUZZLES_PATH.read_text(encoding="utf-8"))
    assert 30 <= len(data) <= 50
    for puzzle in data:
        board = chess.Board(puzzle["fen"])
        for uci in puzzle["moves"].split():
            move = chess.Move.from_uci(uci)
            assert move in board.legal_moves, puzzle["id"]
            board.push(move)


def test_glicko2_direction() -> None:
    player = rating.Rating(1500, 200)
    opponent = rating.Rating(1500, 100)
    win = rating.update(player, opponent, 1.0)
    loss = rating.update(player, opponent, 0.0)
    assert win.rating > 1500 > loss.rating
    assert win.rd < 200 and loss.rd < 200
    assert rating.update(player, opponent, 0.5).rating == player.rating


def test_puzzle_attempt_updates_rating(client: TestClient) -> None:
    start = client.get("/api/profile").json()["puzzle_rating"]
    puzzle = client.get("/api/puzzles/next", params={"mode": "warmup"}).json()
    assert {"id", "fen", "moves", "rating", "themes", "themes_it"} <= puzzle.keys()

    solved = client.post(f"/api/puzzles/{puzzle['id']}/attempt", json={"success": True, "time_ms": 4000, "hints_used": 0}).json()
    assert solved["delta"] > 0
    assert solved["puzzle_rating"] > start
    assert "Soluzione" in solved["explanation_it"]

    repeat = client.post(f"/api/puzzles/{puzzle['id']}/attempt", json={"success": False, "time_ms": 4000, "hints_used": 0}).json()
    assert repeat["delta"] == 0

    other = client.get("/api/puzzles/next", params={"mode": "normal"}).json()
    assert other["id"] != puzzle["id"]
    failed = client.post(f"/api/puzzles/{other['id']}/attempt", json={"success": False, "time_ms": 9000, "hints_used": 0}).json()
    assert failed["delta"] < 0

    prof = client.get("/api/profile").json()
    assert prof["puzzles_solved"] == 1 and prof["puzzles_failed"] == 2
    plan = client.get("/api/plan/today").json()
    warmup = next(i for i in plan["items"] if i["kind"] == "warmup")
    assert warmup["params"]["completed"] == 2

    weak = client.get("/api/stats/weaknesses").json()["themes"]
    assert any(t["errors"] >= 1 for t in weak)


def test_puzzle_themes_and_focus(client: TestClient) -> None:
    themes = client.get("/api/puzzles/themes").json()
    assert themes and {"theme", "label_it", "count"} <= themes[0].keys()
    puzzle = client.get("/api/puzzles/next", params={"mode": "focus", "theme": "fork"}).json()
    assert "fork" in puzzle["themes"]
    assert client.post("/api/puzzles/nope/attempt", json={"success": True, "time_ms": 1, "hints_used": 0}).status_code == 404
