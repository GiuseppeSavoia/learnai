"""Punto d'ingresso del server LearnAI (usato dall'app per Mac tramite PyInstaller).

Avvia uvicorn su CHESSAI_HOST:CHESSAI_PORT (default 127.0.0.1:8000) servendo API e frontend.
Opzioni da riga di comando: ``--host``, ``--port``.

Se ``CHESSAI_PARENT_PID`` è impostata, il server si chiude da solo (con lo spegnimento ordinato
che ferma anche Stockfish) quando il processo padre — l'app per Mac — termina, anche se l'app
viene chiusa in modo anomalo: così non restano processi orfani.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import threading
import time

import uvicorn

from app import config
from app.main import app

log = logging.getLogger("chessai.server")


def _watch_parent(parent_pid: int) -> None:
    while True:
        time.sleep(1.0)
        if os.getppid() != parent_pid:
            log.warning("Processo padre %d terminato: chiudo il server.", parent_pid)
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(10.0)
            os._exit(1)  # lo spegnimento ordinato non è riuscito


def main() -> None:
    parser = argparse.ArgumentParser(description="Server LearnAI (API + interfaccia web)")
    parser.add_argument("--host", default=config.HOST)
    parser.add_argument("--port", type=int, default=config.PORT)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log.info(
        "LearnAI server: dati=%s puzzle=%s frontend=%s stockfish=%s",
        config.DATA_DIR,
        config.PUZZLE_DB_PATH,
        config.STATIC_DIR,
        config.stockfish_path(),
    )

    parent = os.environ.get("CHESSAI_PARENT_PID")
    if parent and parent.isdigit():
        threading.Thread(target=_watch_parent, args=(int(parent),), name="parent-watch", daemon=True).start()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
