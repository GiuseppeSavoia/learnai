// Mock di sviluppo del backend (attivo con VITE_MOCK=1).
// Implementa in memoria tutto il contratto /api per sviluppare la UI senza backend.
import { Chess, type Move } from 'chess.js'
import { ApiError } from './client'
import { studyRoute } from './mockStudy'
import type {
  EngineStatus,
  GameAnalysis,
  GameState,
  GameSummary,
  MoveAnalysis,
  Plan,
  Profile,
  Puzzle,
  PuzzleTheme,
  Weaknesses,
  Classification,
} from './client'

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms))

// ---------------------------------------------------------------- dati statici
const THEMES: PuzzleTheme[] = [
  { theme: 'fork', label_it: 'Forchetta', count: 4120 },
  { theme: 'pin', label_it: 'Inchiodatura', count: 2875 },
  { theme: 'hangingPiece', label_it: 'Pezzo in presa', count: 3310 },
  { theme: 'backRankMate', label_it: 'Matto sulla traversa', count: 980 },
  { theme: 'mateIn1', label_it: 'Matto in 1', count: 2200 },
  { theme: 'mateIn2', label_it: 'Matto in 2', count: 1850 },
  { theme: 'skewer', label_it: 'Infilata', count: 760 },
  { theme: 'endgame', label_it: 'Finale', count: 5400 },
  { theme: 'discoveredAttack', label_it: 'Attacco di scoperta', count: 1220 },
  { theme: 'promotion', label_it: 'Promozione', count: 640 },
]
const themeLabel = (t: string) => THEMES.find((x) => x.theme === t)?.label_it ?? t

const PUZZLES: Puzzle[] = [
  {
    id: 'm001',
    fen: '6k1/p4ppp/8/8/8/8/5PPP/3R2K1 b - - 0 1',
    moves: ['a7a6', 'd1d8'],
    rating: 1050,
    themes: ['backRankMate', 'mateIn1'],
    themes_it: [],
  },
  {
    id: 'm002',
    fen: 'r3k3/7p/8/3N4/8/8/8/6K1 b - - 0 1',
    moves: ['h7h6', 'd5c7', 'e8d7', 'c7a8'],
    rating: 1180,
    themes: ['fork'],
    themes_it: [],
  },
  {
    id: 'm003',
    fen: '4k3/8/8/q7/8/8/8/3RK3 b - - 0 1',
    moves: ['a5d5', 'd1d5'],
    rating: 900,
    themes: ['hangingPiece'],
    themes_it: [],
  },
  {
    id: 'm004',
    fen: '2r3k1/5ppp/8/8/8/8/1Q3PPP/6K1 w - - 0 1',
    moves: ['b2b3', 'c8c1', 'b3d1', 'c1d1'],
    rating: 1240,
    themes: ['backRankMate', 'mateIn2'],
    themes_it: [],
  },
  {
    id: 'm005',
    fen: '8/1P6/8/8/8/k7/8/K7 b - - 0 1',
    moves: ['a3a4', 'b7b8q'],
    rating: 800,
    themes: ['promotion', 'endgame'],
    themes_it: [],
  },
].map((p) => ({ ...p, themes_it: p.themes.map(themeLabel) }))

let puzzleIdx = 0
let puzzleRating = 1342

function makeHistory() {
  const out: Profile['rating_history'] = []
  const now = new Date()
  let pr = 1180
  let gr = 1150
  for (let i = 29; i >= 0; i--) {
    const d = new Date(now)
    d.setDate(now.getDate() - i)
    pr += Math.round(Math.sin(i * 1.7) * 18 + 6)
    gr += Math.round(Math.cos(i * 1.3) * 14 + 4)
    out.push({ date: d.toISOString().slice(0, 10), puzzle_rating: pr, game_rating: gr })
  }
  return out
}

const profile: Profile = {
  puzzle_rating: puzzleRating,
  puzzle_rd: 85,
  game_rating: 1268,
  game_rd: 110,
  target_elo: 2000,
  level: 2,
  level_name: 'Base',
  progress_pct: 0,
  puzzles_solved: 214,
  puzzles_failed: 97,
  games_played: 18,
  rating_history: makeHistory(),
}

