"""Spiegazioni in italiano: euristiche locali (sempre) + arricchimento opzionale con Claude.

Le euristiche usano la posizione, la mossa giocata, la linea migliore del motore (`best_pv`) e la
confutazione dell'avversario dopo la mossa giocata (`reply_pv`).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import chess

from . import config, llm
from .engine import MATE_SCORE
from .themes import META_THEMES, THEME_TIPS_IT, labels_it

log = logging.getLogger(__name__)

PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
PIECE_NAMES = {
    chess.PAWN: "il Pedone",
    chess.KNIGHT: "il Cavallo",
    chess.BISHOP: "l'Alfiere",
    chess.ROOK: "la Torre",
    chess.QUEEN: "la Donna",
    chess.KING: "il Re",
}
PIECE_SHORT = {
    chess.PAWN: "Pedone",
    chess.KNIGHT: "Cavallo",
    chess.BISHOP: "Alfiere",
    chess.ROOK: "Torre",
    chess.QUEEN: "Donna",
    chess.KING: "Re",
}
FEMININE = frozenset({chess.ROOK, chess.QUEEN})
CENTER = frozenset({chess.D4, chess.E4, chess.D5, chess.E5})
CLASS_PREFIX = {"inaccuracy": ("Imprecisione", "?!"), "mistake": ("Errore", "?"), "blunder": ("Errore grave", "??")}
MATE_THRESHOLD = MATE_SCORE - 1000
LINE_PLIES = 4

_SAN_IT = str.maketrans("NBRQK", "CATDR")


# --- formattazione -----------------------------------------------------------
def san_it(san: str) -> str:
    """Notazione algebrica italiana (C=Cavallo, A=Alfiere, T=Torre, D=Donna, R=Re)."""
    return san.translate(_SAN_IT)


def numbered_san(board: chess.Board, move: chess.Move) -> str:
    sep = "." if board.turn == chess.WHITE else "..."
    return f"{board.fullmove_number}{sep}{san_it(board.san(move))}"


def line_san(board: chess.Board, moves: Iterable[chess.Move]) -> list[str]:
    """SAN (internazionale) di una sequenza di mosse a partire da `board`."""
    b = board.copy(stack=False)
    out: list[str] = []
    for move in moves:
        if move not in b.legal_moves:
            break
        out.append(b.san(move))
        b.push(move)
    return out


def format_line(board: chess.Board, moves: Sequence[chess.Move], max_plies: int = 6) -> str:
    """Linea numerata in notazione italiana, es. «24.Axd8 Txd8 25.Df3»."""
    b = board.copy(stack=False)
    parts: list[str] = []
    for i, move in enumerate(moves[:max_plies]):
        if move not in b.legal_moves:
            break
        san = san_it(b.san(move))
        if b.turn == chess.WHITE:
            parts.append(f"{b.fullmove_number}.{san}")
        elif i == 0:
            parts.append(f"{b.fullmove_number}...{san}")
        else:
            parts.append(san)
        b.push(move)
    return " ".join(parts)


def mate_distance(cp: int) -> int | None:
    """Mosse al matto se `cp` codifica un matto (±(10000 − n)), altrimenti None."""
    if abs(cp) >= MATE_THRESHOLD:
        return MATE_SCORE - abs(cp)
    return None


def format_eval(cp: int) -> str:
    n = mate_distance(cp)
    if n is not None:
        side = "Bianco" if cp > 0 else "Nero"
        return f"matto in {n} per il {side}" if n > 0 else f"scacco matto del {side}"
    return f"{cp / 100:+.1f}".replace("-", "−")


def eval_phrase(cp: int) -> str:
    """Giudizio verbale della posizione (valutazione dal punto di vista del Bianco)."""
    n = mate_distance(cp)
    side = "Il Bianco" if cp > 0 else "Il Nero"
    if n is not None:
        return f"{side} ha il matto in {n}" if n > 0 else f"{side} ha dato scacco matto"
    a = abs(cp)
    if a < 50:
        verdict = "Posizione equilibrata"
    elif a < 150:
        verdict = f"{side} sta leggermente meglio"
    elif a < 300:
        verdict = f"{side} è in vantaggio"
    else:
        verdict = f"{side} è in netto vantaggio"
    return f"{verdict} ({format_eval(cp)})"


def mate_theme(n: int) -> str:
    return f"mateIn{n}" if 1 <= n <= 5 else "mate"


# --- motivi tattici ----------------------------------------------------------
def material(board: chess.Board, color: chess.Color) -> int:
    return sum(PIECE_VALUES[p.piece_type] for p in board.piece_map().values() if p.color == color)


def material_balance(board: chess.Board, color: chess.Color) -> int:
    return material(board, color) - material(board, not color)


def material_swing(board: chess.Board, line: Sequence[chess.Move], color: chess.Color, plies: int = LINE_PLIES) -> int:
    """Variazione del bilancio materiale di `color` lungo i primi `plies` semimosse di `line`."""
    b = board.copy(stack=False)
    start = material_balance(b, color)
    for move in line[:plies]:
        if move not in b.legal_moves:
            break
        b.push(move)
    return material_balance(b, color) - start


def captured_piece(board: chess.Board, move: chess.Move) -> chess.Piece | None:
    if board.is_en_passant(move):
        return chess.Piece(chess.PAWN, not board.turn)
    return board.piece_at(move.to_square)


def forked_targets(board: chess.Board, square: chess.Square) -> list[chess.PieceType]:
    """Pezzi avversari attaccati dal pezzo in `square` che costituiscono bersagli reali (forchetta se ≥2)."""
    attacker = board.piece_at(square)
    if attacker is None:
        return []
    targets: list[chess.PieceType] = []
    for sq in board.attacks(square):
        victim = board.piece_at(sq)
        if victim is None or victim.color == attacker.color:
            continue
        if victim.piece_type == chess.KING:
            targets.append(chess.KING)
        elif PIECE_VALUES[victim.piece_type] > PIECE_VALUES[attacker.piece_type] or (
            victim.piece_type != chess.PAWN and not board.is_attacked_by(victim.color, sq)
        ):
            targets.append(victim.piece_type)
    return targets


def new_pins(before: chess.Board, after: chess.Board, victim: chess.Color) -> list[chess.PieceType]:
    """Pezzi (non pedoni) di `victim` inchiodati al Re in `after` ma non in `before`."""
    pinned: list[chess.PieceType] = []
    for sq, piece in after.piece_map().items():
        if piece.color != victim or piece.piece_type in (chess.PAWN, chess.KING):
            continue
        if after.is_pinned(victim, sq) and not (before.piece_at(sq) == piece and before.is_pinned(victim, sq)):
            pinned.append(piece.piece_type)
    return pinned


def skewered_piece(board: chess.Board, move: chess.Move) -> chess.PieceType | None:
    """Infilata: dopo `move` (già giocata su `board`) un pezzo a lunga gittata dà scacco e dietro il Re c'è un pezzo."""
    attacker = board.piece_at(move.to_square)
    if attacker is None or attacker.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN) or not board.is_check():
        return None
    king_sq = board.king(board.turn)
    if king_sq is None:
        return None
    df = chess.square_file(king_sq) - chess.square_file(move.to_square)
    dr = chess.square_rank(king_sq) - chess.square_rank(move.to_square)
    step_f, step_r = (df > 0) - (df < 0), (dr > 0) - (dr < 0)
    f, r = chess.square_file(king_sq) + step_f, chess.square_rank(king_sq) + step_r
    while 0 <= f < 8 and 0 <= r < 8:
        piece = board.piece_at(chess.square(f, r))
        if piece is not None:
            if piece.color == board.turn and PIECE_VALUES[piece.piece_type] >= 3:
                return piece.piece_type
            return None
        f, r = f + step_f, r + step_r
    return None


