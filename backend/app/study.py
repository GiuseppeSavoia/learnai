"""Studio per esami (CFA, GMAT): banca di domande generate da Claude, rating Glicko per esame, debolezze.

Stesso schema degli scacchi: le domande hanno un rating di difficoltà, ogni risposta aggiorna il tuo rating
(Glicko-2, come per i puzzle) e le statistiche per argomento decidono su cosa insistere.

Le domande sono generate da Claude (testo in inglese, come all'esame; spiegazioni in italiano) e salvate in
locale: una volta generate si riusano senza altri costi. Quando la banca di un argomento si sta esaurendo,
un thread in background ne prepara altre per non far aspettare.
"""

from __future__ import annotations

import json
import logging
import math
import os
import random
import threading
from collections.abc import Callable
from dataclasses import dataclass

from . import config, db, llm, rating, syllabus

log = logging.getLogger(__name__)

INITIAL_RATING = 1300.0
INITIAL_RD = 350.0
#: RD alto per le domande: la difficoltà stimata da Claude non è calibrata, quindi pesa meno sul tuo rating
QUESTION_RD = 150.0
DIFFICULTY_RATING = {1: 1100, 2: 1300, 3: 1500, 4: 1700, 5: 1900}
BATCH_SIZE = 4
PREFETCH_BELOW = 3
GENERATION_TIMEOUT = 300.0


class StudyError(Exception):
    """Richiesta non valida (esame/argomento inesistente)."""


class StudyNotFoundError(Exception):
    pass


class StudyUnavailableError(Exception):
    """Nessuna domanda disponibile e generazione impossibile (chiave mancante, errore di rete...)."""


@dataclass(frozen=True)
class GeneratedQuestion:
    vignette: str
    stem: str
    choices: list[str]
    answer: int
    explanation: str


#: Funzione di generazione (sostituibile nei test): (esame, argomento, difficoltà, n, domande_recenti) -> domande
Generator = Callable[[syllabus.Exam, syllabus.Topic, int, int, list[str]], list[GeneratedQuestion]]


def _prefetch_enabled() -> bool:
    return os.environ.get("CHESSAI_STUDY_PREFETCH", "1") != "0"


# --- generazione con Claude ------------------------------------------------------------------
_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "vignette": {"type": "string"},
                    "stem": {"type": "string"},
                    "choices": {"type": "array", "items": {"type": "string"}},
                    "answer_index": {"type": "integer"},
                    "explanation": {"type": "string"},
                },
                "required": ["vignette", "stem", "choices", "answer_index", "explanation"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}

_DIFFICULTY_TEXT = {
    1: "easy (a candidate who has just studied the topic should get it right)",
    2: "moderately easy",
    3: "medium, comparable to a typical real exam question",
    4: "hard (multi-step reasoning or a subtle distractor)",
    5: "very hard (among the hardest questions on the real exam)",
}


def _prompt(exam: syllabus.Exam, topic: syllabus.Topic, difficulty: int, n: int, recent: list[str]) -> str:
    letters = "ABCDE"[: exam.n_choices]
    if topic.kind == "ds":
        fmt = (
            "Each item is a GMAT Data Sufficiency question: the stem contains the question followed by the two "
            "statements labelled (1) and (2). Set `choices` to an empty array: the five standard Data Sufficiency "
            "answer options are added by the app in the canonical order A-E. `answer_index` is 0-4 (A-E)."
        )
    else:
        fmt = (
            f"Each item has exactly {exam.n_choices} answer choices ({', '.join(letters)}), plausible and mutually "
            f"distinct, with exactly one correct answer. Do not prefix choices with letters. `answer_index` is "
            f"0-{exam.n_choices - 1}."
        )
    vignette = (
        "Each item must be self-contained with its own case `vignette` (150-350 words, with the data needed to "
        "answer, tables written as plain text) in the style of the exam's item sets."
        if exam.vignette
        else "Leave `vignette` empty unless the item needs a passage, table or chart (then put it there as plain text)."
    )
    avoid = ""
    if recent:
        avoid = "\nAvoid repeating these already-used questions:\n" + "\n".join(f"- {s}" for s in recent)
    return (
        f"Write {n} ORIGINAL practice questions for the {exam.label} exam.\n"
        f"Topic: {topic.label}. Focus: {topic.focus}.\n"
        f"Difficulty: {_DIFFICULTY_TEXT[difficulty]}.\n\n"
        "Rules:\n"
        "- Write the vignette, stem and choices in English, as in the real exam.\n"
        "- Write the `explanation` in ITALIAN (3-6 sentences): why the correct answer is right, why the tempting "
        "wrong answers are wrong, and the key concept or formula to remember. Show the calculation when there is one.\n"
        "- Questions must be your own: never reproduce or closely paraphrase official CFA Institute or GMAC "
        "material or commercial prep-provider questions.\n"
        "- Double-check every calculation and make sure exactly one choice is correct.\n"
        "- Vary the subtopics across the items.\n"
        f"- {fmt}\n- {vignette}{avoid}"
    )


