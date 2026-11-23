"""Livelli, consigli in italiano, pesatura delle debolezze e piano giornaliero."""

from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass
from datetime import date

from . import db, profile
from .engine import BOT_ELO_MAX, BOT_ELO_MIN
from .puzzle_store import get_store
from .themes import META_THEMES, THEME_TIPS_IT, label_it

WARMUP_COUNT = 5
FOCUS_COUNT = 10
WARMUP_OFFSET = -200


@dataclass(frozen=True)
class Level:
    number: int
    name: str
    min_rating: int


LEVELS = [
    Level(1, "Principiante", 0),
    Level(2, "Base", 1000),
    Level(3, "Intermedio", 1300),
    Level(4, "Avanzato", 1600),
    Level(5, "Esperto", 1800),
]
GOAL_LEVEL = Level(6, "Obiettivo raggiunto", 2000)

DEFAULT_FOCUS: dict[int, list[str]] = {
    1: ["hangingPiece", "mateIn1"],
    2: ["fork", "mateIn2"],
    3: ["pin", "discoveredAttack"],
    4: ["skewer", "deflection"],
    5: ["quietMove", "endgame"],
    6: ["defensiveMove", "zugzwang"],
}

TIPS: dict[int, dict[str, list[str]]] = {
    1: {
        "aperture": [
            "In apertura sviluppa cavalli e alfieri prima di muovere la Donna.",
            "Controlla il centro con i pedoni e e d: dà spazio ai tuoi pezzi.",
            "Arrocca presto per mettere al sicuro il Re.",
        ],
        "principi": [
            "Prima di ogni mossa chiediti: cosa minaccia l'avversario?",
            "Non lasciare pezzi indifesi: conta attaccanti e difensori.",
            "Scacchi, catture, minacce: controllali sempre, nell'ordine.",
        ],
        "finali": [
            "Impara il matto di Donna e Re contro Re: spingi il Re avversario sul bordo.",
            "Impara il matto di Torre e Re contro Re con la tecnica della «scatola».",
            "Con un pedone in più, attiva il Re e spingi il pedone accompagnandolo.",
        ],
    },
    2: {
        "aperture": [
            "Scegli un repertorio semplice: Italiana con il Bianco, 1...e5 o Caro-Kann con il Nero.",
            "Non muovere due volte lo stesso pezzo in apertura senza un motivo concreto.",
            "Collega le Torri: completa lo sviluppo prima di attaccare.",
        ],
        "principi": [
            "Cerca forchette di Cavallo: due bersagli in una sola mossa.",
            "Un pezzo inchiodato è un bersaglio: attaccalo di nuovo con un pedone.",
            "Quando sei in vantaggio di materiale, semplifica scambiando i pezzi.",
        ],
        "finali": [
            "Nei finali di Re e pedone impara la regola del quadrato.",
            "L'opposizione decide molti finali di pedoni: studiala.",
            "Il Re è un pezzo forte nel finale: portalo al centro.",
        ],
    },
    3: {
        "aperture": [
            "Studia le idee delle tue aperture, non solo le mosse: quali rotture di pedone cerchi?",
            "Dopo l'apertura chiediti dove vanno le Torri: colonne aperte e semiaperte.",
            "Evita di aprire il gioco quando sei in ritardo di sviluppo.",
        ],
        "principi": [
            "Individua il pezzo peggiore e miglioralo.",
            "Prima di catturare, cerca una mossa intermedia più forte.",
            "Crea un piano in base alla struttura pedonale.",
        ],
        "finali": [
            "Impara la posizione di Lucena e quella di Philidor nei finali di Torre.",
            "Nei finali di Torre la Torre va dietro ai pedoni passati.",
            "Alfiere contro Cavallo: con pedoni su entrambi i lati l'Alfiere è spesso migliore.",
        ],
    },
    4: {
        "aperture": [
            "Approfondisci le linee principali delle tue aperture fino alla mossa 12-15.",
            "Analizza le tue partite in apertura per capire dove esci dalla teoria.",
            "Conosci le strutture tipiche (Isolani, Carlsbad, Hedgehog) delle tue aperture.",
        ],
        "principi": [
            "Calcola le varianti forzanti fino in fondo prima di sacrificare.",
            "Valuta la profilassi: cosa vuole fare l'avversario e come impedirlo?",
            "Gestisci il tempo: non spendere tutto nelle prime 15 mosse.",
        ],
        "finali": [
            "Studia i finali di Torre con pedoni su un solo lato.",
            "Impara i finali di Alfieri di colore contrario: spesso sono patta.",
            "Nei finali attiva tutti i pezzi prima di spingere i pedoni.",
        ],
    },
    5: {
        "aperture": [
            "Prepara alternative a sorpresa nelle tue aperture principali.",
            "Studia partite magistrali nelle tue aperture per capire i piani tipici.",
            "Verifica le tue linee con il motore, ma ricorda le idee, non le mosse.",
        ],
        "principi": [
            "Allenati sul calcolo con posizioni complesse senza muovere i pezzi.",
            "Riconosci i momenti critici della partita e investi lì il tuo tempo.",
            "Cerca mosse tranquille vincenti quando le tattiche non funzionano.",
        ],
        "finali": [
            "Studia i finali teorici di Torre e pedone contro Torre in profondità.",
            "Allenati sui finali di Donna: la sicurezza del Re conta ancora.",
            "Nei finali complessi cerca la fortezza quando sei in svantaggio.",
        ],
    },
}
TIPS[6] = TIPS[5]


