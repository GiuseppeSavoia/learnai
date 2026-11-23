"""Gestione dell'unica istanza Stockfish condivisa.

- avvio pigro alla prima richiesta, chiusura automatica dopo `ENGINE_IDLE_SECONDS` di inattività;
- un lock serializza tutti gli accessi (una ricerca alla volta);
- profili CPU: eco (1 thread, 64 MB, tempi dimezzati), balanced (2 thread, 128 MB), performance (6 thread, 256 MB);
- mossa del bot con limitazione Elo: UCI_LimitStrength/UCI_Elo da 1320 in su, sotto 1320 Skill Level 0–5
  con profondità ridotta e scelta casuale tra le mosse candidate (MultiPV).
"""

from __future__ import annotations

import math
import os
import random
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

import chess
import chess.engine

from . import config, db

ProfileName = Literal["eco", "balanced", "performance"]

MATE_SCORE = 10000
ENGINE_ELO_FLOOR = 1320
BOT_ELO_MIN = 400
BOT_ELO_MAX = 3190


@dataclass(frozen=True)
class EngineProfile:
    threads: int
    hash_mb: int
    time_factor: float


PROFILES: dict[ProfileName, EngineProfile] = {
    "eco": EngineProfile(threads=1, hash_mb=64, time_factor=0.5),
    "balanced": EngineProfile(threads=2, hash_mb=128, time_factor=1.0),
    "performance": EngineProfile(threads=6, hash_mb=256, time_factor=1.0),
}


class EngineUnavailableError(RuntimeError):
    pass


def score_to_cp(score: chess.engine.PovScore) -> int:
    """Valutazione in centipedoni dal punto di vista del Bianco; i matti valgono ±(10000 − distanza)."""
    value = score.white().score(mate_score=MATE_SCORE)
    assert value is not None
    return value


class EngineManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._engine: chess.engine.SimpleEngine | None = None
        self._last_used = time.monotonic()
        self._version: str | None = None
        self._watchdog: threading.Thread | None = None
        self._wake = threading.Event()
        self.path = config.stockfish_path()
        self.profile: ProfileName = "balanced"
        self.threads = PROFILES["balanced"].threads
        self.hash_mb = PROFILES["balanced"].hash_mb

    # --- configurazione -------------------------------------------------
    def load_settings(self) -> None:
        stored = db.get_setting("engine_profile")
        for name in PROFILES:
            if name == stored:
                self.profile = name
        self.threads = int(db.get_setting("engine_threads") or PROFILES[self.profile].threads)
        self.hash_mb = int(db.get_setting("engine_hash_mb") or PROFILES[self.profile].hash_mb)

    @property
    def time_factor(self) -> float:
        return PROFILES[self.profile].time_factor

    def apply_settings(self, profile: ProfileName | None, threads: int | None, hash_mb: int | None) -> None:
        with self._lock:
            if profile is not None:
                self.profile = profile
                self.threads = PROFILES[profile].threads
                self.hash_mb = PROFILES[profile].hash_mb
            if threads is not None:
                self.threads = max(1, min(threads, os.cpu_count() or 1))
            if hash_mb is not None:
                self.hash_mb = max(16, min(hash_mb, 2048))
            db.set_setting("engine_profile", self.profile)
            db.set_setting("engine_threads", str(self.threads))
            db.set_setting("engine_hash_mb", str(self.hash_mb))
            if self._engine is not None:
                self._engine.configure({"Threads": self.threads, "Hash": self.hash_mb})

    # --- ciclo di vita ---------------------------------------------------
    @property
    def available(self) -> bool:
        return self.path is not None

    @property
    def running(self) -> bool:
        return self._engine is not None

    def pid(self) -> int | None:
        with self._lock:
            if self._engine is None:
                return None
            transport = self._engine.protocol.transport
            return transport.get_pid() if transport is not None else None

    def _start(self) -> chess.engine.SimpleEngine:
        if self.path is None:
            raise EngineUnavailableError("Stockfish non trovato: installalo con `brew install stockfish` o imposta STOCKFISH_PATH.")
        engine = chess.engine.SimpleEngine.popen_uci(self.path)
        engine.configure({"Threads": self.threads, "Hash": self.hash_mb})
        self._version = engine.id.get("name")
        self._engine = engine
        if self._watchdog is None or not self._watchdog.is_alive():
            self._watchdog = threading.Thread(target=self._watch_idle, name="engine-idle", daemon=True)
            self._watchdog.start()
        return engine

    def stop(self) -> None:
        with self._lock:
            if self._engine is not None:
                try:
                    self._engine.quit()
                except (chess.engine.EngineError, chess.engine.EngineTerminatedError, TimeoutError):
                    self._engine.close()
                self._engine = None
            self._wake.set()

    def _watch_idle(self) -> None:
        while True:
            self._wake.wait(max(0.5, min(30.0, config.ENGINE_IDLE_SECONDS / 4)))
            self._wake.clear()
            with self._lock:
                if self._engine is None:
                    return
                if time.monotonic() - self._last_used >= config.ENGINE_IDLE_SECONDS:
                    self.stop()
                    return

    @contextmanager
    def session(self) -> Iterator[chess.engine.SimpleEngine]:
        """Accesso esclusivo al motore (lo avvia se necessario)."""
        with self._lock:
            engine = self._engine or self._start()
            try:
                yield engine
            except chess.engine.EngineTerminatedError:
                self._engine = None
                raise
            finally:
                self._last_used = time.monotonic()

    def version(self) -> str | None:
        if self._version is None and self.path is not None:
            try:
                out = subprocess.run([self.path], input="uci\nquit\n", capture_output=True, text=True, timeout=5).stdout
            except (OSError, subprocess.SubprocessError):
                return None
            for line in out.splitlines():
                if line.startswith("id name "):
                    self._version = line.removeprefix("id name ").strip()
        return self._version

    def status(self) -> dict[str, object]:
        return {
            "available": self.available,
            "path": self.path,
            "version": self.version(),
            "running": self.running,
            "threads": self.threads,
            "hash_mb": self.hash_mb,
            "profile": self.profile,
            "cpu_count": os.cpu_count(),
        }