def claude_generate(
    exam: syllabus.Exam, topic: syllabus.Topic, difficulty: int, n: int, recent: list[str]
) -> list[GeneratedQuestion]:
    if not llm.enabled():
        raise StudyUnavailableError(
            "Hai completato le domande integrate di questo argomento. Per generarne altre con Claude "
            "(a pagamento) aggiungi una chiave API Anthropic in Impostazioni, oppure passa a un altro argomento."
        )
    client = llm.client(timeout=GENERATION_TIMEOUT, max_retries=2)
    with client.beta.messages.stream(
        model=config.CLAUDE_MODEL,
        max_tokens=32000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        thinking={"type": "adaptive"},
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": _SCHEMA}},
        system=(
            "You are an expert item writer for professional finance and business-school admission exams. "
            "You write accurate, exam-realistic multiple-choice questions with rigorous answer keys."
        ),
        messages=[{"role": "user", "content": _prompt(exam, topic, difficulty, n, recent)}],
    ) as stream:
        response = stream.get_final_message()
    if response.stop_reason in ("refusal", "max_tokens"):
        raise StudyUnavailableError(f"Generazione delle domande non riuscita ({response.stop_reason}).")
    # l'ultimo blocco di testo: con i fallback un eventuale testo parziale del primo modello lo precede
    texts = [b.text for b in response.content if b.type == "text"]
    text = texts[-1] if texts else ""
    data = json.loads(text)
    return [
        GeneratedQuestion(
            vignette=str(q.get("vignette", "")),
            stem=str(q.get("stem", "")),
            choices=[str(c) for c in q.get("choices", [])],
            answer=int(q.get("answer_index", -1)),
            explanation=str(q.get("explanation", "")),
        )
        for q in data.get("questions", [])
    ]


generator: Generator = claude_generate


def _normalize(exam: syllabus.Exam, topic: syllabus.Topic, q: GeneratedQuestion, rng: random.Random) -> GeneratedQuestion | None:
    """Valida una domanda generata; per le MCQ mescola le opzioni (gli LLM tendono a mettere la giusta sempre lì)."""
    stem = q.stem.strip()
    explanation = q.explanation.strip()
    vignette = q.vignette.strip()
    if not stem or not explanation or (exam.vignette and not vignette):
        return None
    if topic.kind == "ds":
        if not 0 <= q.answer < len(syllabus.DS_CHOICES):
            return None
        return GeneratedQuestion(vignette, stem, list(syllabus.DS_CHOICES), q.answer, explanation)
    choices = [c.strip() for c in q.choices]
    if len(choices) != exam.n_choices or any(not c for c in choices) or len({c.lower() for c in choices}) != len(choices):
        return None
    if not 0 <= q.answer < len(choices):
        return None
    order = list(range(len(choices)))
    rng.shuffle(order)
    return GeneratedQuestion(vignette, stem, [choices[i] for i in order], order.index(q.answer), explanation)