def pawn_weaknesses(board: chess.Board, color: chess.Color) -> int:
    """Numero di pedoni doppiati + isolati di `color`."""
    files = [chess.square_file(sq) for sq in board.pieces(chess.PAWN, color)]
    count = 0
    for f in set(files):
        n = files.count(f)
        if n > 1:
            count += n - 1
        if (f - 1) not in files and (f + 1) not in files:
            count += n
    return count


def is_endgame(board: chess.Board) -> bool:
    non_pawn = sum(
        PIECE_VALUES[p.piece_type] for p in board.piece_map().values() if p.piece_type not in (chess.PAWN, chess.KING)
    )
    return non_pawn <= 13


def weakens_king(board: chess.Board, move: chess.Move) -> bool:
    """Mossa di pedone dello scudo davanti al Re arroccato, o Re che si muove al centro perdendo l'arrocco."""
    piece = board.piece_at(move.from_square)
    king_sq = board.king(board.turn)
    if piece is None or king_sq is None or is_endgame(board):
        return False
    if piece.piece_type == chess.KING:
        return not board.is_castling(move) and board.has_castling_rights(board.turn)
    if piece.piece_type != chess.PAWN:
        return False
    king_file = chess.square_file(king_sq)
    home_rank = 0 if board.turn == chess.WHITE else 7
    castled_side = king_file >= 6 or king_file <= 2
    return (
        castled_side
        and chess.square_rank(king_sq) == home_rank
        and abs(chess.square_file(move.from_square) - king_file) <= 1
    )


