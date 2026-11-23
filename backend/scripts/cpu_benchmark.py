"""Misura CPU% (processo Stockfish, via psutil) e tempo reale per:
(a) una mossa del bot per ogni profilo, (b) analisi completa di una partita di 40 mosse, (c) motore inattivo.

Uso:  .venv/bin/python scripts/cpu_benchmark.py   → scrive CPU_REPORT.md
CPU% è riferito a un singolo core (200% = due core pieni), come in `top`.
"""

from __future__ import annotations

import os
import platform
import random
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

os.environ["CHESSAI_DATA_DIR"] = tempfile.mkdtemp(prefix="chessai-bench-")
os.environ["CHESSAI_ENGINE_IDLE_SECONDS"] = "5"
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import chess  # noqa: E402
import chess.pgn  # noqa: E402
import psutil  # noqa: E402

from app import analysis, config, db, engine, games, profile  # noqa: E402

MIDDLEGAME = "r1bq1rk1/pp2bppp/2n1pn2/3p4/2PP4/2N1PN2/PP2BPPP/R2QKB1R w KQ - 0 9"
BOT_ELOS = (800, 1500, 2500)
PROFILE_NAMES: tuple[engine.ProfileName, ...] = ("eco", "balanced", "performance")
IDLE_SECONDS = 10.0


@dataclass
class Sample:
    wall_s: float
    cpu_pct: float


def measure(fn: Callable[[], object]) -> Sample:
    pid = engine.manager.pid()
    assert pid is not None, "il motore deve essere avviato prima della misura"
    proc = psutil.Process(pid)
    before = proc.cpu_times()
    start = time.perf_counter()
    fn()
    wall = time.perf_counter() - start
    after = proc.cpu_times()
    cpu = (after.user - before.user) + (after.system - before.system)
    return Sample(wall, 100 * cpu / wall)


def warm_up() -> None:
    engine.analyse(chess.Board(), depth=1, seconds=0.01)


def self_play_game(plies: int) -> str:
    """Partita di prova (bot 1800 contro bot 1600) da analizzare; rigenerata se finisce prima."""
    rng = random.Random(42)
    while True:
        board = chess.Board()
        while not board.is_game_over() and len(board.move_stack) < plies:
            elo = 1800 if board.turn == chess.WHITE else 1600
            board.push(engine.bot_move(board, elo, game_id=0, rng=rng))
        if len(board.move_stack) == plies:
            return str(chess.pgn.Game.from_board(board))


def main() -> None:
    db.init_db()
    profile.ensure_profile()
    rows_moves: list[str] = []
    rows_analysis: list[str] = []

    engine.manager.apply_settings("balanced", None, None)
    warm_up()
    pgn = self_play_game(80)
    game_id = games.import_pgn(pgn, "white")

    for name in PROFILE_NAMES:
        engine.manager.apply_settings(name, None, None)
        warm_up()
        board = chess.Board(MIDDLEGAME)
        for elo in BOT_ELOS:
            samples = [
                measure(lambda b=board, e=elo: engine.bot_move(b, e, game_id=e, rng=random.Random(1))) for _ in range(3)
            ]
            wall = sum(s.wall_s for s in samples) / len(samples)
            cpu = sum(s.cpu_pct for s in samples) / len(samples)
            rows_moves.append(f"| {name} | {engine.manager.threads} | {elo} | {wall * 1000:.0f} ms | {cpu:.0f}% |")
            print(rows_moves[-1], flush=True)

        with db.connect() as conn:
            conn.execute("UPDATE games SET analysis_status = NULL, analysis = NULL WHERE id = ?", (game_id,))
        sample = measure(lambda: analysis.run_analysis(game_id))
        rows_analysis.append(
            f"| {name} | {engine.manager.threads} | 81 | {sample.wall_s:.1f} s | {sample.cpu_pct:.0f}% | "
            f"{sample.wall_s / 81 * 1000:.0f} ms |"
        )
        print(rows_analysis[-1], flush=True)

    engine.manager.apply_settings("balanced", None, None)
    warm_up()
    pid = engine.manager.pid()
    proc = psutil.Process(pid)
    before = proc.cpu_times()
    time.sleep(IDLE_SECONDS / 2)
    after = proc.cpu_times()
    idle_cpu = 100 * ((after.user - before.user) + (after.system - before.system)) / (IDLE_SECONDS / 2)
    deadline = time.monotonic() + config.ENGINE_IDLE_SECONDS + IDLE_SECONDS
    while engine.manager.running and time.monotonic() < deadline:
        time.sleep(0.25)
    stopped = not engine.manager.running and not psutil.pid_exists(pid or 0)
    backend_cpu = psutil.Process().cpu_percent(interval=2.0)

    report = f"""# Rapporto CPU del motore

Generato da `scripts/cpu_benchmark.py` il {time.strftime('%Y-%m-%d %H:%M')}.

- Macchina: {platform.machine()} · macOS {platform.mac_ver()[0]} · {os.cpu_count()} core logici · Python {platform.python_version()}
- Motore: {engine.manager.version()} (`{engine.manager.path}`)
- CPU% = tempo CPU (user+system) del processo Stockfish / tempo reale × 100, riferito a un core
  (100% = un core pieno; il massimo teorico è threads × 100%).

## (a) Una mossa del bot (media di 3 mosse, posizione di mediogioco)

| Profilo | Thread | Elo bot | Tempo | CPU Stockfish |
|---|---|---|---|---|
{chr(10).join(rows_moves)}

Il tempo per mossa va da 100 ms (400 Elo) a 800 ms (3190 Elo); il profilo eco lo dimezza.
Sotto 1320 Elo la ricerca è limitata anche in profondità (Skill Level 0–5), quindi termina prima.

## (b) Analisi completa di una partita di 40 mosse (80 semimosse → 81 posizioni)

Limite per posizione: profondità 16 oppure 150 ms (75 ms in eco), il primo dei due.

| Profilo | Thread | Posizioni | Tempo totale | CPU Stockfish | Tempo per posizione |
|---|---|---|---|---|---|
{chr(10).join(rows_analysis)}

## (c) Inattività

| Stato | CPU Stockfish |
|---|---|
| Motore avviato ma fermo ({IDLE_SECONDS / 2:.0f} s di misura) | {idle_cpu:.1f}% |
| Dopo il timeout di inattività ({config.ENGINE_IDLE_SECONDS:.0f} s nel benchmark, 300 s di default) | {"processo terminato → 0%" if stopped else "ANCORA IN ESECUZIONE"} |
| Processo backend Python a riposo (2 s) | {backend_cpu:.1f}% |
"""
    (BACKEND / "CPU_REPORT.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
