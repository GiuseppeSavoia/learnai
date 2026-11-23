"""Accesso a Claude: risoluzione della chiave API e costruzione del client.

La chiave si cerca prima nella variabile d'ambiente ``ANTHROPIC_API_KEY`` (sviluppo da terminale), poi
nelle impostazioni locali (salvata dalla pagina Impostazioni: necessaria per l'app per Mac, che aperta dal
Finder non eredita le variabili della shell). La chiave non viene mai restituita dalle API né scritta nei log.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from . import db

if TYPE_CHECKING:
    import anthropic

SETTING_KEY = "anthropic_api_key"


def api_key() -> str | None:
    env = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if env:
        return env
    try:
        stored = (db.get_setting(SETTING_KEY) or "").strip()
    except Exception:  # database non ancora inizializzato
        return None
    return stored or None


def enabled() -> bool:
    return api_key() is not None


def key_source() -> str | None:
    """"env", "settings" oppure None: utile alla UI per sapere se la chiave si può modificare."""
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return "env"
    return "settings" if enabled() else None


def set_api_key(value: str | None) -> None:
    db.set_setting(SETTING_KEY, (value or "").strip())


def client(timeout: float, max_retries: int = 2) -> anthropic.Anthropic:
    import anthropic

    return anthropic.Anthropic(api_key=api_key(), timeout=timeout, max_retries=max_retries)