def describe_move(board: chess.Board, move: chess.Move) -> tuple[str, list[str]]:
    """Breve descrizione tattica di una mossa (usata per suggerimenti e analisi di posizione)."""
    notes: list[str] = []
    themes: list[str] = []
    victim = captured_piece(board, move) if board.is_capture(move) else None
    after = board.copy(stack=False)
    after.push(move)
    if after.is_checkmate():
        return "dà scacco matto", ["mateIn1"]
    if victim is not None:
        defended = board.is_attacked_by(victim.color, move.to_square)
        suffix = "" if defended else (" indifesa" if victim.piece_type in FEMININE else " indifeso")
        notes.append(f"cattura {PIECE_NAMES[victim.piece_type]}{suffix}")
        if not defended:
            themes.append("hangingPiece")
    if move.promotion:
        notes.append(f"promuove a {PIECE_SHORT[move.promotion]}")
        themes.append("promotion")
    if after.is_check():
        notes.append("dà scacco")
    targets = forked_targets(after, move.to_square)
    if len(targets) >= 2:
        notes.append("attacca insieme " + " e ".join(PIECE_SHORT[t] for t in targets[:3]) + " (forchetta)")
        themes.append("fork")
    pins = new_pins(board, after, not board.turn)
    if pins:
        notes.append(f"inchioda {PIECE_NAMES[pins[0]]} dell'avversario")
        themes.append("pin")
    skewer = skewered_piece(after, move)
    if skewer is not None:
        notes.append(f"infila il Re e {PIECE_NAMES[skewer]}")
        themes.append("skewer")
    if not notes:
        notes.extend(_quiet_notes(board, move))
    return ", ".join(notes), themes


def _quiet_notes(board: chess.Board, move: chess.Move) -> list[str]:
    """Descrizione di una mossa senza motivi tattici: arrocco, sviluppo, centro, minacce."""
    piece = board.piece_at(move.from_square)
    if piece is None:
        return []
    if board.is_castling(move):
        return ["arrocca e mette al sicuro il Re"]
    home_rank = 0 if piece.color == chess.WHITE else 7
    if piece.piece_type in (chess.KNIGHT, chess.BISHOP) and chess.square_rank(move.from_square) == home_rank:
        return ["sviluppa un pezzo"]
    if piece.piece_type == chess.PAWN and move.to_square in CENTER:
        return ["occupa il centro"]
    after = board.copy(stack=False)
    after.push(move)
    for sq in after.attacks(move.to_square):
        victim = after.piece_at(sq)
        if (
            victim is not None
            and victim.color != piece.color
            and victim.piece_type != chess.KING
            and (PIECE_VALUES[victim.piece_type] > PIECE_VALUES[piece.piece_type] or not after.is_attacked_by(victim.color, sq))
        ):
            return [f"minaccia {PIECE_NAMES[victim.piece_type]}"]
    return []


