from __future__ import annotations

import time

from fastapi.testclient import TestClient

GAME_KEYS = {"id", "fen", "pgn", "moves_san", "moves_uci", "color", "bot_elo", "status", "result", "termination", "last_bot_move"}
MOVE_KEYS = {
    "ply", "color", "san", "uci", "fen_before", "fen_after", "eval_before", "eval_after", "best_move_uci",
    "best_move_san", "best_line_san", "cp_loss", "classification", "explanation_it", "themes",
}
CLASSES = {"best", "excellent", "good", "inaccuracy", "mistake", "blunder", "book", "forced"}


def _wait_analysis(client: TestClient, game_id: int) -> dict:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        data = client.get(f"/api/games/{game_id}/analysis").json()
        if data["status"] in ("done", "error"):
            return data
        time.sleep(0.2)
    raise AssertionError("analisi non terminata")


def test_full_game_flow(client: TestClient) -> None:
    game = client.post("/api/games", json={"bot_elo": 1500, "color": "white"}).json()
    assert GAME_KEYS <= game.keys()
    assert game["status"] == "active" and game["moves_uci"] == []
    gid = game["id"]

    game = client.post(f"/api/games/{gid}/move", json={"uci": "e2e4"}).json()
    assert len(game["moves_uci"]) == 2 and game["last_bot_move"] == game["moves_uci"][1]
    assert game["moves_san"][0] == "e4"
    assert client.post(f"/api/games/{gid}/move", json={"uci": "e2e4"}).status_code == 400
    assert client.post(f"/api/games/{gid}/move", json={"uci": "zzzz"}).status_code == 400

    hint = client.post(f"/api/games/{gid}/hint").json()
    assert {"uci", "san", "explanation_it"} <= hint.keys()
    game = client.post(f"/api/games/{gid}/move", json={"uci": hint["uci"]}).json()
    assert len(game["moves_uci"]) == 4

    assert client.post(f"/api/games/{gid}/analyze").status_code == 400  # partita in corso
    game = client.post(f"/api/games/{gid}/resign").json()
    assert game["status"] == "finished" and game["result"] == "0-1" and game["termination"] == "Abbandono"
    assert '[Result "0-1"]' in game["pgn"]
    assert client.get(f"/api/games/{gid}").json()["status"] == "finished"

    prof = client.get("/api/profile").json()
    assert prof["games_played"] == 1 and prof["game_rating"] < 1200

    assert client.get(f"/api/games/{gid}/analysis").status_code == 404
    queued = client.post(f"/api/games/{gid}/analyze").json()
    assert queued["status"] in ("queued", "running", "done")
    data = _wait_analysis(client, gid)
    assert data["status"] == "done" and data["progress"] == 1
    assert len(data["moves"]) == 4
    assert data["accuracy_white"] is not None and data["accuracy_black"] is not None
    assert data["summary_it"].startswith("Precisione con il Bianco")
    assert {"blunder", "mistake", "inaccuracy"} <= data["counts"].keys()
    for move in data["moves"]:
        assert MOVE_KEYS <= move.keys()
        assert move["classification"] in CLASSES
        assert move["explanation_it"]

    listed = client.get("/api/games").json()
    assert listed[0]["id"] == gid and listed[0]["analyzed"] is True and listed[0]["accuracy"] is not None
    review = next(i for i in client.get("/api/plan/today").json()["items"] if i["kind"] == "review")
    assert review["done"] is True and review["params"]["game_id"] == gid


def test_black_game_bot_moves_first(client: TestClient) -> None:
    game = client.post("/api/games", json={"bot_elo": 900, "color": "black"}).json()
    assert len(game["moves_uci"]) == 1 and game["last_bot_move"] == game["moves_uci"][0]


