"""Contenuti integrati: struttura valida per ogni esame, caricamento nella banca, API del percorso."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import study_content, syllabus


@pytest.mark.parametrize("exam_id", list(syllabus.EXAMS))
def test_content_is_valid(exam_id: str) -> None:
    exam = syllabus.EXAMS[exam_id]
    content = study_content.load(exam_id)
    assert content["exam"] == exam_id
    modules = content["modules"]
    assert {m["topic"] for m in modules} == {t.id for t in exam.topics}, "ogni argomento ha il suo modulo"
    ids: set[str] = set()
    for m in modules:
        topic = exam.topic(m["topic"])
        assert topic is not None
        assert m["title"] and m["summary"]
        assert len(m["sections"]) >= 3, m["topic"]
        for sec in m["sections"]:
            assert sec["title"] and sec["body"] and all(isinstance(p, str) and p for p in sec["body"])
        assert m["pitfalls"], m["topic"]
        # l'interfaccia usa il testo come chiave React: titoli, formule ed errori devono essere unici nel modulo
        for key in ("formulas", "pitfalls"):
            assert len(set(m.get(key, []))) == len(m.get(key, [])), f"{m['topic']}: {key} duplicati"
        titles = [sec["title"] for sec in m["sections"]]
        assert len(set(titles)) == len(titles), f"{m['topic']}: titoli di sezione duplicati"
        questions = study_content.module_questions(m)
        assert len(questions) >= 4, m["topic"]
        for q in questions:
            qid = q["id"]
            assert qid not in ids, f"id duplicato {qid}"
            ids.add(qid)
            assert 1 <= q["difficulty"] <= 5, qid
            assert q["stem"].strip() and q["explanation"].strip(), qid
            if exam.vignette:
                assert q["vignette"].strip(), f"{qid}: manca la vignette"
            if topic.kind == "ds":
                assert 0 <= q["answer"] < 5, qid
            else:
                choices = [c.strip() for c in q["choices"]]
                assert len(choices) == exam.n_choices, qid
                assert all(choices) and len({c.lower() for c in choices}) == len(choices), qid
                assert 0 <= q["answer"] < len(choices), qid


def test_seed_is_idempotent_and_serves_without_key(client: TestClient) -> None:
    added = study_content.seed_all()
    assert added > 0
    assert study_content.seed_all() == 0
    summary = {e["id"]: e for e in client.get("/api/study/exams").json()["exams"]}
    assert summary["cfa1"]["bank_unseen"] > 0
    q = client.get("/api/study/exams/cfa1/next").json()
    assert q["choices"] and "answer" not in q


def test_path_and_lesson_done(client: TestClient) -> None:
    data = client.get("/api/study/exams/cfa1/path").json()
    assert data["modules"][0]["step"] == 1
    first = data["modules"][0]
    assert first["sections"] and first["lesson_done"] is False
    upd = client.put(f"/api/study/exams/cfa1/lessons/{first['topic']}", json={"done": True}).json()
    assert upd["modules"][0]["lesson_done"] is True
    assert client.put("/api/study/exams/cfa1/lessons/nope", json={"done": True}).status_code == 400
