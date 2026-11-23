"""API FastAPI di LearnAI (tutte le rotte sotto /api)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from . import analysis, config, curriculum, db, engine, games, llm, profile, puzzle_store, puzzles, study, study_content


class ProfileUpdate(BaseModel):
    target_elo: int | None = Field(default=None, ge=800, le=3200)
    initial_rating: int | None = Field(default=None, ge=100, le=3000)


class AttemptBody(BaseModel):
    success: bool
    time_ms: int = Field(default=0, ge=0)
    hints_used: int = Field(default=0, ge=0)


class NewGameBody(BaseModel):
    bot_elo: int | None = Field(default=None, ge=engine.BOT_ELO_MIN, le=engine.BOT_ELO_MAX)
    color: games.ColorChoice = "random"


class MoveBody(BaseModel):
    uci: str = Field(min_length=4, max_length=5)


class ImportBody(BaseModel):
    pgn: str = Field(min_length=1)
    color: Literal["white", "black"] = "white"


class PositionBody(BaseModel):
    fen: str
    multipv: int = Field(default=1, ge=1, le=3)


class StudyAnswerBody(BaseModel):
    choice: int = Field(ge=0, le=4)
    time_ms: int = Field(default=0, ge=0)


class LessonDoneBody(BaseModel):
    done: bool = True


class ClaudeSettingsBody(BaseModel):
    #: stringa vuota = rimuovi la chiave salvata
    api_key: str = Field(max_length=500)


class EngineSettingsBody(BaseModel):
    profile: engine.ProfileName | None = None
    threads: int | None = Field(default=None, ge=1, le=64)
    hash_mb: int | None = Field(default=None, ge=16, le=2048)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    db.init_db()
    profile.ensure_profile()
    engine.manager.load_settings()
    analysis.worker.resume_pending()
    if study_content.seeding_enabled():
        study_content.seed_all()
    yield
    engine.manager.stop()


app = FastAPI(title="LearnAI", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(games.GameNotFoundError)
@app.exception_handler(puzzles.PuzzleNotFoundError)
@app.exception_handler(study.StudyNotFoundError)
async def not_found(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(games.GameError)
@app.exception_handler(study.StudyError)
async def bad_request(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(engine.EngineUnavailableError)
@app.exception_handler(study.StudyUnavailableError)
async def engine_unavailable(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


api = APIRouter(prefix="/api")


# --- stato del server --------------------------------------------------------------------
@api.get("/health")
def health() -> dict[str, object]:
    """Risposta leggera usata dall'app per Mac per sapere quando il server è pronto."""
    store = puzzle_store.get_store()
    return {
        "status": "ok",
        "version": app.version,
        "puzzles": "lichess" if isinstance(store, puzzle_store.SqlitePuzzleStore) else "fallback",
        "engine_available": engine.manager.available,
        "frontend": _frontend_index() is not None,
    }


# --- profilo e piano -------------------------------------------------------------
@api.get("/profile")
def get_profile() -> dict[str, object]:
    return curriculum.profile_response()


@api.put("/profile")
def put_profile(body: ProfileUpdate) -> dict[str, object]:
    profile.update_settings(body.target_elo, body.initial_rating)
    return curriculum.profile_response()


@api.get("/plan/today")
def plan_today() -> dict[str, object]:
    return curriculum.today_plan()


@api.get("/stats/weaknesses")
def weaknesses() -> dict[str, object]:
    return curriculum.weaknesses_response()


# --- puzzle --------------------------------------------------------------------------
@api.get("/puzzles/next")
def next_puzzle(theme: str | None = None, mode: puzzles.Mode = "normal") -> dict[str, object]:
    return puzzles.next_puzzle(theme, mode)


@api.post("/puzzles/{puzzle_id}/attempt")
def puzzle_attempt(puzzle_id: str, body: AttemptBody) -> dict[str, object]:
    return puzzles.record_attempt(puzzle_id, body.success, body.time_ms, body.hints_used)


@api.get("/puzzles/themes")
def puzzle_themes() -> list[dict[str, object]]:
    return puzzles.themes_response()


# --- partite -----------------------------------------------------------------------------
@api.post("/games")
def create_game(body: NewGameBody) -> dict[str, object]:
    return games.create(body.bot_elo, body.color)


@api.get("/games")
def list_games() -> list[dict[str, object]]:
    return games.list_games()


@api.post("/games/import")
def import_game(body: ImportBody) -> dict[str, int]:
    return {"id": games.import_pgn(body.pgn, body.color)}