function levelName(r: number) {
  if (r < 1000) return 'Principiante'
  if (r < 1300) return 'Base'
  if (r < 1600) return 'Intermedio'
  if (r < 1800) return 'Avanzato'
  if (r < 2000) return 'Esperto'
  return 'Obiettivo raggiunto'
}

function refreshProfile() {
  profile.puzzle_rating = puzzleRating
  const best = Math.max(profile.puzzle_rating, profile.game_rating)
  profile.level_name = levelName(best)
  const start = 800
  profile.progress_pct = Math.max(0, Math.min(100, Math.round(((best - start) / (profile.target_elo - start)) * 100)))
}
refreshProfile()

const engine: EngineStatus = {
  available: true,
  path: '/opt/homebrew/bin/stockfish',
  version: 'Stockfish 17.1',
  running: false,
  threads: 2,
  hash_mb: 128,
  profile: 'balanced',
  cpu_count: 10,
}

// ---------------------------------------------------------------- partite
interface MockGame {
  id: number
  chess: Chess
  color: 'white' | 'black'
  bot_elo: number
  created_at: string
  status: 'active' | 'finished'
  result: GameState['result']
  termination: string | null
  last_bot_move: string | null
  imported: boolean
  analysisStartedAt: number | null
}

const games = new Map<number, MockGame>()
let nextGameId = 1

function addGame(pgn: string | null, color: 'white' | 'black', bot_elo: number, daysAgo: number, imported = false) {
  const chess = new Chess()
  if (pgn) chess.loadPgn(pgn)
  const d = new Date()
  d.setDate(d.getDate() - daysAgo)
  const g: MockGame = {
    id: nextGameId++,
    chess,
    color,
    bot_elo,
    created_at: d.toISOString(),
    status: pgn ? 'finished' : 'active',
    result: null,
    termination: null,
    last_bot_move: null,
    imported,
    analysisStartedAt: null,
  }
  if (pgn) finishFromPosition(g)
  games.set(g.id, g)
  return g
}

function finishFromPosition(g: MockGame) {
  const c = g.chess
  if (c.isCheckmate()) {
    g.result = c.turn() === 'w' ? '0-1' : '1-0'
    g.termination = 'Scacco matto'
  } else if (c.isDraw() || c.isStalemate()) {
    g.result = '1/2-1/2'
    g.termination = c.isStalemate() ? 'Stallo' : 'Patta'
  } else {
    const r = c.getHeaders()['Result']
    g.result = r === '1-0' || r === '0-1' || r === '1/2-1/2' ? r : '0-1'
    g.termination = 'Abbandono'
  }
  g.status = 'finished'
}

// partite d'esempio
const g1 = addGame('1. e4 e5 2. Nf3 Nc6 3. Bc4 Nd4 4. Nxe5 Qg5 5. Nxf7 Qxg2 6. Rf1 Qxe4+ 7. Be2 Nf3#', 'white', 1300, 2)
g1.analysisStartedAt = 0 // già analizzata
addGame(
  '1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. Bg5 Be7 5. e3 O-O 6. Nf3 Nbd7 7. Rc1 c6 8. Bd3 dxc4 9. Bxc4 Nd5 10. Bxe7 Qxe7 11. O-O Nxc3 12. Rxc3 e5 13. Qc2 e4 14. Nd2 Nf6 15. Rc1 Bg4 16. h3 Bh5 17. Nxe4 Nxe4 18. Qxe4 Qxe4 1-0',
  'white',
  1400,
  1,
)

function gameState(g: MockGame): GameState {
  const hist = g.chess.history({ verbose: true })
  return {
    id: g.id,
    fen: g.chess.fen(),
    pgn: g.chess.pgn(),
    moves_san: hist.map((m) => m.san),
    moves_uci: hist.map(uciOf),
    color: g.color,
    bot_elo: g.bot_elo,
    status: g.status,
    result: g.result,
    termination: g.termination,
    last_bot_move: g.last_bot_move,
  }
}

const uciOf = (m: Move) => m.from + m.to + (m.promotion ?? '')
const VALUES: Record<string, number> = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 }

function material(c: Chess): number {
  let s = 0
  for (const row of c.board())
    for (const sq of row) if (sq) s += (sq.color === 'w' ? 1 : -1) * VALUES[sq.type]
  return s
}