# --- spiegazione degli errori nelle partite ------------------------------------
@dataclass
class MoveContext:
    board: chess.Board  # posizione prima della mossa
    move: chess.Move
    best_pv: list[chess.Move]
    reply_pv: list[chess.Move]
    eval_before: int  # punto di vista del Bianco
    eval_after: int
    classification: str
    reasons: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)

    @property
    def mover(self) -> chess.Color:
        return self.board.turn

    def pov(self, cp: int) -> int:
        return cp if self.mover == chess.WHITE else -cp

    def add(self, reason: str, theme: str | None = None) -> None:
        self.reasons.append(reason)
        if theme and theme not in self.themes:
            self.themes.append(theme)


def _mate_reasons(ctx: MoveContext, after: chess.Board) -> bool:
    before, now = ctx.pov(ctx.eval_before), ctx.pov(ctx.eval_after)
    n_after = mate_distance(now)
    if now < 0 and n_after is not None:
        ctx.add(f"permette all'avversario il matto in {n_after}: {format_line(after, ctx.reply_pv)}", mate_theme(n_after))
        return True
    n_before = mate_distance(before)
    if before > 0 and n_before is not None and not (now > 0 and n_after is not None) and ctx.best_pv:
        ctx.add(f"lascia sfuggire il matto in {n_before} con {format_line(ctx.board, ctx.best_pv)}", mate_theme(n_before))
        return True
    return False


def _material_reasons(ctx: MoveContext, after: chess.Board) -> None:
    if not ctx.reply_pv or ctx.reply_pv[0] not in after.legal_moves:
        return
    reply = ctx.reply_pv[0]
    swing = material_swing(ctx.board, [ctx.move, *ctx.reply_pv], ctx.mover, plies=LINE_PLIES + 1)
    refutation = format_line(after, ctx.reply_pv, max_plies=3)
    victim = captured_piece(after, reply) if after.is_capture(reply) else None

    moved = ctx.board.piece_at(ctx.move.from_square)
    taken = captured_piece(ctx.board, ctx.move) if ctx.board.is_capture(ctx.move) else None
    if (
        moved is not None
        and taken is not None
        and reply.to_square == ctx.move.to_square
        and PIECE_VALUES[moved.piece_type] > PIECE_VALUES[taken.piece_type]
        and swing < 0
    ):
        ctx.add(
            f"è uno scambio sfavorevole: dai {PIECE_NAMES[moved.piece_type]} per {PIECE_NAMES[taken.piece_type]} ({refutation})",
            "badExchange",
        )
        return

    reply_board = after.copy(stack=False)
    reply_board.push(reply)
    fork = forked_targets(reply_board, reply.to_square)
    if len(fork) >= 2:
        names = " e ".join(PIECE_SHORT[t] for t in fork[:3])
        ctx.add(f"consente la forchetta {refutation}, che attacca {names}", "fork")
    pins = new_pins(after, reply_board, ctx.mover)
    if pins:
        ctx.add(f"consente l'inchiodatura {refutation} contro {PIECE_NAMES[pins[0]]}", "pin")
    skewer = skewered_piece(reply_board, reply)
    if skewer is not None:
        ctx.add(f"consente l'infilata {refutation}, che vince {PIECE_NAMES[skewer]}", "skewer")

    if victim is not None and swing <= -2:
        piece = PIECE_NAMES[victim.piece_type]
        where = "porta" if reply.to_square == ctx.move.to_square else "lascia"
        ctx.add(f"{where} {piece} in presa: dopo {refutation} perdi materiale", "hangingPiece")
    elif swing <= -2 and not ctx.reasons:
        ctx.add(f"dopo {refutation} perdi materiale (circa {-swing} punti)")