manager = EngineManager()


# --- operazioni di alto livello -------------------------------------------
def analyse(board: chess.Board, *, depth: int, seconds: float, multipv: int = 1) -> list[chess.engine.InfoDict]:
    """Analisi con limite di profondità e tempo (il tempo è scalato dal profilo)."""
    limit = chess.engine.Limit(depth=depth, time=seconds * manager.time_factor)
    with manager.session() as engine:
        return engine.analyse(board, limit, multipv=multipv)


def bot_movetime(elo: int) -> float:
    """Tempo per mossa del bot (secondi): 100 ms a 400 Elo, 800 ms a 3190 Elo, scalato dal profilo."""
    frac = (min(max(elo, BOT_ELO_MIN), BOT_ELO_MAX) - BOT_ELO_MIN) / (BOT_ELO_MAX - BOT_ELO_MIN)
    return (0.1 + 0.7 * frac) * manager.time_factor


def weak_skill(elo: int) -> tuple[int, int, float]:
    """Parametri sotto 1320 Elo: (Skill Level 0–5, profondità, probabilità di scegliere a caso tra le candidate)."""
    gap = (ENGINE_ELO_FLOOR - max(elo, BOT_ELO_MIN)) / (ENGINE_ELO_FLOOR - BOT_ELO_MIN)  # 0..1
    skill = round(5 * (1 - gap))
    depth = 1 + skill
    random_pick_probability = 0.15 + 0.35 * gap
    return skill, depth, random_pick_probability


def _pick_candidate(infos: list[chess.engine.InfoDict], elo: int, rng: random.Random) -> chess.Move:
    """Scelta pesata tra le linee MultiPV: più basso l'Elo, più probabili le mosse peggiori."""
    temperature = 60 + 0.4 * (ENGINE_ELO_FLOOR - elo)
    scored = [(info["pv"][0], info["score"].relative.score(mate_score=MATE_SCORE) or 0) for info in infos if info.get("pv")]
    best = max(s for _, s in scored)
    weights = [math.exp(-(best - s) / temperature) for _, s in scored]
    return rng.choices([m for m, _ in scored], weights=weights, k=1)[0]


def bot_move(board: chess.Board, elo: int, game_id: int, rng: random.Random | None = None) -> chess.Move:
    rng = rng or random.Random()
    elo = min(max(elo, BOT_ELO_MIN), BOT_ELO_MAX)
    movetime = bot_movetime(elo)
    with manager.session() as engine:
        if elo >= ENGINE_ELO_FLOOR:
            result = engine.play(
                board,
                chess.engine.Limit(time=movetime),
                game=game_id,
                options={"UCI_LimitStrength": True, "UCI_Elo": elo},
            )
        else:
            skill, depth, random_pick = weak_skill(elo)
            limit = chess.engine.Limit(depth=depth, time=movetime)
            if rng.random() < random_pick:
                candidates = min(5, board.legal_moves.count())
                infos = engine.analyse(board, limit, multipv=candidates, game=game_id)
                return _pick_candidate(infos, elo, rng)
            result = engine.play(board, limit, game=game_id, options={"Skill Level": skill})
    if result.move is None:
        raise EngineUnavailableError("Il motore non ha restituito una mossa.")
    return result.move
