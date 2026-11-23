# LearnAI — Allenatore locale: scacchi (obiettivo 2000 Elo), CFA e GMAT

App locale (nessun servizio cloud obbligatorio) per allenarsi a scacchi con un motore personale.
Lingua dell'interfaccia e delle spiegazioni: **italiano**.

## Stack

| Parte | Tecnologia |
|---|---|
| Motore | **Stockfish** (installato con `brew install stockfish`), pilotato via UCI con `python-chess` |
| Backend | Python 3.11, **FastAPI** + uvicorn, SQLite (SQLAlchemy o sqlite3), cartella `backend/` |
| Frontend | **Vite + React + TypeScript**, `react-chessboard` + `chess.js`, grafici con `recharts`, cartella `frontend/` |
| Puzzle | Database puzzle Lichess (CC0) `lichess_db_puzzle.csv.zst` importato in SQLite (sottoinsieme filtrato) |
| Spiegazioni | Regole euristiche locali in italiano (sempre) + **opzionale** Claude API se `ANTHROPIC_API_KEY` è impostata |

Backend su `http://localhost:8000`, frontend su `http://localhost:5173` (proxy Vite `/api` → 8000).
Dati utente in `backend/data/chessai.db`. Puzzle in `backend/data/puzzles.db`.
Percorsi configurabili via variabili d'ambiente (`CHESSAI_DATA_DIR`, `CHESSAI_PUZZLES_DB`, `CHESSAI_STATIC_DIR`, `STOCKFISH_PATH`, `CHESSAI_PORT`: vedi `backend/app/config.py`). L'app per Mac (`macapp/`) li usa per tenere i dati in `~/Library/Application Support/ChessAI` e puzzle, Stockfish e interfaccia dentro il bundle.

## Consumo CPU del motore (requisito chiave)

- Una sola istanza Stockfish condivisa, avviata a richiesta, chiusa dopo 5 min di inattività (0% CPU da fermo).
- Impostazioni di default: `Threads=2`, `Hash=128` MB, modificabili via API/Impostazioni.
- Gioco contro il bot: `movetime` 100–800 ms per mossa, `UCI_LimitStrength` + `UCI_Elo` (min 1320).
  Sotto 1320 Elo usare `Skill Level` 0–5 + profondità ridotta + scelta casuale tra le mosse candidate (MultiPV).
- Analisi partita: profondità ~16 o 150 ms per posizione, in background, con progresso.
- Profilo "Risparmio" (1 thread, 64 MB, tempi dimezzati) e "Prestazioni" (6 thread, 256 MB).

## Modello dell'allievo