/** Valutazione statica (cp, punto di vista del Bianco) con matto = ±10000. */
function staticEval(c: Chess): number {
  if (c.isCheckmate()) return c.turn() === 'w' ? -10000 : 10000
  if (c.isDraw()) return 0
  return material(c) * 100
}

/** Valutazione a 2 semimosse: dopo la mossa, l'avversario risponde con la cattura migliore. */
function scoreMove(c: Chess, m: Move): number {
  const pov = c.turn() === 'w' ? 1 : -1
  c.move(m)
  let worst = staticEval(c) * pov
  if (!c.isGameOver()) {
    for (const r of c.moves({ verbose: true })) {
      c.move(r)
      const v = staticEval(c) * pov
      if (v < worst) worst = v
      c.undo()
    }
  }
  c.undo()
  return worst
}

function bestMove(c: Chess): { move: Move; score: number } | null {
  const moves = c.moves({ verbose: true })
  if (!moves.length) return null
  let best = moves[0]
  let bestScore = -Infinity
  for (const m of moves) {
    const s = scoreMove(c, m) + Math.random() * 10
    if (s > bestScore) {
      bestScore = s
      best = m
    }
  }
  return { move: best, score: bestScore }
}

function botReply(g: MockGame) {
  if (g.chess.isGameOver()) return
  const moves = g.chess.moves({ verbose: true })
  // bot semplice: a Elo alto sceglie la mossa "migliore", altrimenti a volte casuale
  const pick = Math.random() < Math.min(0.9, g.bot_elo / 2400) ? bestMove(g.chess)!.move : moves[Math.floor(Math.random() * moves.length)]
  g.chess.move(pick)
  g.last_bot_move = uciOf(pick)
}

function checkEnd(g: MockGame) {
  if (g.chess.isGameOver()) finishFromPosition(g)
}

// ---------------------------------------------------------------- analisi
function classify(cpLoss: number, ply: number, nLegal: number): Classification {
  if (nLegal === 1) return 'forced'
  if (ply <= 4) return 'book'
  if (cpLoss >= 300) return 'blunder'
  if (cpLoss >= 150) return 'mistake'
  if (cpLoss >= 60) return 'inaccuracy'
  if (cpLoss <= 0) return 'best'
  if (cpLoss < 25) return 'excellent'
  return 'good'
}

const CLS_IT: Record<Classification, string> = {
  best: 'Mossa migliore',
  excellent: 'Ottima mossa',
  good: 'Buona mossa',
  inaccuracy: 'Imprecisione',
  mistake: 'Errore',
  blunder: 'Errore grave',
  book: 'Mossa di teoria',
  forced: 'Mossa forzata',
}

const analysisCache = new Map<number, GameAnalysis>()

function analyse(g: MockGame): GameAnalysis {
  const cached = analysisCache.get(g.id)
  if (cached) return cached
  const res = computeAnalysis(g)
  analysisCache.set(g.id, res)
  return res
}

