# Rapporto CPU del motore

Generato da `scripts/cpu_benchmark.py` il 2026-11-16 01:24.

- Macchina: arm64 · macOS 15.7 · 8 core logici · Python 3.11.3
- Motore: Stockfish 19 (`/opt/homebrew/bin/stockfish`)
- CPU% = tempo CPU (user+system) del processo Stockfish / tempo reale × 100, riferito a un core
  (100% = un core pieno; il massimo teorico è threads × 100%).

## (a) Una mossa del bot (media di 3 mosse, posizione di mediogioco)

| Profilo | Thread | Elo bot | Tempo | CPU Stockfish |
|---|---|---|---|---|
| eco | 1 | 800 | 4 ms | 75% |
| eco | 1 | 1500 | 191 ms | 99% |
| eco | 1 | 2500 | 315 ms | 100% |
| balanced | 2 | 800 | 4 ms | 142% |
| balanced | 2 | 1500 | 379 ms | 199% |
| balanced | 2 | 2500 | 630 ms | 200% |
| performance | 6 | 800 | 8 ms | 264% |
| performance | 6 | 1500 | 396 ms | 434% |
| performance | 6 | 2500 | 631 ms | 589% |

Il tempo per mossa va da 100 ms (400 Elo) a 800 ms (3190 Elo); il profilo eco lo dimezza.
Sotto 1320 Elo la ricerca è limitata anche in profondità (Skill Level 0–5), quindi termina prima.

## (b) Analisi completa di una partita di 40 mosse (80 semimosse → 81 posizioni)

Limite per posizione: profondità 16 oppure 150 ms (75 ms in eco), il primo dei due.

| Profilo | Thread | Posizioni | Tempo totale | CPU Stockfish | Tempo per posizione |
|---|---|---|---|---|---|
| eco | 1 | 81 | 6.2 s | 98% | 76 ms |
| balanced | 2 | 81 | 11.9 s | 198% | 147 ms |
| performance | 6 | 81 | 12.0 s | 593% | 148 ms |

## (c) Inattività

| Stato | CPU Stockfish |
|---|---|
| Motore avviato ma fermo (5 s di misura) | 0.0% |
| Dopo il timeout di inattività (5 s nel benchmark, 300 s di default) | processo terminato → 0% |
| Processo backend Python a riposo (2 s) | 0.0% |