- Due rating Glicko-2: `puzzle_rating` e `game_rating` (partenza: stima iniziale dichiarata dall'utente, default 1200, RD 350).
- Obiettivo: `target_elo` (default 2000). Livelli: Principiante <1000, Base 1000–1300, Intermedio 1300–1600, Avanzato 1600–1800, Esperto 1800–2000, Obiettivo raggiunto ≥2000.
- Debolezze: conteggio per tema (fork, pin, hangingPiece, mateIn2, endgame, ...) dei puzzle sbagliati e degli errori nelle partite analizzate. Usate per pesare i temi dei puzzle successivi.

## Piano progressivo (`/api/plan/today`)

Sessione giornaliera generata dal modello:
1. Riscaldamento: 5 puzzle facili (rating −200).
2. Allenamento mirato: 10 puzzle sui 2 temi più deboli (rating ±50).
3. Partita contro il bot a `game_rating + 100` (in salita progressiva).
4. Revisione: analisi dell'ultima partita non ancora rivista.
Più consigli testuali per livello (aperture, principi, finali) in italiano.

## Contratto API (base `/api`, JSON)

### Profilo & piano
- `GET /profile` → `{puzzle_rating, puzzle_rd, game_rating, game_rd, target_elo, level, level_name, progress_pct, puzzles_solved, puzzles_failed, games_played, rating_history: [{date, puzzle_rating, game_rating}]}`
- `PUT /profile` body `{target_elo?, initial_rating?}` → profilo
- `GET /plan/today` → `{date, level_name, focus_themes: [string], tips: [string], items: [{id, kind: "warmup"|"puzzles"|"game"|"review", title, description, done: bool, params: {...}}]}`
- `GET /stats/weaknesses` → `{themes: [{theme, label_it, errors, attempts, success_rate}]}`

### Puzzle
- `GET /puzzles/next?theme=<opt>&mode=<warmup|focus|normal>` → `{id, fen, moves: [uci...], rating, themes: [string], themes_it: [string]}`
  - `fen` è la posizione PRIMA della mossa dell'avversario; `moves[0]` è la mossa dell'avversario da animare, poi l'utente deve trovare `moves[1]`, l'app risponde `moves[2]`, ecc. (formato Lichess).
- `POST /puzzles/{id}/attempt` body `{success: bool, time_ms: int, hints_used: int}` → `{puzzle_rating, delta, explanation_it}`
- `GET /puzzles/themes` → `[{theme, label_it, count}]`

### Partite contro il bot
- `POST /games` body `{bot_elo?: int, color: "white"|"black"|"random"}` → `GameState`
- `GET /games/{id}` → `GameState`
- `POST /games/{id}/move` body `{uci}` → `GameState` (include la risposta del bot già giocata; 400 se illegale)
- `POST /games/{id}/resign` → `GameState`
- `POST /games/{id}/hint` → `{uci, san, explanation_it}`
- `GET /games` → `[{id, created_at, bot_elo, color, result, status, analyzed: bool, accuracy?}]`
- `POST /games/import` body `{pgn}` → `{id}` (importa una partita giocata altrove per analizzarla)
- `GameState` = `{id, fen, pgn, moves_san: [string], moves_uci: [string], color, bot_elo, status: "active"|"finished", result: "1-0"|"0-1"|"1/2-1/2"|null, termination: string|null, last_bot_move: uci|null}`

### Analisi & spiegazione errori
- `POST /games/{id}/analyze` → `{status: "queued"|"running"|"done", progress: 0..1}`
- `GET /games/{id}/analysis` → `{status, progress, accuracy_white, accuracy_black, summary_it, counts: {blunder, mistake, inaccuracy, ...}, moves: [MoveAnalysis]}`
- `MoveAnalysis` = `{ply, color, san, uci, fen_before, fen_after, eval_before, eval_after, best_move_uci, best_move_san, best_line_san: [string], cp_loss, classification: "best"|"excellent"|"good"|"inaccuracy"|"mistake"|"blunder"|"book"|"forced", explanation_it, themes: [string]}`
  - `eval_*` in centipedoni dal punto di vista del Bianco; i matti come ±10000 (meno la distanza).
  - Soglie (perdita di win% stile Lichess): inaccuracy ≥10%, mistake ≥20%, blunder ≥30%.
- `POST /analysis/position` body `{fen, multipv?: 1..3}` → `{eval, lines: [{eval, moves_san, moves_uci}], explanation_it}`

### Stato del server
- `GET /health` → `{status: "ok", version, puzzles: "lichess"|"fallback", engine_available, frontend: bool}` (usato dall'app per Mac per sapere quando il server è pronto)
- Se esiste la build del frontend (`frontend/dist` o `CHESSAI_STATIC_DIR`) il backend la serve su `/`, con fallback a `index.html` per le rotte client (`/tattica`, `/analisi/3`, ...); le rotte `/api` inesistenti restano 404.

### Motore
- `GET /engine/status` → `{available, path, version, running, threads, hash_mb, profile, cpu_count}`
- `PUT /engine/settings` body `{profile?: "eco"|"balanced"|"performance", threads?, hash_mb?}` → status

### Studio (CFA I-III, GMAT)
Moduli: `syllabus.py` (esami, argomenti, pesi approssimativi), `study.py` (banca domande, generazione con Claude, rating per esame), `llm.py` (chiave API: env `ANTHROPIC_API_KEY`, poi impostazione salvata).
Contenuti integrati in `backend/app/resources/study/` (`study_content.py`): `<esame>.json` (percorso e domande) più pacchetti `<esame>.<nome>.json` uniti per argomento; la teoria approfondita per CFA I-III sta in `<esame>.theory-<argomento>.json` (sezioni, formule, errori tipici; i paragrafi che iniziano con «Esempio» e «Trappola» sono evidenziati nella pagina). Dopo modifiche ai contenuti: `scripts/annotate_terms.py`, poi riavviare il backend (il caricamento è in cache).
- `GET /study/exams` → `{claude_enabled, exams: [{id, label, short, description, rating, rd, target_rating, progress_pct, answered, accuracy, bank_total, bank_unseen}]}`
- `GET /study/exams/{exam}` → riepilogo + `topics: [{id, label, weight_pct, attempts, errors, accuracy, weakness}]`
- `GET /study/exams/{exam}/next?topic=` → `{id, exam, topic, topic_label, difficulty, vignette, stem, choices}` (senza risposta né spiegazione). 503 se la banca è vuota e la generazione non è possibile.
- `POST /study/questions/{id}/answer` body `{choice, time_ms}` → `{correct, answer, explanation, rated, rating_before, rating_after, rating_delta}` (rating aggiornato solo alla prima risposta)
- `POST /study/questions/{id}/flag` → esclude la domanda e annulla il suo effetto sul rating
- `GET /settings/claude` → `{enabled, source: "env"|"settings"|null, model}`; `PUT /settings/claude` body `{api_key}` (vuota = rimuovi). La chiave non viene mai restituita.

Generazione: `client.beta.messages.stream` con output strutturato JSON, `fallbacks: "default"`, effort `medium`; le opzioni vengono validate e mescolate lato server (tranne Data Sufficiency, con opzioni canoniche). Difficoltà 1-5 → rating 1100-1900, RD 150 (difficoltà non calibrata). Nei test `CHESSAI_STUDY_PREFETCH=0` disattiva la pre-generazione in background.

## Spiegazioni degli errori (italiano)

Il modulo `backend/app/explain.py` produce per ogni errore un testo come:
> «Errore grave: 23...Cd4?? lascia la Donna in presa: dopo 24.Axd8 perdi materiale. Era meglio 23...Tfd8, che difende...»

Euristiche minime: pezzo lasciato in presa, matto mancato/subito, forchetta/inchiodatura persa (dal tema della best line),
cattura migliore ignorata, peggioramento della struttura, re esposto, scambio sfavorevole, finale perso.
Se `ANTHROPIC_API_KEY` è presente, arricchire con Claude (modello `claude-opus-5-5`) passando FEN, mossa giocata, best line e valutazioni; fallback sempre all'euristica.
