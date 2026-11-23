"""Studio CFA/GMAT: generazione (finta), selezione, risposta, rating, segnalazione, chiave API."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app import study, syllabus


def _fake_generator(calls: list[tuple[str, str, int]]) -> study.Generator:
    def gen(exam: syllabus.Exam, topic: syllabus.Topic, difficulty: int, n: int, recent: list[str]) -> list[study.GeneratedQuestion]:
        calls.append((exam.id, topic.id, difficulty))
        start = len(recent)
        out = [
            study.GeneratedQuestion(
                vignette="Case text." if exam.vignette else "",
                stem=f"Question {start + i} on {topic.id}?",
                choices=[] if topic.kind == "ds" else [f"choice {k}" for k in range(exam.n_choices)],
                answer=0,
                explanation="Spiegazione.",
            )
            for i in range(n)
        ]
        # una domanda non valida (opzioni duplicate) deve essere scartata
        out.append(study.GeneratedQuestion("x", "bad", ["a"] * exam.n_choices, 0, "x"))
        return out

    return gen


@pytest.fixture()
def calls(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[tuple[str, str, int]]]:
    log: list[tuple[str, str, int]] = []
    monkeypatch.setattr(study, "generator", _fake_generator(log))
    yield log


def _correct_index(client: TestClient, qid: int) -> int:
    from app import db

    with db.connect() as conn:
        return conn.execute("SELECT answer FROM study_questions WHERE id = ?", (qid,)).fetchone()["answer"]


def test_exams_list(client: TestClient) -> None:
    data = client.get("/api/study/exams").json()
    assert data["claude_enabled"] is False
    assert [e["id"] for e in data["exams"]] == ["cfa1", "cfa2", "cfa3", "gmat"]
    assert data["exams"][0]["rating"] == 1300


def test_exam_detail_and_unknown(client: TestClient) -> None:
    data = client.get("/api/study/exams/cfa1").json()
    assert len(data["topics"]) == 10
    assert abs(sum(t["weight_pct"] for t in data["topics"]) - 100) < 1
    assert client.get("/api/study/exams/nope").status_code == 400


def test_next_without_key_is_503(client: TestClient) -> None:
    r = client.get("/api/study/exams/cfa1/next")
    assert r.status_code == 503
    assert "chiave api" in r.json()["detail"].lower()


def test_generate_answer_and_rating(client: TestClient, calls: list[tuple[str, str, int]]) -> None:
    q = client.get("/api/study/exams/cfa1/next?topic=fixed").json()
    assert calls and calls[0][:2] == ("cfa1", "fixed")
    assert "answer" not in q and "explanation" not in q
    assert len(q["choices"]) == 3
    correct = _correct_index(client, q["id"])

    res = client.post(f"/api/study/questions/{q['id']}/answer", json={"choice": correct, "time_ms": 1000}).json()
    assert res["correct"] is True and res["rated"] is True and res["rating_delta"] > 0
    assert res["explanation"] == "Spiegazione."

    again = client.post(f"/api/study/questions/{q['id']}/answer", json={"choice": correct}).json()
    assert again["rated"] is False and again["rating_delta"] == 0

    # la stessa domanda non viene riproposta; la banca non si rigenera finché ci sono inedite
    q2 = client.get("/api/study/exams/cfa1/next?topic=fixed").json()
    assert q2["id"] != q["id"]
    assert len(calls) == 1

    summary = client.get("/api/study/exams").json()["exams"][0]
    assert summary["answered"] == 1 and summary["accuracy"] == 1.0
    assert summary["bank_total"] == study.BATCH_SIZE  # la domanda non valida è stata scartata


def test_wrong_answer_and_flag_restores_rating(client: TestClient, calls: list[tuple[str, str, int]]) -> None:
    q = client.get("/api/study/exams/cfa1/next?topic=quant").json()
    wrong = (_correct_index(client, q["id"]) + 1) % 3
    res = client.post(f"/api/study/questions/{q['id']}/answer", json={"choice": wrong}).json()
    assert res["correct"] is False and res["rating_delta"] < 0

    flagged = client.post(f"/api/study/questions/{q['id']}/flag").json()
    assert flagged["flagged"] is True and flagged["rating_restored"] > 0
    detail = client.get("/api/study/exams/cfa1").json()
    assert detail["rating"] == 1300 and detail["answered"] == 0
    quant = next(t for t in detail["topics"] if t["id"] == "quant")
    assert quant["attempts"] == 0


def test_gmat_data_sufficiency_uses_canonical_choices(client: TestClient, calls: list[tuple[str, str, int]]) -> None:
    q = client.get("/api/study/exams/gmat/next?topic=ds").json()
    assert q["choices"] == list(syllabus.DS_CHOICES)


def test_vignette_exams_require_vignette(client: TestClient, calls: list[tuple[str, str, int]]) -> None:
    q = client.get("/api/study/exams/cfa2/next?topic=equity").json()
    assert q["vignette"] == "Case text."


def test_answer_validation(client: TestClient, calls: list[tuple[str, str, int]]) -> None:
    q = client.get("/api/study/exams/cfa1/next?topic=econ").json()
    assert client.post(f"/api/study/questions/{q['id']}/answer", json={"choice": 3}).status_code == 400
    assert client.post("/api/study/questions/99999/answer", json={"choice": 0}).status_code == 404
    assert client.get("/api/study/exams/cfa1/next?topic=nope").status_code == 400


def test_claude_key_setting_never_returned(client: TestClient) -> None:
    assert client.get("/api/settings/claude").json()["enabled"] is False
    data = client.put("/api/settings/claude", json={"api_key": "sk-ant-test-123"}).json()
    assert data == {"enabled": True, "source": "settings", "model": data["model"]}
    assert "sk-ant" not in client.get("/api/settings/claude").text
    assert client.put("/api/settings/claude", json={"api_key": ""}).json()["enabled"] is False


class _Block:
    def __init__(self, type_: str, text: str = "") -> None:
        self.type = type_
        self.text = text


class _FakeStream:
    def __init__(self, message: object) -> None:
        self._message = message

    def __enter__(self) -> _FakeStream:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def get_final_message(self) -> object:
        return self._message


def _fake_client(stop_reason: str, text: str, captured: dict[str, object]) -> object:
    class Msg:
        def __init__(self) -> None:
            self.stop_reason = stop_reason
            self.content = [_Block("thinking"), _Block("text", text)]

    class Messages:
        def stream(self, **kwargs: object) -> _FakeStream:
            captured.update(kwargs)
            return _FakeStream(Msg())

    class Beta:
        messages = Messages()

    class Client:
        beta = Beta()

    return Client()


def _use_fake_claude(monkeypatch: pytest.MonkeyPatch, stop_reason: str, text: str) -> dict[str, object]:
    from app import llm

    captured: dict[str, object] = {}
    monkeypatch.setattr(llm, "api_key", lambda: "sk-test")
    monkeypatch.setattr(llm, "client", lambda timeout, max_retries=2: _fake_client(stop_reason, text, captured))
    return captured


def test_claude_generate_parses_structured_output(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    payload = {"questions": [
        {"vignette": "", "stem": f"Q{i}?", "choices": ["x", "y", "z"], "answer_index": 1, "explanation": "Perché."}
        for i in range(3)
    ]}
    captured = _use_fake_claude(monkeypatch, "end_turn", json.dumps(payload))
    q = client.get("/api/study/exams/cfa1/next?topic=deriv").json()
    assert q["stem"].startswith("Q") and sorted(q["choices"]) == ["x", "y", "z"]
    assert captured["fallbacks"] == "default"
    assert captured["output_config"]["format"]["type"] == "json_schema"  # type: ignore[index]
    res = client.post(f"/api/study/questions/{q['id']}/answer", json={"choice": q["choices"].index("y")}).json()
    assert res["correct"] is True


@pytest.mark.parametrize(("stop_reason", "text"), [("refusal", ""), ("max_tokens", "{\"questions\": ["), ("end_turn", "not json")])
def test_claude_generate_failures_are_503(client: TestClient, monkeypatch: pytest.MonkeyPatch, stop_reason: str, text: str) -> None:
    _use_fake_claude(monkeypatch, stop_reason, text)
    r = client.get("/api/study/exams/gmat/next?topic=cr")
    assert r.status_code == 503