def _best_move_reason(ctx: MoveContext) -> str:
    """Perché la mossa migliore era migliore (tema aggiunto ai temi dell'errore)."""
    if not ctx.best_pv:
        return ""
    best = ctx.best_pv[0]
    if best == ctx.move or best not in ctx.board.legal_moves:
        return ""
    desc, themes = describe_move(ctx.board, best)
    gain = material_swing(ctx.board, ctx.best_pv, ctx.mover)
    if ctx.board.is_capture(best) and "missedCapture" not in ctx.themes and gain >= 2:
        themes = [*themes, "missedCapture"]
    for t in themes:
        if t not in ctx.themes:
            ctx.themes.append(t)
    if gain >= 2 and "cattura" not in desc:
        desc = f"{desc} e vince materiale" if desc else "vince materiale"
    return f", che {desc}" if desc else ""


def _positional_reasons(ctx: MoveContext, after: chess.Board) -> None:
    if weakens_king(ctx.board, ctx.move):
        ctx.add("indebolisce la protezione del tuo Re", "exposedKing")
    if pawn_weaknesses(after, ctx.mover) > pawn_weaknesses(ctx.board, ctx.mover):
        ctx.add("peggiora la struttura pedonale (pedoni doppiati o isolati)", "pawnStructure")


def _endgame_reason(ctx: MoveContext, win_before: float, win_after: float) -> None:
    if is_endgame(ctx.board) and win_before >= 40 and win_after <= 20:
        state = "vinta" if win_before >= 70 else "pari"
        ctx.add(f"nel finale trasforma una posizione {state} in una persa", "endgame")


def explain_move(ctx: MoveContext, win_before: float, win_after: float) -> tuple[str, list[str]]:
    """Testo italiano e temi per una mossa analizzata. `win_*` = probabilità di vittoria (0–100) di chi muove."""
    played = numbered_san(ctx.board, ctx.move)
    best_san = numbered_san(ctx.board, ctx.best_pv[0]) if ctx.best_pv and ctx.best_pv[0] in ctx.board.legal_moves else None
    after = ctx.board.copy(stack=False)
    after.push(ctx.move)

    if ctx.classification == "forced":
        return f"{played}: mossa forzata, era l'unica mossa legale.", []
    if ctx.classification == "best":
        desc, themes = describe_move(ctx.board, ctx.move)
        return (f"{played} è la mossa migliore: {desc}." if desc else f"{played} è la mossa migliore."), themes
    if ctx.classification in ("excellent", "good"):
        quality = "Ottima mossa" if ctx.classification == "excellent" else "Buona mossa"
        hint = f" Il motore preferiva {best_san} ({format_line(ctx.board, ctx.best_pv, 4)})." if best_san else ""
        return f"{quality}: {played}.{hint}", []

    label, mark = CLASS_PREFIX[ctx.classification]
    if not _mate_reasons(ctx, after):
        _material_reasons(ctx, after)
        _endgame_reason(ctx, win_before, win_after)
        if not ctx.reasons:
            _positional_reasons(ctx, after)
    best_reason = _best_move_reason(ctx)

    text = f"{label}: {played}{mark}"
    if ctx.reasons:
        text += " " + "; inoltre ".join(ctx.reasons[:2]) + "."
    else:
        text += " peggiora la tua posizione senza un motivo tattico evidente."
    if best_san:
        text += f" Era meglio {best_san}{best_reason}: {format_line(ctx.board, ctx.best_pv, 5)}."
    text += f" Valutazione: da {format_eval(ctx.eval_before)} a {format_eval(ctx.eval_after)}."
    return text, ctx.themes


# --- spiegazioni di posizione, suggerimenti, puzzle, riepiloghi ----------------
def explain_position(board: chess.Board, eval_cp: int, pv: list[chess.Move]) -> str:
    if board.is_checkmate():
        return "Scacco matto: la partita è finita."
    if board.is_stalemate():
        return "Stallo: la partita è patta."
    text = eval_phrase(eval_cp) + "."
    if pv and pv[0] in board.legal_moves:
        desc, _ = describe_move(board, pv[0])
        what = f", che {desc}" if desc else ""
        text += f" La mossa migliore è {numbered_san(board, pv[0])}{what}. Linea principale: {format_line(board, pv)}."
    return text