def level_for(strength: float, target_elo: int) -> Level:
    if strength >= target_elo:
        return GOAL_LEVEL
    current = LEVELS[0]
    for level in LEVELS:
        if strength >= level.min_rating:
            current = level
    return current


def profile_response() -> dict[str, object]:
    p = profile.load()
    level = level_for(p.strength, p.target_elo)
    span = max(1, p.target_elo - p.initial_rating)
    progress = max(0.0, min(100.0, (p.strength - p.initial_rating) / span * 100))
    return {
        "puzzle_rating": round(p.puzzle.rating),
        "puzzle_rd": round(p.puzzle.rd),
        "game_rating": round(p.game.rating),
        "game_rd": round(p.game.rd),
        "target_elo": p.target_elo,
        "level": level.number,
        "level_name": level.name,
        "progress_pct": round(progress, 1),
        "strength": round(p.strength),
        "initial_rating": round(p.initial_rating),
        "puzzles_solved": p.puzzles_solved,
        "puzzles_failed": p.puzzles_failed,
        "games_played": p.games_played,
        "rating_history": profile.history(),
    }


# --- debolezze -------------------------------------------------------------------
def weakness_score(stat: profile.ThemeStat) -> float:
    """Tasso d'errore smussato (prior 1 errore su 4) pesato per il numero di errori."""
    smoothed = (stat.errors + 1) / (stat.attempts + 4)
    return smoothed * (1 + math.log1p(stat.errors))


def ranked_weaknesses() -> list[tuple[str, float]]:
    available = get_store().theme_counts()
    ranked = [
        (s.theme, weakness_score(s))
        for s in profile.theme_stats()
        if s.errors > 0 and s.theme not in META_THEMES and available.get(s.theme, 0) > 0
    ]
    return sorted(ranked, key=lambda x: x[1], reverse=True)


def weaknesses_response() -> dict[str, object]:
    stats = sorted(profile.theme_stats(), key=weakness_score, reverse=True)
    return {
        "themes": [
            {
                "theme": s.theme,
                "label_it": label_it(s.theme),
                "errors": s.errors,
                "attempts": s.attempts,
                "success_rate": round(s.success_rate, 3),
            }
            for s in stats
            if s.theme not in META_THEMES
        ]
    }


def focus_themes(level: Level) -> list[str]:
    themes = [t for t, _ in ranked_weaknesses()[:2]]
    for default in DEFAULT_FOCUS[level.number]:
        if len(themes) >= 2:
            break
        if default not in themes:
            themes.append(default)
    return themes


def weighted_theme(rng: random.Random) -> str | None:
    """Tema per la modalità normale: metà delle volte nessun filtro, altrimenti pesato sulle debolezze."""
    ranked = ranked_weaknesses()[:8]
    if not ranked or rng.random() < 0.5:
        return None
    return rng.choices([t for t, _ in ranked], weights=[w for _, w in ranked], k=1)[0]


# --- piano giornaliero -------------------------------------------------------------
def _daily_tips(level: Level, focus: list[str], day: date) -> list[str]:
    tips = TIPS[level.number]
    idx = day.toordinal()
    chosen = [tips[cat][idx % len(tips[cat])] for cat in ("aperture", "principi", "finali")]
    focus_tip = next((THEME_TIPS_IT[t] for t in focus if t in THEME_TIPS_IT), None)
    if focus_tip:
        chosen.insert(0, focus_tip)
    return chosen


def _bot_elo_for(game_rating: float) -> int:
    return int(min(BOT_ELO_MAX, max(BOT_ELO_MIN, round((game_rating + 100) / 10) * 10)))


