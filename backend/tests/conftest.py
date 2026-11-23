"""Configurazione dei test: dati utente in una cartella temporanea, puzzle dal set integrato."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="chessai-test-"))
os.environ["CHESSAI_DATA_DIR"] = str(_TMP)
os.environ["CHESSAI_PUZZLES_DB"] = str(_TMP / "missing-puzzles.db")
# niente chiamate a Claude (a pagamento) né thread in background durante i test
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["CHESSAI_STUDY_PREFETCH"] = "0"
# banca vuota di default (i test sui contenuti integrati la riempiono esplicitamente)
os.environ["CHESSAI_STUDY_SEED"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """Client con database utente vuoto per ogni test."""
    for suffix in ("", "-wal", "-shm"):
        Path(f"{config.USER_DB_PATH}{suffix}").unlink(missing_ok=True)
    with TestClient(app) as test_client:
        yield test_client
