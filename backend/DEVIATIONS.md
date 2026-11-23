# Deviazioni ed estensioni rispetto a docs/ARCHITECTURE.md

Tutte le rotte, i nomi dei campi e i tipi del contratto sono implementati come da specifica.
Le voci seguenti sono comportamenti non specificati (scelte fatte) o campi **aggiuntivi** (compatibili).

## Errori HTTP
- Errori in formato FastAPI `{"detail": "<messaggio in italiano>"}`.
- `400`: mossa illegale/non valida, non è il turno dell'utente, partita già terminata, PGN o FEN non validi,
  `POST /games/{id}/analyze` su una partita ancora in corso, `POST /games/{id}/hint` su partita terminata.
- `404`: partita o puzzle inesistenti; **`GET /games/{id}/analysis` quando l'analisi non è mai stata richiesta**.
- `422`: corpo della richiesta non valido (validazione Pydantic).
- `503`: Stockfish non disponibile.

## Analisi
- `status` può valere anche `"error"` se l'analisi fallisce (si può ripetere con `POST .../analyze`).
- Durante `queued`/`running`: `moves` è `[]`, `counts` è `{}`, accuratezze e `summary_it` sono `null`.
- `classification: "book"` non viene mai prodotta (nessun libro di aperture locale).
- `counts` si riferisce al colore dell'utente e contiene le chiavi
  `best, excellent, good, inaccuracy, mistake, blunder, forced`. Campo aggiuntivo `counts_by_color: {white, black}`.
- `MoveAnalysis` ha due campi aggiuntivi: `win_loss` (perdita di win% di chi muove) e
  `explanation_source` (`"heuristic"` | `"claude"`).
- Le spiegazioni sono generate per entrambi i colori; con `ANTHROPIC_API_KEY` Claude riscrive solo i 5 errori
  (mistake/blunder) più gravi dell'utente, con fallback sempre all'euristica.

## Notazione
- I campi `*_san` (`moves_san`, `best_move_san`, `best_line_san`, `san` del suggerimento, `lines[].moves_san`)
  sono in SAN internazionale (compatibile con chess.js). La notazione italiana (C, A, T, D, R) è usata solo
  nei testi `explanation_it` / `summary_it`.

## Partite
- `GameState.bot_elo` è `null` per le partite importate.
- `POST /games/import` accetta un campo opzionale `color: "white"|"black"` (default `"white"`) che indica il
  lato dell'utente, usato per `counts`, `accuracy` e statistiche dei temi deboli.
- `POST /games` senza `bot_elo` usa `game_rating + 100`; `bot_elo` è limitato a 400–3190.
- Una mossa di pedone sull'ultima traversa senza suffisso di promozione (es. `e7e8`) promuove a Donna.
- Patta per triplice ripetizione e regola delle 50 mosse applicata automaticamente.
- `games_played` e `game_rating` contano solo le partite contro il bot (non quelle importate).

## Profilo, piano, puzzle
- `level` è un intero 1–6 (Principiante … Obiettivo raggiunto); la soglia di «Obiettivo raggiunto» è `target_elo`.
- Campi aggiuntivi in `GET /profile`: `strength` (forza combinata usata per livello e progresso) e `initial_rating`.
- Forza usata per livello e `progress_pct`: 60% `game_rating` + 40% `puzzle_rating`;
  `progress_pct` = avanzamento da `initial_rating` a `target_elo`.
- `PUT /profile` con `initial_rating` reimposta entrambi i rating a quel valore (RD 350).
- `rating_history`: un punto per giorno (ultimo valore della giornata).
- Piano: `params` contiene `mode`, `count`, `completed`, `rating`, `themes` (puzzle), `bot_elo`, `color` (partita),
  `game_id` (revisione, `null` se non c'è nessuna partita). Temi, Elo del bot e consigli sono fissati per la giornata.
- Puzzle: il rating cambia solo al primo tentativo di ogni puzzle (`delta = 0` sui successivi);
  risolto con aiuti (`hints_used > 0`) conta come mezzo punto.
- `GET /stats/weaknesses`: `errors` = puzzle sbagliati + errori in partita; `attempts` = puzzle tentati + errori in partita.
  Esclusi i temi «meta» (lunghezza, fase, origine del puzzle).