def test_import_detects_checkmate_and_analyses(client: TestClient) -> None:
    pgn = '[Event "Test"]\n\n1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0'
    gid = client.post("/api/games/import", json={"pgn": pgn, "color": "black"}).json()["id"]
    game = client.get(f"/api/games/{gid}").json()
    assert game["status"] == "finished" and game["result"] == "1-0" and game["termination"] == "Scacco matto"
    assert game["bot_elo"] is None
    client.post(f"/api/games/{gid}/analyze")
    data = _wait_analysis(client, gid)
    blunder = data["moves"][5]
    assert blunder["san"] == "Nf6" and blunder["classification"] == "blunder"
    assert "matto" in blunder["explanation_it"]
    assert data["counts"]["blunder"] == 1
    assert data["moves"][6]["eval_after"] == 10000
    themes = {t["theme"] for t in client.get("/api/stats/weaknesses").json()["themes"]}
    assert "mateIn1" in themes
    assert client.post("/api/games/import", json={"pgn": "1. e4 e5 2. Ke3 Qxx9"}).status_code == 400


def test_profile_plan_engine_and_position(client: TestClient) -> None:
    prof = client.put("/api/profile", json={"target_elo": 2200, "initial_rating": 1500}).json()
    assert prof["target_elo"] == 2200 and prof["puzzle_rating"] == 1500 and prof["game_rating"] == 1500
    assert prof["level_name"] == "Intermedio" and prof["rating_history"]

    plan = client.get("/api/plan/today").json()
    assert [i["kind"] for i in plan["items"]] == ["warmup", "puzzles", "game", "review"]
    assert len(plan["focus_themes"]) == 2 and plan["tips"]
    assert next(i for i in plan["items"] if i["kind"] == "game")["params"]["bot_elo"] == 1600

    status = client.put("/api/engine/settings", json={"profile": "eco"}).json()
    assert status["profile"] == "eco" and status["threads"] == 1 and status["hash_mb"] == 64
    status = client.put("/api/engine/settings", json={"profile": "balanced", "threads": 3}).json()
    assert status["threads"] == 3 and status["hash_mb"] == 128
    client.put("/api/engine/settings", json={"profile": "balanced"})
    status = client.get("/api/engine/status").json()
    assert status["available"] and status["version"].startswith("Stockfish") and status["cpu_count"] >= 1

    fen = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
    pos = client.post("/api/analysis/position", json={"fen": fen, "multipv": 3}).json()
    assert pos["eval"] == 9999 and len(pos["lines"]) == 3
    assert pos["lines"][0]["moves_san"][0] == "Qxf7#"
    assert "matto" in pos["explanation_it"]
    assert client.post("/api/analysis/position", json={"fen": "not a fen"}).status_code == 400


def test_health(client: TestClient) -> None:
    data = client.get("/api/health").json()
    assert data["status"] == "ok"
    assert data["puzzles"] in ("lichess", "fallback")


def test_frontend_spa_fallback(client: TestClient, tmp_path, monkeypatch) -> None:
    from app import config

    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>ChessAI</html>", encoding="utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setattr(config, "STATIC_DIR", tmp_path)

    for path in ("/", "/tattica", "/analisi/3", "/gioca/12"):
        res = client.get(path)
        assert res.status_code == 200 and "ChessAI" in res.text, path
    res = client.get("/assets/app.js")
    assert res.status_code == 200 and "console.log" in res.text
    assert client.get("/assets/missing.js").status_code == 404
    # mai file fuori dalla cartella della build
    (tmp_path.parent / "secret.txt").write_text("SEGRETO", encoding="utf-8")
    assert "SEGRETO" not in client.get("/..%2Fsecret.txt").text
    # /api non è coperto dal fallback
    assert client.get("/api/does-not-exist").status_code == 404
    assert client.post("/api/does-not-exist").status_code == 404
    assert client.get("/api/health").json()["frontend"] is True
    assert client.get("/api/profile").status_code == 200


def test_frontend_absent(client: TestClient, tmp_path, monkeypatch) -> None:
    from app import config

    monkeypatch.setattr(config, "STATIC_DIR", tmp_path / "missing")
    assert client.get("/tattica").status_code == 404
    assert client.get("/api/health").json()["frontend"] is False