function computeAnalysis(g: MockGame): GameAnalysis {
  const hist = g.chess.history({ verbose: true })
  const c = new Chess()
  const moves: MoveAnalysis[] = []
  let prevEval = 20
  hist.forEach((m, i) => {
    const ply = i + 1
    const legal = c.moves({ verbose: true })
    const pov = c.turn() === 'w' ? 1 : -1
    const best = bestMove(c)!
    const played = legal.find((x) => x.san === m.san)!
    const playedScore = scoreMove(c, played)
    const bestScore = Math.round(best.score)
    const evalBefore = ply === 1 ? prevEval : prevEval
    const fenBefore = c.fen()
    c.move(m.san)
    const evalAfter = c.isCheckmate() ? (pov === 1 ? 9999 : -9999) : Math.round(playedScore * pov + ((ply * 37) % 23) - 11)
    const cpLoss = Math.max(0, Math.min(1000, bestScore - playedScore))
    const cls = classify(cpLoss, ply, legal.length)
    const moveNo = `${Math.ceil(ply / 2)}${ply % 2 ? '.' : '...'}`
    const isBest = best.move.san === m.san
    let expl = `${CLS_IT[cls]}: ${moveNo}${m.san}.`
    if (['inaccuracy', 'mistake', 'blunder'].includes(cls)) {
      expl += ` Perdi circa ${(cpLoss / 100).toFixed(1)} pedoni di valore.`
      if (m.captured) expl += ' La cattura sembra allettante ma concede una risposta forte all\'avversario.'
      else expl += ' Questa mossa lascia materiale scoperto o ignora una minaccia.'
      expl += ` Era meglio ${moveNo}${best.move.san}${best.move.captured ? ', che vince materiale' : ', che mantiene l\'equilibrio'}.`
    } else if (cls === 'book') {
      expl = `${moveNo}${m.san} è una mossa di teoria d'apertura.`
    } else if (isBest) {
      expl += ' È la scelta del motore.'
    }
    moves.push({
      ply,
      color: pov === 1 ? 'white' : 'black',
      san: m.san,
      uci: uciOf(m),
      fen_before: fenBefore,
      fen_after: c.fen(),
      eval_before: evalBefore,
      eval_after: evalAfter,
      best_move_uci: uciOf(best.move),
      best_move_san: best.move.san,
      best_line_san: [best.move.san],
      cp_loss: isBest ? 0 : cpLoss,
      classification: isBest && cls !== 'book' && cls !== 'forced' ? 'best' : cls,
      explanation_it: expl,
      themes: cls === 'blunder' ? ['hangingPiece'] : [],
    })
    prevEval = evalAfter
  })
  const counts: Record<string, number> = { blunder: 0, mistake: 0, inaccuracy: 0, good: 0, excellent: 0, best: 0, book: 0, forced: 0 }
  for (const m of moves) counts[m.classification]++
  const acc = (col: 'white' | 'black') => {
    const ms = moves.filter((m) => m.color === col)
    if (!ms.length) return 100
    const avg = ms.reduce((s, m) => s + Math.min(m.cp_loss, 500), 0) / ms.length
    return Math.round(Math.max(20, 100 - avg / 4) * 10) / 10
  }
  const userCol = g.color
  const userBl = moves.filter((m) => m.color === userCol && m.classification === 'blunder').length
  return {
    status: 'done',
    progress: 1,
    accuracy_white: acc('white'),
    accuracy_black: acc('black'),
    summary_it:
      `Partita di ${Math.ceil(moves.length / 2)} mosse. ` +
      (userBl
        ? `Hai commesso ${userBl} errore/i grave/i: rivedi le posizioni evidenziate in rosso e cerca le minacce dell'avversario prima di muovere.`
        : 'Nessun errore grave: buona partita! Lavora sulle imprecisioni per alzare la precisione.'),
    counts,
    moves,
  }
}

const ANALYSIS_MS = 3500

// ---------------------------------------------------------------- router
function bad(status: number, msg: string): never {
  throw new ApiError(status, msg)
}

function getGame(id: string): MockGame {
  const g = games.get(Number(id))
  if (!g) bad(404, 'Partita non trovata')
  return g
}

export async function mockRequest<T>(method: string, fullPath: string, body?: unknown): Promise<T> {
  await delay(120 + Math.random() * 120)
  const [path, query = ''] = fullPath.split('?')
  const q = new URLSearchParams(query)
  const b = (body ?? {}) as Record<string, unknown>
  const seg = path.split('/').filter(Boolean)
  const res = route(method, seg, q, b)
  // copia profonda per evitare mutazioni condivise
  return JSON.parse(JSON.stringify(res)) as T
}