def explain_hint(board: chess.Board, move: chess.Move) -> str:
    desc, themes = describe_move(board, move)
    tips = [THEME_TIPS_IT[t] for t in themes if t in THEME_TIPS_IT]
    text = f"Considera {san_it(board.san(move))}: {desc}." if desc else f"Considera {san_it(board.san(move))}."
    if tips:
        text += " " + tips[0]
    return text


def explain_puzzle(fen: str, moves: list[str], themes: list[str], success: bool) -> str:
    board = chess.Board(fen)
    board.push_uci(moves[0])
    solution = format_line(board, [chess.Move.from_uci(m) for m in moves[1:]], max_plies=len(moves))
    tactical = [t for t in themes if t not in META_THEMES]
    head = "Risolto!" if success else "Non risolto."
    text = f"{head} Soluzione: {solution}."
    if tactical:
        text += " Temi: " + ", ".join(labels_it(tactical)).lower() + "."
    tip = next((THEME_TIPS_IT[t] for t in tactical if t in THEME_TIPS_IT), None)
    if tip:
        text += " " + tip
    return text


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def summarize_game(
    color: chess.Color,
    accuracy: float | None,
    counts: dict[str, int],
    worst: tuple[str, str] | None,
    themes: list[str],
) -> str:
    """Riepilogo della partita dal punto di vista dell'utente. `worst` = (mossa numerata, classificazione)."""
    side = "Bianco" if color == chess.WHITE else "Nero"
    parts = []
    if accuracy is not None:
        parts.append(f"Precisione con il {side}: {accuracy:.0f}%.")
    b, m, i = counts.get("blunder", 0), counts.get("mistake", 0), counts.get("inaccuracy", 0)
    if b + m + i == 0:
        parts.append("Nessun errore significativo: ottima partita!")
    else:
        parts.append(
            f"Hai commesso {_plural(b, 'errore grave', 'errori gravi')}, {_plural(m, 'errore', 'errori')} "
            f"e {_plural(i, 'imprecisione', 'imprecisioni')}."
        )
    if worst is not None:
        parts.append(f"La mossa più costosa è stata {worst[0]} ({CLASS_PREFIX[worst[1]][0].lower()}).")
    if themes:
        parts.append("Temi da ripassare: " + ", ".join(labels_it(themes[:3])).lower() + ".")
    return " ".join(parts)


# --- arricchimento con Claude (opzionale) --------------------------------------
@dataclass(frozen=True)
class ClaudeRequest:
    fen_before: str
    played_san: str
    best_line_san: list[str]
    eval_before: int
    eval_after: int
    classification: str
    heuristic: str


def claude_enabled() -> bool:
    return llm.enabled()


def enrich_with_claude(req: ClaudeRequest) -> str | None:
    """Spiegazione didattica generata da Claude; None se non configurato o in caso di errore (si usa l'euristica)."""
    if not claude_enabled():
        return None
    try:
        client = llm.client(timeout=30.0, max_retries=1)
        prompt = (
            "Sei un istruttore di scacchi. Spiega in italiano, in 2-3 frasi semplici per un giocatore di club, "
            "perché la mossa giocata è un errore e cosa insegna la mossa migliore. Usa la notazione italiana "
            "(C, A, T, D, R). Non inventare varianti diverse da quelle fornite.\n\n"
            f"FEN prima della mossa: {req.fen_before}\n"
            f"Mossa giocata: {req.played_san} (classificazione: {req.classification})\n"
            f"Linea migliore del motore: {' '.join(req.best_line_san)}\n"
            f"Valutazione prima: {format_eval(req.eval_before)}, dopo: {format_eval(req.eval_after)} (punto di vista del Bianco)\n"
            f"Analisi automatica: {req.heuristic}"
        )
        response = client.beta.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=1024,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": prompt}],
        )
        if response.stop_reason == "refusal":
            return None
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        return text or None
    except Exception as exc:  # qualsiasi errore (rete, quota, SDK) → fallback all'euristica
        log.warning("Arricchimento Claude non riuscito: %s", exc)
        return None
