"""Contenuti di studio integrati: percorso (lezioni) e banca di domande scritte a mano, senza costi d'uso.

Un file JSON per esame in ``resources/study/<esame>.json``:

    {"exam": "cfa1", "modules": [
        {"topic": "ethics", "title": "...", "summary": "...",
         "sections": [{"title": "...", "body": ["paragrafo", ...]}],
         "formulas": ["..."], "pitfalls": ["..."],
         "questions": [{"id": "...", "difficulty": 1-5, "vignette": "", "stem": "...",
                        "choices": [...], "answer": 0, "explanation": "..."}],
         "item_sets": [{"id": "...", "vignette": "...", "questions": [...]}]}
    ]}

L'ordine dei moduli è l'ordine consigliato del percorso. All'avvio le domande vengono copiate nella banca
locale (una volta sola, per ``seed_id``) con le opzioni mescolate in modo deterministico; da lì le usa lo
stesso motore adattivo delle domande generate da Claude, che entrano in gioco solo a banca esaurita.
"""

from __future__ import annotations

import json
import os
import random
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import db, study, syllabus

CONTENT_DIR = Path(__file__).resolve().parent / "resources" / "study"


def seeding_enabled() -> bool:
    return os.environ.get("CHESSAI_STUDY_SEED", "1") != "0"


_LIST_KEYS = ("sections", "formulas", "pitfalls", "questions", "item_sets")


@lru_cache(maxsize=None)
def load(exam_id: str) -> dict[str, Any]:
    """Contenuto dell'esame: ``<esame>.json`` più eventuali pacchetti ``<esame>.<nome>.json``.

    I pacchetti aggiuntivi hanno la stessa forma; i moduli vengono uniti per argomento (le liste si
    accodano, l'ordine del percorso resta quello del file principale).
    """
    path = CONTENT_DIR / f"{exam_id}.json"
    if not path.is_file():
        return {"exam": exam_id, "modules": []}
    content = json.loads(path.read_text(encoding="utf-8"))
    by_topic = {m["topic"]: m for m in content["modules"]}
    for extra in sorted(CONTENT_DIR.glob(f"{exam_id}.*.json")):
        for module in json.loads(extra.read_text(encoding="utf-8"))["modules"]:
            base = by_topic.get(module["topic"])
            if base is None:
                content["modules"].append(module)
                by_topic[module["topic"]] = module
                continue
            for key in _LIST_KEYS:
                if module.get(key):
                    base[key] = [*base.get(key, []), *module[key]]
    return content


def module_questions(module: dict[str, Any]) -> list[dict[str, Any]]:
    """Domande del modulo, con quelle dei casi (item set) espanse e la vignette copiata in ognuna."""
    out = [dict(q) for q in module.get("questions", [])]
    for item_set in module.get("item_sets", []):
        for q in item_set["questions"]:
            out.append({**q, "vignette": item_set["vignette"]})
    return out


def seed_all() -> int:
    """Copia nella banca le domande integrate non ancora presenti; restituisce quante ne ha aggiunte."""
    added = 0
    with db.connect() as conn:
        for exam_id, exam in syllabus.EXAMS.items():
            for module in load(exam_id)["modules"]:
                topic = exam.topic(module["topic"])
                if topic is None:
                    continue
                for q in module_questions(module):
                    seed_id = f"{exam_id}:{q['id']}"
                    choices = list(syllabus.DS_CHOICES) if topic.kind == "ds" else list(q["choices"])
                    answer = int(q["answer"])
                    if topic.kind != "ds":
                        order = list(range(len(choices)))
                        random.Random(seed_id).shuffle(order)
                        choices, answer = [choices[i] for i in order], order.index(answer)
                    difficulty = int(q["difficulty"])
                    cur = conn.execute(
                        "INSERT OR IGNORE INTO study_questions(exam, topic, difficulty, rating, vignette, stem, choices,"
                        " answer, explanation, created_at, seed_id) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (exam_id, topic.id, difficulty, study.DIFFICULTY_RATING[difficulty], q.get("vignette", ""),
                         q["stem"], json.dumps(choices, ensure_ascii=False), answer, q["explanation"], db.now_iso(), seed_id),
                    )
                    added += cur.rowcount
    return added


def _lessons_done(exam_id: str) -> set[str]:
    with db.connect() as conn:
        rows = conn.execute("SELECT topic FROM study_lessons_done WHERE exam = ?", (exam_id,)).fetchall()
    return {r["topic"] for r in rows}


def set_lesson_done(exam_id: str, topic_id: str, done: bool) -> dict[str, object]:
    exam = syllabus.get_exam(exam_id)
    if exam is None or exam.topic(topic_id) is None:
        raise study.StudyError("Esame o argomento sconosciuto")
    with db.connect() as conn:
        if done:
            conn.execute(
                "INSERT OR REPLACE INTO study_lessons_done(exam, topic, done_at) VALUES(?, ?, ?)",
                (exam_id, topic_id, db.now_iso()),
            )
        else:
            conn.execute("DELETE FROM study_lessons_done WHERE exam = ? AND topic = ?", (exam_id, topic_id))
    return path_response(exam_id)


def path_response(exam_id: str) -> dict[str, object]:
    exam = syllabus.get_exam(exam_id)
    if exam is None:
        raise study.StudyError(f"Esame sconosciuto: {exam_id}")
    done = _lessons_done(exam_id)
    stats = {t["id"]: t for t in study.exam_response(exam_id)["topics"]}  # type: ignore[union-attr]
    modules = []
    for i, module in enumerate(load(exam_id)["modules"], start=1):
        topic = exam.topic(module["topic"])
        if topic is None:
            continue
        st = stats.get(topic.id, {})
        attempts = int(st.get("attempts", 0))
        accuracy = st.get("accuracy")
        mastered = attempts >= 5 and accuracy is not None and float(accuracy) >= 0.7
        modules.append({
            "step": i,
            "topic": topic.id,
            "topic_label": topic.label,
            "title": module["title"],
            "summary": module.get("summary", ""),
            "sections": module.get("sections", []),
            "formulas": module.get("formulas", []),
            "pitfalls": module.get("pitfalls", []),
            "n_questions": len(module_questions(module)),
            "lesson_done": topic.id in done,
            "attempts": attempts,
            "accuracy": accuracy,
            "mastered": mastered,
        })
    return {"exam": exam_id, "label": exam.label, "modules": modules}