_locks: dict[tuple[str, str], threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(exam_id: str, topic_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault((exam_id, topic_id), threading.Lock())


def _recent_stems(exam_id: str, topic_id: str, limit: int = 15) -> list[str]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT stem FROM study_questions WHERE exam = ? AND topic = ? ORDER BY id DESC LIMIT ?",
            (exam_id, topic_id, limit),
        ).fetchall()
    return [" ".join(r["stem"].split())[:120] for r in rows]


def generate_batch(exam: syllabus.Exam, topic: syllabus.Topic, difficulty: int, n: int = BATCH_SIZE) -> int:
    """Genera e salva fino a `n` domande; restituisce quante ne sono state salvate."""
    rng = random.Random()
    raw = generator(exam, topic, difficulty, n, _recent_stems(exam.id, topic.id))
    valid = [q for q in (_normalize(exam, topic, r, rng) for r in raw) if q is not None]
    if len(valid) < len(raw):
        log.warning("Scartate %d domande generate non valide (%s/%s)", len(raw) - len(valid), exam.id, topic.id)
    with db.connect() as conn:
        for q in valid:
            conn.execute(
                "INSERT INTO study_questions(exam, topic, difficulty, rating, vignette, stem, choices, answer,"
                " explanation, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (exam.id, topic.id, difficulty, DIFFICULTY_RATING[difficulty], q.vignette, q.stem,
                 json.dumps(q.choices, ensure_ascii=False), q.answer, q.explanation, db.now_iso()),
            )
    return len(valid)


def _prefetch(exam: syllabus.Exam, topic: syllabus.Topic, difficulty: int) -> None:
    lock = _lock_for(exam.id, topic.id)
    if not lock.acquire(blocking=False):
        return
    try:
        generate_batch(exam, topic, difficulty)
    except Exception as exc:  # in background: solo log, la prossima richiesta riproverà
        log.warning("Pre-generazione domande non riuscita (%s/%s): %s", exam.id, topic.id, exc)
    finally:
        lock.release()


# --- profilo per esame ------------------------------------------------------------------------
def _exam(exam_id: str) -> syllabus.Exam:
    exam = syllabus.get_exam(exam_id)
    if exam is None:
        raise StudyError(f"Esame sconosciuto: {exam_id}")
    return exam


def _rating_row(exam_id: str) -> dict[str, float]:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM study_ratings WHERE exam = ?", (exam_id,)).fetchone()
    if row is None:
        return {"rating": INITIAL_RATING, "rd": INITIAL_RD, "vol": rating.DEFAULT_VOLATILITY, "answered": 0, "correct": 0}
    return dict(row)


def _topic_stats(exam_id: str) -> dict[str, tuple[int, int]]:
    with db.connect() as conn:
        rows = conn.execute("SELECT topic, attempts, errors FROM study_topic_stats WHERE exam = ?", (exam_id,)).fetchall()
    return {r["topic"]: (r["attempts"], r["errors"]) for r in rows}


def _weakness(attempts: int, errors: int) -> float:
    """Tasso d'errore smussato (stesso prior degli scacchi: 1 errore su 4)."""
    return (errors + 1) / (attempts + 4)


def _pick_topic(exam: syllabus.Exam, rng: random.Random) -> syllabus.Topic:
    stats = _topic_stats(exam.id)
    weights = []
    for t in exam.topics:
        attempts, errors = stats.get(t.id, (0, 0))
        weights.append(t.weight * (0.5 + 2 * _weakness(attempts, errors)))
    return rng.choices(exam.topics, weights=weights, k=1)[0]


def _target_difficulty(user_rating: float, rng: random.Random) -> int:
    base = min(DIFFICULTY_RATING, key=lambda d: abs(DIFFICULTY_RATING[d] - user_rating))
    return max(1, min(5, base + rng.choice((-1, 0, 0, 1))))


def _unseen(conn: object, exam_id: str, topic_id: str) -> list[dict[str, object]]:
    rows = conn.execute(  # type: ignore[attr-defined]
        "SELECT q.* FROM study_questions q WHERE q.exam = ? AND q.topic = ? AND q.flagged = 0"
        " AND NOT EXISTS (SELECT 1 FROM study_attempts a WHERE a.question_id = q.id)",
        (exam_id, topic_id),
    ).fetchall()
    return [dict(r) for r in rows]


