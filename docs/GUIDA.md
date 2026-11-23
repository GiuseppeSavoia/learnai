# LearnAI — il tuo allenatore personale (scacchi, CFA, GMAT)

LearnAI è un'applicazione che gira sul tuo Mac e usa un unico metodo adattivo (rating Glicko,
punti deboli per argomento, spiegazione di ogni errore) per tre materie:

- **Studio CFA (Livelli I, II, III) e GMAT Focus** — domande a risposta multipla generate da
  **Claude** sugli argomenti del programma, calibrate sul tuo rating e concentrate sui tuoi punti
  deboli, con spiegazione in italiano (testo delle domande in inglese, come all'esame).
  Vedi [Studio CFA e GMAT](#studio-cfa-e-gmat).
- **Scacchi** — verso i **2000 Elo**. Usa il motore **Stockfish** come avversario e come "maestro" che rivede le tue
partite, più un archivio di decine di migliaia di **puzzle tattici di Lichess**.
Tutta l'interfaccia e tutte le spiegazioni sono in italiano.

Cosa puoi fare negli scacchi:

- **Il mio percorso** — i tuoi rating (puzzle e partite), il livello, quanto manca all'obiettivo,
  il piano di allenamento di oggi, i tuoi punti deboli e qualche consiglio.
- **Tattica** — puzzle adatti al tuo livello, con suggerimenti, filtro per tema
  (forchetta, inchiodatura, matto in 2, ...) e spiegazione della soluzione.
- **Gioca** — partite contro il motore, da 600 a 2800 Elo, con suggerimento della mossa migliore.
- **Analisi** — revisione delle partite con il motore: precisione, mosse classificate
  (migliore, imprecisione, errore, errore grave), grafico della valutazione, frecce con la mossa
  migliore e una spiegazione in italiano di ogni errore. Puoi anche **importare un PGN** giocato
  su Lichess o Chess.com.
- **Impostazioni** — chiave API di Claude, quanto far lavorare il processore
  (Risparmio / Bilanciato / Prestazioni), Elo obiettivo e rating di partenza.

Gli scacchi funzionano senza servizi cloud; lo studio CFA/GMAT usa l'API di Claude per generare le
domande (poi restano salvate in locale). I tuoi dati restano in `backend/data/chessai.db`
(oppure in `~/Library/Application Support/ChessAI/` se usi l'[app per Mac](#app-per-mac)).

## Requisiti

| Cosa | Versione | Come installarlo |
|---|---|---|
| macOS (Apple Silicon o Intel) | — | — |
| [Homebrew](https://brew.sh) | — | vedi sito |
| Stockfish | 16 o successivo | `brew install stockfish` |
| Python | 3.11 | `brew install python@3.11` |
| Node.js | 20 o successivo | `brew install node` (oppure nvm) |

Spazio su disco: circa 300 MB (dipendenze + ~45 MB di puzzle).

## Prima installazione (una volta sola)

Dalla cartella del progetto:

```bash
# 1. Motore
brew install stockfish

# 2. Backend (Python)
cd backend
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. Puzzle di Lichess (scarica il database compresso, alcune centinaia di MB, e ne importa
#    un sottoinsieme bilanciato in backend/data/puzzles.db; richiede qualche minuto)
.venv/bin/python scripts/import_puzzles.py
cd ..

# 4. Frontend (interfaccia web)
cd frontend
npm install
cd ..
```

Se salti il passo 3 l'app funziona lo stesso, ma con un piccolo insieme di puzzle di riserva.

## Avvio

```bash
./start.sh
```

Lo script avvia il backend (http://localhost:8000) e l'interfaccia (http://localhost:5173) e apre
il browser. Per chiudere tutto premi **Ctrl+C** nel terminale.
(Se non vuoi che apra il browser: `CHESSAI_NO_OPEN=1 ./start.sh`.)

In alternativa, in due terminali separati:

```bash
backend/run.sh                 # backend su :8000
cd frontend && npm run dev     # interfaccia su :5173
```

## App per Mac

LearnAI può diventare una vera app per Mac, **LearnAI.app**: si apre dal Launchpad o dal Dock come
qualsiasi altra app, in una sua finestra, e contiene già tutto (server, Stockfish, puzzle e
interfaccia). Non servono terminale, browser, Python o Node per usarla.

**Costruirla e installarla** (una volta fatta la [prima installazione](#prima-installazione-una-volta-sola)
e con Xcode o i Command Line Tools installati):

```bash
macapp/build.sh
```

Lo script fa tutto da solo (build dell'interfaccia, backend "congelato" con PyInstaller, app Swift,
icona, firma) in circa 20 secondi, crea `dist/LearnAI.app` e la copia in **`/Applications/LearnAI.app`**
(sostituendo solo una versione precedente di LearnAI). Con `macapp/build.sh --no-install` si ferma a
`dist/LearnAI.app`. Rilancia lo script ogni volta che aggiorni il codice.

**Avvio**: apri LearnAI dal Launchpad/Finder oppure `open /Applications/LearnAI.app`. Compare una
schermata di caricamento e dopo circa un secondo l'interfaccia. Per chiudere: ⌘Q o chiudi la finestra
(il motore e il server si fermano insieme all'app). ⌘C / ⌘V / ⌘A funzionano nei campi di testo
(es. import PGN), ⌘R ricarica la pagina, ⌘+ / ⌘- regolano lo zoom.

**Dove stanno i file**

| Cosa | Dove |
|---|---|
| App | `/Applications/LearnAI.app` (circa 180 MB: 95 MB Stockfish, 45 MB puzzle, 36 MB server) |
| I tuoi dati (rating, partite, analisi, impostazioni) | `~/Library/Application Support/ChessAI/chessai.db` |
| Log del server | `~/Library/Logs/ChessAI/server.log` (e `server.previous.log` dell'avvio precedente) |
| Preferenze della finestra | `~/Library/Preferences/com.local.chessai.plist` |

L'app parte con un profilo nuovo: **non** importa i dati di sviluppo di `backend/data/chessai.db`.
Dal menu **Aiuto** puoi aprire la cartella dei dati o il log. Se il server non riesce a partire,
l'app mostra un avviso con il percorso del log.

**Disinstallare**

```bash
osascript -e 'tell application "LearnAI" to quit'
rm -rf /Applications/LearnAI.app
# facoltativo, per cancellare anche dati e impostazioni (irreversibile):
rm -rf ~/Library/Application\ Support/ChessAI ~/Library/Logs/ChessAI \
       ~/Library/WebKit/com.local.chessai ~/Library/Caches/com.local.chessai \
       ~/Library/HTTPStorages/com.local.chessai
defaults delete com.local.chessai
```

Dettagli tecnici e scelte implementative: `macapp/README.md`.

## Quanto consuma il processore

Stockfish viene avviato **solo quando serve** e si chiude da solo dopo 5 minuti di inattività:
quando non giochi e non analizzi, il consumo è **zero**. Il profilo si sceglie in **Impostazioni**.

Misure su un Mac Apple Silicon con 8 core (100% = un core del processore occupato al massimo):

**Mossa del motore durante una partita**

| Profilo | Core usati | Bot 800 Elo | Bot 1500 Elo | Bot 2500 Elo |
|---|---|---|---|---|
| Risparmio | 1 | istantanea | ~0,2 s, 1 core pieno | ~0,3 s, 1 core pieno |
| Bilanciato (predefinito) | 2 | istantanea | ~0,4 s, 2 core pieni | ~0,6 s, 2 core pieni |
| Prestazioni | 6 | istantanea | ~0,4 s, ~4 core | ~0,6 s, ~6 core |

In pratica: il motore "pensa" per meno di un secondo a ogni mossa e poi si ferma.
Più il bot è forte, più ci pensa (da 0,1 s a 400 Elo fino a 0,8 s al massimo).

**Analisi di una partita intera (40 mosse)**

| Profilo | Durata | Carico |
|---|---|---|
| Risparmio | ~6 secondi | 1 core |
| Bilanciato | ~12 secondi | 2 core |
| Prestazioni | ~12 secondi | ~6 core |

**A riposo**: 0% — il backend non consuma nulla e il motore, se acceso, resta fermo finché non
viene spento automaticamente.

Consiglio: a batteria usa **Risparmio**; per analisi più profonde usa **Prestazioni**.
I dettagli tecnici sono in `backend/CPU_REPORT.md`.

## Come funziona il percorso verso i 2000

1. **Punto di partenza.** Parti da 1200 (o dal tuo Elo online, impostabile in Impostazioni).
   L'app tiene due rating separati con il sistema **Glicko-2**: uno per i puzzle e uno per le
   partite contro il motore. All'inizio cambiano molto, poi si stabilizzano man mano che giochi.
2. **Livelli.** La tua "forza" (60% rating partite + 40% rating puzzle) determina il livello:
   Principiante (<1000), Base (1000–1300), Intermedio (1300–1600), Avanzato (1600–1800),
   Esperto (1800–2000), Obiettivo raggiunto (≥ obiettivo). La barra di progresso misura
   quanta strada hai fatto dal punto di partenza all'obiettivo.
3. **Piano di oggi**, generato ogni giorno in base ai tuoi dati:
   - **Riscaldamento**: 5 puzzle facili (circa 200 punti sotto il tuo rating);
   - **Allenamento mirato**: 10 puzzle sui 2 temi in cui sbagli di più;
   - **Partita**: contro il motore a circa **100 punti sopra** il tuo rating partite — man mano che
     vinci il bot diventa più forte, così la difficoltà sale insieme a te;
   - **Revisione**: analisi dell'ultima partita non ancora rivista, per capire gli errori.
4. **Punti deboli.** Ogni puzzle sbagliato e ogni errore trovato nelle tue partite aumentano il peso
   del tema corrispondente (forchetta, pezzo in presa, matto in 2, finale...). I puzzle successivi
   insistono su quei temi finché la percentuale di riuscita non migliora.
5. **Consigli** su aperture, principi e finali adatti al tuo livello.

## Studio CFA e GMAT

Ogni esame (CFA I, CFA II, CFA III, GMAT Focus) ha il suo rating, che parte da 1300; 1700 è il
livello indicativo "da esame".

**Percorso integrato (gratis, offline)**: per ogni esame c'è un percorso di moduli in ordine, uno per
argomento del programma. Ogni modulo ha una lezione in italiano (concetti, formule da sapere, errori
tipici, con il termine inglese tra parentesi accanto ai termini tecnici) e una banca di domande scritte
a mano con spiegazione: 308 in tutto (CFA I 119, CFA II 80 in 20 casi/vignette, CFA III 48 in 12 casi,
GMAT 61). Sono in `backend/app/resources/study/<esame>.json` più eventuali pacchetti aggiuntivi
`<esame>.<nome>.json` (uniti per argomento) e vengono caricate nella banca locale all'avvio, anche in
un database già esistente. Dopo aver aggiunto o modificato contenuti esegui
`cd backend && .venv/bin/python scripts/annotate_terms.py` per aggiungere i termini inglesi dal glossario. Un argomento è "padroneggiato" con almeno 5 risposte e il 70% di corrette.

**Esercizio adattivo**:

1. scegli un argomento oppure lascia **Automatico**: l'argomento viene estratto in base al suo peso
   nell'esame e ai tuoi errori;
2. la domanda viene presa dalla banca locale vicino al tuo rating, prima tra quelle integrate; quando le
   hai finite e hai inserito una chiave API, Claude ne genera di nuove a pagamento (la prima volta può volerci fino a un minuto). Quando la banca si sta
   esaurendo, altre domande vengono preparate in background;
3. rispondi: il rating si aggiorna solo alla prima risposta a ogni domanda e ricevi la spiegazione
   in italiano;
4. se una domanda ti sembra sbagliata (succede, soprattutto nei calcoli), premi
   **Segnala domanda errata**: viene esclusa e il suo effetto sul rating viene annullato.

Formati: CFA I con domande singole a 3 opzioni; CFA II e III con un caso (vignette) dentro ogni domanda;
GMAT a 5 opzioni (Data Sufficiency con le opzioni standard). Non sono inclusi le risposte aperte del
CFA III, Two-Part Analysis e Multi-Source Reasoning a risposte multiple. I pesi degli argomenti sono
approssimativi. Le domande sono originali, non materiale ufficiale CFA Institute/GMAC: usale come
allenamento in aggiunta ai materiali ufficiali.

**Chiave API**: serve una chiave Anthropic (console.anthropic.com), con costo a consumo. Inseriscila in
**Impostazioni → Claude** (viene salvata nel database locale `chessai.db`, mai restituita dall'API) oppure
esporta `ANTHROPIC_API_KEY` prima di `./start.sh`. Per l'app per Mac usa le Impostazioni: aperta dal
Finder non vede le variabili d'ambiente della shell.

## Spiegazioni più ricche con Claude negli scacchi (facoltativo)

Le spiegazioni degli errori sono sempre generate in locale con regole euristiche in italiano.
Se imposti una chiave API di Anthropic (da Impostazioni o con la variabile d'ambiente), i 5 errori più gravi di ogni partita analizzata vengono
spiegati in modo più discorsivo da Claude (con ritorno automatico alle spiegazioni locali in caso
di problemi):

```bash
export ANTHROPIC_API_KEY="la-tua-chiave"
./start.sh
```

Senza chiave gli scacchi funzionano completamente offline (a parte il download iniziale dei puzzle).

## Struttura del progetto

| Percorso | Contenuto |
|---|---|
| `backend/` | API FastAPI + Stockfish (`backend/run.sh`), test con `cd backend && .venv/bin/python -m pytest -q` |
| `frontend/` | Interfaccia Vite + React (`npm run dev`, `npm run build`) |
| `docs/ARCHITECTURE.md` | Architettura e contratto API |
| `backend/DEVIATIONS.md` | Scelte implementative ed estensioni rispetto al contratto |
| `backend/CPU_REPORT.md` | Misure dettagliate del consumo di CPU |
| `start.sh` | Avvio di backend e frontend insieme |
| `macapp/` | App nativa per Mac: wrapper Swift, icona e `build.sh` (vedi `macapp/README.md`) |
