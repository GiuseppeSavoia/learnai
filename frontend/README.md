# ChessAI — Frontend

Interfaccia web (Vite + React + TypeScript) dell'allenatore di scacchi locale.
Scacchiera con `react-chessboard` + `chess.js`, grafici con `recharts`, routing con `react-router`.

## Avvio

```bash
npm install
npm run dev        # http://localhost:5173, proxy /api → http://localhost:8000 (backend FastAPI)
npm run dev:mock   # stessa UI con un backend finto in memoria (VITE_MOCK=1), non serve il backend
npm run build      # controllo dei tipi + build di produzione in dist/
```

## Pagine

| Percorso | Pagina |
|---|---|
| `/` | **Il mio percorso**: rating puzzle/partite, livello, progresso verso l'obiettivo, storico, piano di oggi, punti deboli, consigli |
| `/tattica` | **Tattica**: puzzle (filtri `?mode=warmup|focus|normal&theme=...`), suggerimenti, serie di risposte esatte |
| `/gioca`, `/gioca/:id` | **Partita contro il motore**: Elo 600–2800, colore, suggerimento, abbandono |
| `/analisi`, `/analisi/:id` | **Revisione**: elenco partite, import PGN, analisi con avanzamento, grafico di valutazione, navigazione con ← → Home End, "Prossimo errore" |
| `/impostazioni` | Profilo del motore (Risparmio / Bilanciato / Prestazioni), stato di Stockfish, Elo obiettivo e rating iniziale |

## Struttura

- `src/api/client.ts` — tipi e chiamate fetch tipizzate secondo il contratto in `docs/ARCHITECTURE.md`
- `src/api/mock.ts` — backend finto per lo sviluppo (attivo solo con `VITE_MOCK=1`)
- `src/components/` — `Board` (click o trascinamento, mosse legali, promozione, ultima mossa), `EvalBar`, `EvalGraph`, `MoveList`, `RatingChart`, `Layout`
- `src/pages/` — una pagina per sezione
- `src/lib/` — utilità scacchistiche (UCI, valutazioni, classificazioni) e link del piano

Tema scuro predefinito, tema chiaro dal pulsante in basso nella barra laterale.