def _public(q: dict[str, object], exam: syllabus.Exam) -> dict[str, object]:
    topic = exam.topic(str(q["topic"]))
    return {
        "id": q["id"],
        "exam": exam.id,
        "topic": q["topic"],
        "topic_label": topic.label if topic else q["topic"],
        "difficulty": q["difficulty"],
        "vignette": q["vignette"],
        "stem": q["stem"],
        "choices": json.loads(str(q["choices"])),
    }


def next_question(exam_id: str, topic_id: str | None = None) -> dict[str, object]:
    exam = _exam(exam_id)
    rng = random.Random()
    if topic_id:
        topic = exam.topic(topic_id)
        if topic is None:
            raise StudyError(f"Argomento sconosciuto per {exam.label}: {topic_id}")
    else:
        topic = _pick_topic(exam, rng)
    user_rating = float(_rating_row(exam.id)["rating"])
    difficulty = _target_difficulty(user_rating, rng)

    with db.connect() as conn:
        pool = _unseen(conn, exam.id, topic.id)
    if not pool:
        with _lock_for(exam.id, topic.id):
            with db.connect() as conn:
                pool = _unseen(conn, exam.id, topic.id)
            if not pool:
                try:
                    generate_batch(exam, topic, difficulty)
                except StudyUnavailableError:
                    raise
                except Exception as exc:
                    log.warning("Generazione domande non riuscita (%s/%s): %s", exam.id, topic.id, exc)
                    raise StudyUnavailableError("Non sono riuscito a generare nuove domande: riprova tra poco.") from exc
                with db.connect() as conn:
                    pool = _unseen(conn, exam.id, topic.id)
    if not pool:
        raise StudyUnavailableError("Nessuna domanda valida generata: riprova.")

    pool.sort(key=lambda q: abs(float(q["rating"]) - user_rating))  # type: ignore[arg-type]
    question = rng.choice(pool[:3])
    if len(pool) - 1 < PREFETCH_BELOW and _prefetch_enabled() and llm.enabled():
        threading.Thread(target=_prefetch, args=(exam, topic, difficulty), daemon=True).start()
    return _public(question, exam)


def _load(question_id: int) -> dict[str, object]:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM study_questions WHERE id = ?", (question_id,)).fetchone()
    if row is None:
        raise StudyNotFoundError(f"Domanda {question_id} non trovata")
    return dict(row)


def answer(question_id: int, choice: int, time_ms: int) -> dict[str, object]:
    q = _load(question_id)
    exam = _exam(str(q["exam"]))
    n_choices = len(json.loads(str(q["choices"])))
    if not 0 <= choice < n_choices:
        raise StudyError("Risposta fuori intervallo")
    correct = choice == q["answer"]
    with db.connect() as conn:
        first = conn.execute("SELECT 1 FROM study_attempts WHERE question_id = ?", (question_id,)).fetchone() is None
    rated = first and not q["flagged"]
    row = _rating_row(exam.id)
    before = float(row["rating"])
    new = rating.Rating(before, float(row["rd"]), float(row["vol"]))
    if rated:
        new = rating.update(new, rating.Rating(float(q["rating"]), QUESTION_RD), 1.0 if correct else 0.0)  # type: ignore[arg-type]
    delta = new.rating - before if rated else 0.0
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO study_attempts(question_id, exam, topic, ts, day, choice, correct, time_ms, rated, delta)"
            " VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (question_id, exam.id, q["topic"], db.now_iso(), db.today(), choice, int(correct), time_ms, int(rated), delta),
        )
        if rated:
            conn.execute(
                "INSERT INTO study_ratings(exam, rating, rd, vol, answered, correct) VALUES(?, ?, ?, ?, 1, ?)"
                " ON CONFLICT(exam) DO UPDATE SET rating = excluded.rating, rd = excluded.rd, vol = excluded.vol,"
                " answered = answered + 1, correct = correct + excluded.correct",
                (exam.id, new.rating, new.rd, new.volatility, int(correct)),
            )
            conn.execute(
                "INSERT INTO study_topic_stats(exam, topic, attempts, errors) VALUES(?, ?, 1, ?)"
                " ON CONFLICT(exam, topic) DO UPDATE SET attempts = attempts + 1, errors = errors + excluded.errors",
                (exam.id, q["topic"], int(not correct)),
            )
    return {
        "correct": correct,
        "answer": q["answer"],
        "explanation": q["explanation"],
        "rated": rated,
        "rating_before": round(before),
        "rating_after": round(new.rating),
        "rating_delta": round(delta, 1),
    }