@dataclass(frozen=True)
class DailyPlan:
    """Parte fissa del piano del giorno, generata una volta al giorno."""

    level_name: str
    focus_themes: list[str]
    tips: list[str]
    warmup_rating: int
    focus_rating: int
    bot_elo: int


def stored_plan() -> DailyPlan:
    day = db.today()
    with db.connect() as conn:
        row = conn.execute("SELECT plan FROM daily_plans WHERE day = ?", (day,)).fetchone()
    if row:
        return DailyPlan(**json.loads(row["plan"]))
    p = profile.load()
    level = level_for(p.strength, p.target_elo)
    focus = focus_themes(level)
    plan = DailyPlan(
        level_name=level.name,
        focus_themes=focus,
        tips=_daily_tips(level, focus, date.today()),
        warmup_rating=round(p.puzzle.rating + WARMUP_OFFSET),
        focus_rating=round(p.puzzle.rating),
        bot_elo=_bot_elo_for(p.game.rating),
    )
    with db.connect() as conn:
        conn.execute("INSERT OR IGNORE INTO daily_plans(day, plan) VALUES (?, ?)", (day, json.dumps(asdict(plan))))
    return plan


def _attempts_today(mode: str) -> int:
    with db.connect() as conn:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM puzzle_attempts WHERE day = ? AND mode = ?", (db.today(), mode)
            ).fetchone()[0]
        )


def _review_target() -> tuple[int | None, bool]:
    """(partita da rivedere, già fatta?) — l'ultima partita finita non ancora analizzata."""
    with db.connect() as conn:
        pending = conn.execute(
            "SELECT id FROM games WHERE status = 'finished' AND COALESCE(analysis_status, '') != 'done' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if pending:
            return int(pending["id"]), False
        reviewed = conn.execute(
            "SELECT id FROM games WHERE analysis_status = 'done' AND substr(analyzed_at, 1, 10) = ? "
            "ORDER BY id DESC LIMIT 1",
            (db.today(),),
        ).fetchone()
    return (int(reviewed["id"]), True) if reviewed else (None, False)


def today_plan() -> dict[str, object]:
    plan = stored_plan()
    focus = plan.focus_themes
    focus_labels = ", ".join(label_it(t).lower() for t in focus)
    warmup_done = _attempts_today("warmup")
    focus_done = _attempts_today("focus")
    with db.connect() as conn:
        games_today = int(
            conn.execute(
                "SELECT COUNT(*) FROM games WHERE source = 'bot' AND status = 'finished' AND substr(finished_at, 1, 10) = ?",
                (db.today(),),
            ).fetchone()[0]
        )
    review_id, review_done = _review_target()
    review_desc = (
        "Analizza l'ultima partita e leggi le spiegazioni degli errori."
        if review_id is not None
        else "Gioca una partita: poi potrai rivederla qui."
    )
    items = [
        {
            "id": "warmup",
            "kind": "warmup",
            "title": "Riscaldamento",
            "description": f"{WARMUP_COUNT} puzzle facili (circa {plan.warmup_rating}) per entrare in ritmo.",
            "done": warmup_done >= WARMUP_COUNT,
            "params": {"mode": "warmup", "count": WARMUP_COUNT, "completed": min(warmup_done, WARMUP_COUNT), "rating": plan.warmup_rating},
        },
        {
            "id": "focus",
            "kind": "puzzles",
            "title": "Allenamento mirato",
            "description": f"{FOCUS_COUNT} puzzle sui temi più deboli: {focus_labels}.",
            "done": focus_done >= FOCUS_COUNT,
            "params": {
                "mode": "focus",
                "count": FOCUS_COUNT,
                "completed": min(focus_done, FOCUS_COUNT),
                "themes": focus,
                "rating": plan.focus_rating,
            },
        },
        {
            "id": "game",
            "kind": "game",
            "title": f"Partita contro il bot ({plan.bot_elo})",
            "description": "Una partita contro il bot un po' più forte di te: gioca con calma e applica i temi di oggi.",
            "done": games_today > 0,
            "params": {"bot_elo": plan.bot_elo, "color": "random"},
        },
        {
            "id": "review",
            "kind": "review",
            "title": "Revisione",
            "description": review_desc,
            "done": review_done,
            "params": {"game_id": review_id},
        },
    ]
    return {
        "date": db.today(),
        "level_name": plan.level_name,
        "focus_themes": focus,
        "tips": plan.tips,
        "items": items,
    }