function route(method: string, seg: string[], q: URLSearchParams, b: Record<string, unknown>): unknown {
  if (seg[0] === 'study' || (seg[0] === 'settings' && seg[1] === 'claude')) return studyRoute(method, seg, q, b)
  const key = `${method} /${seg.map((s, i) => (i > 0 && /^[\w-]+$/.test(s) && (seg[i - 1] === 'games' || seg[i - 1] === 'puzzles') && !['next', 'themes', 'import'].includes(s) ? ':id' : s)).join('/')}`
  switch (key) {
    case 'GET /profile':
      refreshProfile()
      return profile
    case 'PUT /profile':
      if (typeof b.target_elo === 'number') profile.target_elo = b.target_elo
      if (typeof b.initial_rating === 'number') {
        puzzleRating = b.initial_rating
        profile.game_rating = b.initial_rating
      }
      refreshProfile()
      return profile
    case 'GET /plan/today': {
      const plan: Plan = {
        date: new Date().toISOString().slice(0, 10),
        level_name: profile.level_name,
        focus_themes: ['fork', 'pin'],
        tips: [
          'Prima di ogni mossa chiediti: quali pezzi sono indifesi? Quali minacce ha l\'avversario?',
          'In apertura sviluppa i pezzi leggeri prima della Donna e arrocca presto.',
          'Nei finali di torre, attiva il Re e metti la torre dietro il pedone passato.',
        ],
        items: [
          { id: 'warmup', kind: 'warmup', title: 'Riscaldamento', description: '5 puzzle facili per scaldarti (rating −200).', done: true, params: { mode: 'warmup', count: 5 } },
          { id: 'focus', kind: 'puzzles', title: 'Allenamento mirato', description: '10 puzzle su Forchetta e Inchiodatura.', done: false, params: { mode: 'focus', themes: ['fork', 'pin'], count: 10 } },
          { id: 'game', kind: 'game', title: 'Partita contro il bot', description: `Gioca una partita contro il motore a ${profile.game_rating + 100} Elo.`, done: false, params: { bot_elo: profile.game_rating + 100 } },
          { id: 'review', kind: 'review', title: 'Revisione', description: 'Analizza la tua ultima partita e trova gli errori.', done: false, params: { game_id: 2 } },
        ],
      }
      return plan
    }
    case 'GET /stats/weaknesses': {
      const w: Weaknesses = {
        themes: [
          { theme: 'fork', label_it: 'Forchetta', errors: 14, attempts: 31, success_rate: 0.55 },
          { theme: 'pin', label_it: 'Inchiodatura', errors: 11, attempts: 26, success_rate: 0.58 },
          { theme: 'endgame', label_it: 'Finale', errors: 8, attempts: 22, success_rate: 0.64 },
          { theme: 'backRankMate', label_it: 'Matto sulla traversa', errors: 5, attempts: 18, success_rate: 0.72 },
          { theme: 'hangingPiece', label_it: 'Pezzo in presa', errors: 3, attempts: 20, success_rate: 0.85 },
        ],
      }
      return w
    }
    case 'GET /puzzles/next': {
      const theme = q.get('theme')
      const pool = theme ? PUZZLES.filter((p) => p.themes.includes(theme)) : PUZZLES
      const list = pool.length ? pool : PUZZLES
      const p = list[puzzleIdx++ % list.length]
      return p
    }
    case 'GET /puzzles/themes':
      return THEMES
    case 'POST /puzzles/:id/attempt': {
      const p = PUZZLES.find((x) => x.id === seg[1])
      const success = !!b.success
      const hints = Number(b.hints_used ?? 0)
      const delta = success ? Math.max(2, 12 - hints * 4) : -9
      puzzleRating += delta
      if (success) profile.puzzles_solved++
      else profile.puzzles_failed++
      const tm = p ? p.themes_it.join(', ') : ''
      return {
        puzzle_rating: puzzleRating,
        delta,
        explanation_it: success
          ? `Esatto! Il tema era: ${tm}. Hai sfruttato la debolezza dell'avversario in modo preciso.`
          : `Non era la mossa giusta. Tema: ${tm}. Cerca prima scacchi, catture e minacce: la soluzione inizia con ${p ? p.moves[1] : '?'}.`,
      }
    }
    case 'POST /games': {
      let color = (b.color as string) ?? 'white'
      if (color === 'random') color = Math.random() < 0.5 ? 'white' : 'black'
      const g = addGame(null, color as 'white' | 'black', Number(b.bot_elo ?? profile.game_rating + 100), 0)
      if (g.color === 'black') botReply(g)
      return gameState(g)
    }
    case 'GET /games':
      return [...games.values()]
        .sort((a, b2) => b2.id - a.id)
        .map<GameSummary>((g) => ({
          id: g.id,
          created_at: g.created_at,
          bot_elo: g.imported ? null : g.bot_elo,
          color: g.color,
          result: g.result,
          status: g.status,
          analyzed: g.analysisStartedAt !== null && Date.now() - g.analysisStartedAt >= ANALYSIS_MS,
          accuracy: g.analysisStartedAt !== null && Date.now() - g.analysisStartedAt >= ANALYSIS_MS ? analyse(g)[g.color === 'white' ? 'accuracy_white' : 'accuracy_black'] : null,
        }))
    case 'GET /games/:id':
      return gameState(getGame(seg[1]))
    case 'POST /games/:id/move': {
      const g = getGame(seg[1])
      if (g.status !== 'active') bad(400, 'La partita è terminata')
      const uci = String(b.uci ?? '')
      try {
        g.chess.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] })
      } catch {
        bad(400, 'Mossa illegale')
      }
      g.last_bot_move = null
      checkEnd(g)
      if (g.status === 'active') {
        botReply(g)
        checkEnd(g)
      }
      return gameState(g)
    }
    case 'POST /games/:id/resign': {
      const g = getGame(seg[1])
      g.status = 'finished'
      g.result = g.color === 'white' ? '0-1' : '1-0'
      g.termination = 'Abbandono'
      return gameState(g)
    }
    case 'POST /games/:id/hint': {
      const g = getGame(seg[1])
      const bm = bestMove(g.chess)
      if (!bm) bad(400, 'Nessuna mossa disponibile')
      const m = bm.move
      return {
        uci: uciOf(m),
        san: m.san,
        explanation_it: m.captured
          ? `Considera ${m.san}: catturi materiale senza concedere contropartite.`
          : m.san.includes('+')
            ? `${m.san} dà scacco e prende l'iniziativa.`
            : `${m.san} migliora la posizione del pezzo e controlla case importanti.`,
      }
    }
    case 'POST /games/import': {
      const pgn = String(b.pgn ?? '')
      const c = new Chess()
      try {
        c.loadPgn(pgn)
      } catch {
        bad(400, 'PGN non valido')
      }
      if (!c.history().length) bad(400, 'Il PGN non contiene mosse')
      const g = addGame(pgn, b.color === 'black' ? 'black' : 'white', 0, 0, true)
      return { id: g.id }
    }
    case 'POST /games/:id/analyze': {
      const g = getGame(seg[1])
      if (g.analysisStartedAt === null) g.analysisStartedAt = Date.now()
      return analysisProgress(g)
    }
    case 'GET /games/:id/analysis': {
      const g = getGame(seg[1])
      if (g.analysisStartedAt === null) bad(404, 'Analisi non disponibile')
      const p = analysisProgress(g)
      if (p.status !== 'done')
        return { ...p, accuracy_white: null, accuracy_black: null, summary_it: null, counts: {}, moves: [] } satisfies GameAnalysis
      return analyse(g)
    }
    case 'POST /analysis/position': {
      const c = new Chess(String(b.fen))
      const bm = bestMove(c)
      const ev = staticEval(c)
      return {
        eval: ev,
        lines: bm ? [{ eval: ev, moves_san: [bm.move.san], moves_uci: [uciOf(bm.move)] }] : [],
        explanation_it: bm ? `La mossa migliore è ${bm.move.san}.` : 'Partita terminata.',
      }
    }
    case 'GET /engine/status':
      return engine
    case 'PUT /engine/settings': {
      const prof = b.profile as string | undefined
      if (prof === 'eco') Object.assign(engine, { profile: 'eco', threads: 1, hash_mb: 64 })
      if (prof === 'balanced') Object.assign(engine, { profile: 'balanced', threads: 2, hash_mb: 128 })
      if (prof === 'performance') Object.assign(engine, { profile: 'performance', threads: 6, hash_mb: 256 })
      if (typeof b.threads === 'number') engine.threads = b.threads
      if (typeof b.hash_mb === 'number') engine.hash_mb = b.hash_mb
      return engine
    }
  }
  bad(404, `Mock: endpoint non gestito ${key}`)
}

function analysisProgress(g: MockGame) {
  const el = Date.now() - (g.analysisStartedAt ?? Date.now())
  if (el >= ANALYSIS_MS) return { status: 'done', progress: 1 }
  if (el < 400) return { status: 'queued', progress: 0 }
  return { status: 'running', progress: Math.min(0.99, el / ANALYSIS_MS) }
}