def flag(question_id: int) -> dict[str, object]:
    """Segnala una domanda errata: esclusa per sempre e il suo effetto sul rating viene annullato."""
    q = _load(question_id)
    if q["flagged"]:
        return {"flagged": True, "rating_restored": 0}
    with db.connect() as conn:
        row = conn.execute(
            "SELECT correct, delta FROM study_attempts WHERE question_id = ? AND rated = 1", (question_id,)
        ).fetchone()
        conn.execute("UPDATE study_questions SET flagged = 1 WHERE id = ?", (question_id,))
        restored = 0.0
        if row is not None:
            restored = -float(row["delta"])
            conn.execute(
                "UPDATE study_ratings SET rating = rating - ?, answered = MAX(answered - 1, 0),"
                " correct = MAX(correct - ?, 0) WHERE exam = ?",
                (row["delta"], row["correct"], q["exam"]),
            )
            conn.execute(
                "UPDATE study_topic_stats SET attempts = MAX(attempts - 1, 0), errors = MAX(errors - ?, 0)"
                " WHERE exam = ? AND topic = ?",
                (int(not row["correct"]), q["exam"], q["topic"]),
            )
            conn.execute("UPDATE study_attempts SET rated = 0, delta = 0 WHERE question_id = ?", (question_id,))
    return {"flagged": True, "rating_restored": round(restored, 1)}


# --- riepiloghi ---------------------------------------------------------------------------------
def _progress(exam: syllabus.Exam, value: float) -> float:
    span = exam.target_rating - INITIAL_RATING
    return round(max(0.0, min(100.0, (value - INITIAL_RATING) / span * 100)), 1)


def _bank_counts() -> dict[str, tuple[int, int]]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT exam, COUNT(*) AS total, SUM(CASE WHEN NOT EXISTS (SELECT 1 FROM study_attempts a"
            " WHERE a.question_id = q.id) AND flagged = 0 THEN 1 ELSE 0 END) AS unseen"
            " FROM study_questions q GROUP BY exam"
        ).fetchall()
    return {r["exam"]: (r["total"], r["unseen"] or 0) for r in rows}


def _summary(exam: syllabus.Exam, banks: dict[str, tuple[int, int]]) -> dict[str, object]:
    row = _rating_row(exam.id)
    answered = int(row["answered"])
    total, unseen = banks.get(exam.id, (0, 0))
    return {
        "id": exam.id,
        "label": exam.label,
        "short": exam.short,
        "description": exam.description,
        "rating": round(float(row["rating"])),
        "rd": round(float(row["rd"])),
        "target_rating": exam.target_rating,
        "progress_pct": _progress(exam, float(row["rating"])),
        "answered": answered,
        "accuracy": round(int(row["correct"]) / answered, 3) if answered else None,
        "bank_total": total,
        "bank_unseen": unseen,
    }


def exams_response() -> dict[str, object]:
    banks = _bank_counts()
    return {
        "claude_enabled": llm.enabled(),
        "exams": [_summary(e, banks) for e in syllabus.EXAMS.values()],
    }


def exam_response(exam_id: str) -> dict[str, object]:
    exam = _exam(exam_id)
    stats = _topic_stats(exam.id)
    total_weight = sum(t.weight for t in exam.topics)
    topics = []
    for t in exam.topics:
        attempts, errors = stats.get(t.id, (0, 0))
        topics.append({
            "id": t.id,
            "label": t.label,
            "weight_pct": round(t.weight / total_weight * 100, 1),
            "attempts": attempts,
            "errors": errors,
            "accuracy": round((attempts - errors) / attempts, 3) if attempts else None,
            "weakness": round(_weakness(attempts, errors) * (1 + math.log1p(errors)), 3),
        })
    return {**_summary(exam, _bank_counts()), "claude_enabled": llm.enabled(), "topics": topics}
