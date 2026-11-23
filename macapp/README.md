# LearnAI.app — app nativa per Mac

Questa cartella contiene tutto ciò che serve per trasformare LearnAI (backend FastAPI + interfaccia
React) in un'app per Mac autosufficiente: nessun Python, Node o Homebrew richiesto per usarla.

```bash
macapp/build.sh               # build completa → dist/LearnAI.app, poi copia in /Applications
macapp/build.sh --no-install  # solo dist/LearnAI.app
```

Prerequisiti per **costruirla** (non per usarla): Xcode o Command Line Tools (`swiftc`, `iconutil`,
`codesign`), `backend/.venv` con `backend/requirements-dev.txt` (PyInstaller; lo script lo installa
se manca), Node.js per la build del frontend, Stockfish (`brew install stockfish`) e, facoltativo,
`backend/data/puzzles.db` (senza, l'app usa il piccolo set di puzzle di riserva).

## File

| File | Ruolo |
|---|---|
| `build.sh` | Script unico e ripetibile: npm build → PyInstaller → swiftc → icona → bundle → firma → installazione |
| `Sources/main.swift` | Punto d'ingresso AppKit |
| `Sources/AppDelegate.swift` | Finestra unica con `WKWebView`, attesa di `/api/health`, chiusura ordinata, errori |
| `Sources/ServerController.swift` | Avvio/arresto del server congelato, scelta della porta, log |
| `Sources/LoadingView.swift` | Schermata nativa "Avvio di LearnAI…" |
| `Sources/MainMenu.swift` | Barra dei menu (LearnAI, Composizione, Vista, Finestra, Aiuto) |
| `make_icon.swift` | Disegna l'icona (♞ su quadrato arrotondato verde) a tutte le dimensioni dell'iconset |
| `Info.plist` | Metadati del bundle (`com.local.chessai`, macOS 13+, ATS solo per localhost) |
| `../backend/server.py` | Punto d'ingresso del server (uvicorn) congelato da PyInstaller |

## Struttura del bundle

```
LearnAI.app/Contents/
  Info.plist, PkgInfo
  MacOS/LearnAI                 wrapper Swift (AppKit + WKWebView), arm64
  Resources/
    server/chessai-server       backend congelato (PyInstaller onedir) + server/_internal/
    stockfish                   copia di Stockfish (dipende solo da libSystem e libc++)
    puzzles.db                  puzzle Lichess, aperto in sola lettura
    web/                        build del frontend (frontend/dist)
    AppIcon.icns
    licenses/stockfish-COPYING.txt
```

## Come funziona all'avvio

1. Il wrapper sceglie una porta libera su 127.0.0.1 (vedi deviazioni: preferisce quella dell'ultima volta).
2. Avvia `Resources/server/chessai-server` con queste variabili d'ambiente:
   `CHESSAI_DATA_DIR=~/Library/Application Support/ChessAI`, `CHESSAI_PUZZLES_DB=<bundle>/puzzles.db`,
   `STOCKFISH_PATH=<bundle>/stockfish`, `CHESSAI_STATIC_DIR=<bundle>/web`, `CHESSAI_PORT=<porta>`,
   `CHESSAI_PARENT_PID=<pid dell'app>`. Output in `~/Library/Logs/ChessAI/server.log`
   (il log dell'avvio precedente resta in `server.previous.log`).
3. Mostra una schermata di caricamento nativa e interroga `GET /api/health` ogni 150 ms (massimo 60 s).
4. Quando il server risponde carica `http://127.0.0.1:<porta>/` nella `WKWebView` e la mostra
   appena la pagina ha finito di caricare.
5. Se il server non parte (o si chiude durante l'uso) compare un `NSAlert` con il percorso del log e
   le ultime righe; durante l'uso si può scegliere **Riavvia**.

Alla chiusura (⌘Q, chiusura della finestra, `osascript -e 'tell application "LearnAI" to quit'`) l'app
risponde `terminateLater`, manda SIGTERM al server (spegnimento ordinato di uvicorn, che chiude anche
Stockfish), aspetta al massimo 5 s, poi SIGKILL; infine chiude eventuali figli rimasti.
Se l'app viene uccisa in modo anomalo (es. `kill -9`), il server se ne accorge entro un secondo
(`CHESSAI_PARENT_PID`) e si chiude da solo, e Stockfish esce quando il suo stdin si chiude.

## Deviazioni rispetto al progetto iniziale

- **Porta**: invece di una porta casuale a ogni avvio, l'app riusa la porta dell'ultima volta
  (default 47821, salvata in `UserDefaults` come `ServerPort`) se è libera, altrimenti ne sceglie una
  libera a caso e la ricorda. Motivo: il `localStorage` della WebView è legato all'origine
  `http://127.0.0.1:<porta>`; con una porta stabile il tema chiaro/scuro e la serie di puzzle
  sopravvivono ai riavvii. Se il server termina durante l'avvio (es. porta occupata nel frattempo)
  l'app riprova una volta su una porta casuale.
- **Posizione della finestra**: salvata a mano in `UserDefaults` (`MainWindowFrame`) invece di
  `setFrameAutosaveName`. Su questo Mac (display con notch + due monitor esterni, macOS 15) il
  meccanismo standard ripristinava la dimensione ma spostava la finestra su un altro schermo; il
  ripristino manuale è stato verificato su tutti e tre gli schermi. Se la cornice salvata non è più
  visibile (monitor scollegato) la finestra viene centrata.
- **Menu in italiano**, come l'interfaccia: *Composizione* (Edit), *Vista* (View), *Finestra* (Window)
  e un menu *Aiuto* con "Mostra la cartella dei dati" e "Mostra il log del server". *Vista* ha anche
  Dimensioni reali / Ingrandisci / Riduci (zoom della pagina) e il tutto schermo.
- **Variabili d'ambiente**: il nome richiesto `CHESSAI_PUZZLES_DB` è quello principale; il vecchio
  `CHESSAI_PUZZLE_DB` (già usato dal backend) è ancora accettato. In più `CHESSAI_HOST`/`CHESSAI_PORT`
  (anche `--host`/`--port` da riga di comando) e `CHESSAI_PARENT_PID`. Nel server congelato, se
  `CHESSAI_DATA_DIR` manca, il default è `~/Library/Application Support/ChessAI` (in sviluppo resta
  `backend/data`).
- **Frontend servito da una rotta "catch-all"** invece di `StaticFiles`: serve i file della build,
  restituisce `index.html` per le rotte client, 404 JSON per qualsiasi `/api/...` inesistente (anche
  POST) e 404 per file statici mancanti con estensione (es. `/favicon.ico`), senza mai uscire dalla
  cartella della build. `index.html` ha `Cache-Control: no-cache`, `/assets/*` (con hash) cache lunga.
- **Firma**: `codesign --deep` non entra in `Contents/Resources`, quindi lo script firma prima
  ad-hoc ogni Mach-O annidato (eseguibile del server, `.so`/`.dylib`, Stockfish) e poi l'intero
  bundle con `codesign --force --deep -s -`, verificato con `codesign --verify --deep --strict`.
  `spctl -a` risponde "rejected": è normale per una firma ad-hoc senza notarizzazione, ma l'app
  si apre senza avvisi di Gatekeeper perché non ha l'attributo `com.apple.quarantine` (lo script
  esegue `xattr -cr`). L'attributo `com.apple.provenance` che macOS 15 aggiunge da solo non è una
  quarantena e non si può rimuovere: non blocca l'avvio. **Se copi l'app su un altro Mac via
  AirDrop/download riceverà la quarantena**: aprila con clic destro → Apri oppure
  `xattr -dr com.apple.quarantine /Applications/LearnAI.app`.
- **Solo Apple Silicon (arm64)**: il Python del venv e lo Stockfish di Homebrew sono arm64, quindi
  l'app non è universale. Su un Mac Intel va ricostruita lì.
- **`_decimal` escluso** da PyInstaller: il Python 3.11 di Homebrew lo collega a `libmpdec`, che non è
  installata; il modulo `decimal` ripiega automaticamente sull'implementazione in puro Python.
- **Spiegazioni con Claude**: le app avviate dal Finder non ereditano le variabili della shell,
  quindi `ANTHROPIC_API_KEY` di norma non arriva al server e l'app usa le spiegazioni locali.
  Per abilitarle: `launchctl setenv ANTHROPIC_API_KEY ...` e poi riaprire l'app.
- **Licenza**: insieme a Stockfish (GPLv3) viene copiato il suo `Copying.txt` in
  `Resources/licenses/`. L'app è pensata per uso personale, non per la distribuzione.
- **Installazione**: lo script sostituisce `/Applications/LearnAI.app` solo se il suo
  `CFBundleIdentifier` è `com.local.chessai`; se ChessAI è aperta la chiude prima con AppleScript.