@api.get("/games/{game_id}")
def get_game(game_id: int) -> dict[str, object]:
    return games.state(games.load(game_id))


@api.post("/games/{game_id}/move")
def game_move(game_id: int, body: MoveBody) -> dict[str, object]:
    return games.play_move(game_id, body.uci)


@api.post("/games/{game_id}/resign")
def game_resign(game_id: int) -> dict[str, object]:
    return games.resign(game_id)


@api.post("/games/{game_id}/hint")
def game_hint(game_id: int) -> dict[str, object]:
    return games.hint(game_id)


# --- analisi -----------------------------------------------------------------------------
@api.post("/games/{game_id}/analyze")
def analyze_game(game_id: int) -> dict[str, object]:
    return analysis.worker.submit(game_id)


@api.get("/games/{game_id}/analysis")
def game_analysis(game_id: int) -> dict[str, object]:
    result = analysis.analysis_response(game_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Analisi non ancora richiesta: usa POST /api/games/{id}/analyze.")
    return result


@api.post("/analysis/position")
def analyze_position(body: PositionBody) -> dict[str, object]:
    return analysis.analyse_position(body.fen, body.multipv)


# --- motore ------------------------------------------------------------------------------
@api.get("/engine/status")
def engine_status() -> dict[str, object]:
    return engine.manager.status()


@api.put("/engine/settings")
def engine_settings(body: EngineSettingsBody) -> dict[str, object]:
    engine.manager.apply_settings(body.profile, body.threads, body.hash_mb)
    return engine.manager.status()


# --- studio (CFA, GMAT) ---------------------------------------------------------------------
@api.get("/study/exams")
def study_exams() -> dict[str, object]:
    return study.exams_response()


@api.get("/study/exams/{exam_id}")
def study_exam(exam_id: str) -> dict[str, object]:
    return study.exam_response(exam_id)


@api.get("/study/exams/{exam_id}/path")
def study_path(exam_id: str) -> dict[str, object]:
    return study_content.path_response(exam_id)


@api.put("/study/exams/{exam_id}/lessons/{topic_id}")
def study_lesson_done(exam_id: str, topic_id: str, body: LessonDoneBody) -> dict[str, object]:
    return study_content.set_lesson_done(exam_id, topic_id, body.done)


@api.get("/study/exams/{exam_id}/next")
def study_next(exam_id: str, topic: str | None = None) -> dict[str, object]:
    return study.next_question(exam_id, topic)


@api.post("/study/questions/{question_id}/answer")
def study_answer(question_id: int, body: StudyAnswerBody) -> dict[str, object]:
    return study.answer(question_id, body.choice, body.time_ms)


@api.post("/study/questions/{question_id}/flag")
def study_flag(question_id: int) -> dict[str, object]:
    return study.flag(question_id)


# --- Claude (chiave API) ---------------------------------------------------------------------
def _claude_status() -> dict[str, object]:
    return {"enabled": llm.enabled(), "source": llm.key_source(), "model": config.CLAUDE_MODEL}


@api.get("/settings/claude")
def claude_settings() -> dict[str, object]:
    return _claude_status()


@api.put("/settings/claude")
def put_claude_settings(body: ClaudeSettingsBody) -> dict[str, object]:
    llm.set_api_key(body.api_key)
    return _claude_status()


app.include_router(api)


# --- interfaccia web (build di Vite) ---------------------------------------------------------
def _frontend_index() -> Path | None:
    static = config.STATIC_DIR
    if static is None:
        return None
    index = static / "index.html"
    return index if index.is_file() else None


@app.api_route("/{full_path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
def frontend(full_path: str, request: Request) -> Response:
    """Serve la build del frontend con fallback a index.html per le rotte client (/tattica, /analisi/3...).

    Le rotte /api inesistenti restano 404 JSON: il fallback non le "copre".
    """
    if full_path == "api" or full_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    index = _frontend_index()
    if index is None:
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    if request.method not in ("GET", "HEAD"):
        return JSONResponse(status_code=405, content={"detail": "Method Not Allowed"})
    root = index.parent.resolve()
    if full_path:
        candidate = (root / full_path).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            # i file in /assets hanno l'hash nel nome: si possono tenere in cache a lungo
            cache = "public, max-age=31536000, immutable" if full_path.startswith("assets/") else "no-cache"
            return FileResponse(candidate, headers={"Cache-Control": cache})
        if Path(full_path).suffix and not full_path.endswith(".html"):
            # file statico mancante (es. /favicon.ico): niente fallback HTML
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
    return FileResponse(index, headers={"Cache-Control": "no-cache"})
