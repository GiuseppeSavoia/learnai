// Client tipizzato per l'API del backend (base /api).
// I tipi rispecchiano esattamente il contratto in docs/ARCHITECTURE.md.

// ---------- Profilo & piano ----------
export interface RatingPoint {
  date: string
  puzzle_rating: number
  game_rating: number
}

export interface Profile {
  puzzle_rating: number
  puzzle_rd: number
  game_rating: number
  game_rd: number
  target_elo: number
  level: number | string
  level_name: string
  progress_pct: number
  /** Estensione del backend: forza combinata (60% partite + 40% puzzle) usata per livello e progresso. */
  strength?: number
  /** Estensione del backend: rating di partenza da cui si misura il progresso. */
  initial_rating?: number
  puzzles_solved: number
  puzzles_failed: number
  games_played: number
  rating_history: RatingPoint[]
}

export interface ProfileUpdate {
  target_elo?: number
  initial_rating?: number
}

export type PlanItemKind = 'warmup' | 'puzzles' | 'game' | 'review'

export interface PlanItem {
  id: string | number
  kind: PlanItemKind
  title: string
  description: string
  done: boolean
  params: Record<string, unknown>
}

export interface Plan {
  date: string
  level_name: string
  focus_themes: string[]
  tips: string[]
  items: PlanItem[]
}

export interface WeaknessTheme {
  theme: string
  label_it: string
  errors: number
  attempts: number
  success_rate: number
}

export interface Weaknesses {
  themes: WeaknessTheme[]
}

// ---------- Puzzle ----------
export type PuzzleMode = 'warmup' | 'focus' | 'normal'

export interface Puzzle {
  id: string
  fen: string
  moves: string[]
  rating: number
  themes: string[]
  themes_it: string[]
}

export interface PuzzleAttempt {
  success: boolean
  time_ms: number
  hints_used: number
}

export interface PuzzleAttemptResult {
  puzzle_rating: number
  delta: number
  explanation_it: string
}

export interface PuzzleTheme {
  theme: string
  label_it: string
  count: number
}

// ---------- Partite ----------
export type ColorChoice = 'white' | 'black' | 'random'
export type GameResult = '1-0' | '0-1' | '1/2-1/2' | null

export interface GameState {
  id: number | string
  fen: string
  pgn: string
  moves_san: string[]
  moves_uci: string[]
  color: 'white' | 'black'
  bot_elo: number
  status: 'active' | 'finished'
  result: GameResult
  termination: string | null
  last_bot_move: string | null
}

export interface GameSummary {
  id: number | string
  created_at: string
  bot_elo: number | null
  color: 'white' | 'black' | string
  result: GameResult | string
  status: 'active' | 'finished' | string
  analyzed: boolean
  accuracy?: number | null
}

export interface Hint {
  uci: string
  san: string
  explanation_it: string
}

// ---------- Analisi ----------
export type AnalysisStatus = 'queued' | 'running' | 'done' | 'none' | 'error' | string

export interface AnalyzeResponse {
  status: AnalysisStatus
  progress: number
}

export type Classification =
  | 'best'
  | 'excellent'
  | 'good'
  | 'inaccuracy'
  | 'mistake'
  | 'blunder'
  | 'book'
  | 'forced'

export interface MoveAnalysis {
  ply: number
  color: 'white' | 'black'
  san: string
  uci: string
  fen_before: string
  fen_after: string
  eval_before: number
  eval_after: number
  best_move_uci: string | null
  best_move_san: string | null
  best_line_san: string[]
  cp_loss: number
  classification: Classification
  explanation_it: string
  themes: string[]
}

export interface GameAnalysis {
  status: AnalysisStatus
  progress: number
  accuracy_white: number | null
  accuracy_black: number | null
  summary_it: string | null
  counts: Record<string, number>
  moves: MoveAnalysis[]
}

export interface PositionLine {
  eval: number
  moves_san: string[]
  moves_uci: string[]
}

export interface PositionAnalysis {
  eval: number
  lines: PositionLine[]
  explanation_it: string
}

// ---------- Motore ----------
export type EngineProfile = 'eco' | 'balanced' | 'performance'

export interface EngineStatus {
  available: boolean
  path: string | null
  version: string | null
  running: boolean
  threads: number
  hash_mb: number
  profile: EngineProfile | string
  cpu_count: number
}

export interface EngineSettings {
  profile?: EngineProfile
  threads?: number
  hash_mb?: number
}

// ---------- Trasporto ----------
// ---------- Studio (CFA, GMAT) ----------
export interface StudyExamSummary {
  id: string
  label: string
  short: string
  description: string
  rating: number
  rd: number
  target_rating: number
  progress_pct: number
  answered: number
  accuracy: number | null
  bank_total: number
  bank_unseen: number
}

export interface StudyExams {
  claude_enabled: boolean
  exams: StudyExamSummary[]
}

export interface StudyTopic {
  id: string
  label: string
  weight_pct: number
  attempts: number
  errors: number
  accuracy: number | null
  weakness: number
}

export interface StudyExamDetail extends StudyExamSummary {
  claude_enabled: boolean
  topics: StudyTopic[]
}

export interface StudyQuestion {
  id: number
  exam: string
  topic: string
  topic_label: string
  difficulty: number
  vignette: string
  stem: string
  choices: string[]
}

export interface StudyAnswerResult {
  correct: boolean
  answer: number
  explanation: string
  rated: boolean
  rating_before: number
  rating_after: number
  rating_delta: number
}

export interface LessonSection {
  title: string
  body: string[]
}

export interface StudyModule {
  step: number
  topic: string
  topic_label: string
  title: string
  summary: string
  sections: LessonSection[]
  formulas: string[]
  pitfalls: string[]
  n_questions: number
  lesson_done: boolean
  attempts: number
  accuracy: number | null
  mastered: boolean
}

export interface StudyPath {
  exam: string
  label: string
  modules: StudyModule[]
}

export interface ClaudeSettings {
  enabled: boolean
  source: 'env' | 'settings' | null
  model: string
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export const USE_MOCK = import.meta.env.VITE_MOCK === '1'

const BASE = '/api'

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  if (USE_MOCK) {
    const { mockRequest } = await import('./mock')
    return mockRequest<T>(method, path, body)
  }
  let res: Response
  try {
    res = await fetch(BASE + path, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'Impossibile contattare il backend (è avviato su :8000?)')
  }
  if (!res.ok) {
    let msg = `Errore ${res.status}`
    try {
      const data = await res.json()
      if (data && typeof data.detail === 'string') msg = data.detail
      else if (data && Array.isArray(data.detail)) msg = data.detail.map((d: { msg?: string }) => d.msg).join('; ')
    } catch {
      // risposta non JSON: tipicamente il proxy Vite quando il backend è spento
      if (res.status >= 500) msg = `Backend non raggiungibile (errore ${res.status}). È avviato su :8000?`
    }
    throw new ApiError(res.status, msg)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

function qs(params: Record<string, string | undefined>): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v) p.set(k, v)
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const api = {
  // profilo & piano
  getProfile: () => request<Profile>('GET', '/profile'),
  updateProfile: (body: ProfileUpdate) => request<Profile>('PUT', '/profile', body),
  getPlanToday: () => request<Plan>('GET', '/plan/today'),
  getWeaknesses: () => request<Weaknesses>('GET', '/stats/weaknesses'),

  // puzzle
  nextPuzzle: (opts: { theme?: string; mode?: PuzzleMode } = {}) =>
    request<Puzzle>('GET', '/puzzles/next' + qs({ theme: opts.theme, mode: opts.mode })),
  attemptPuzzle: (id: string, body: PuzzleAttempt) =>
    request<PuzzleAttemptResult>('POST', `/puzzles/${encodeURIComponent(id)}/attempt`, body),
  getPuzzleThemes: () => request<PuzzleTheme[]>('GET', '/puzzles/themes'),

  // partite
  newGame: (body: { bot_elo?: number; color: ColorChoice }) => request<GameState>('POST', '/games', body),
  getGame: (id: string | number) => request<GameState>('GET', `/games/${id}`),
  move: (id: string | number, uci: string) => request<GameState>('POST', `/games/${id}/move`, { uci }),
  resign: (id: string | number) => request<GameState>('POST', `/games/${id}/resign`),
  hint: (id: string | number) => request<Hint>('POST', `/games/${id}/hint`),
  listGames: () => request<GameSummary[]>('GET', '/games'),
  /** `color` (lato giocato dall'utente) è un'estensione opzionale accettata dal backend; default "white". */
  importPgn: (pgn: string, color?: 'white' | 'black') =>
    request<{ id: number | string }>('POST', '/games/import', color ? { pgn, color } : { pgn }),

  // analisi
  analyzeGame: (id: string | number) => request<AnalyzeResponse>('POST', `/games/${id}/analyze`),
  getAnalysis: (id: string | number) => request<GameAnalysis>('GET', `/games/${id}/analysis`),
  analyzePosition: (fen: string, multipv = 1) =>
    request<PositionAnalysis>('POST', '/analysis/position', { fen, multipv }),

  // studio
  getStudyExams: () => request<StudyExams>('GET', '/study/exams'),
  getStudyExam: (exam: string) => request<StudyExamDetail>('GET', `/study/exams/${encodeURIComponent(exam)}`),
  getStudyPath: (exam: string) => request<StudyPath>('GET', `/study/exams/${encodeURIComponent(exam)}/path`),
  setLessonDone: (exam: string, topic: string, done: boolean) =>
    request<StudyPath>('PUT', `/study/exams/${encodeURIComponent(exam)}/lessons/${encodeURIComponent(topic)}`, { done }),
  nextStudyQuestion: (exam: string, topic?: string) =>
    request<StudyQuestion>('GET', `/study/exams/${encodeURIComponent(exam)}/next` + qs({ topic })),
  answerStudyQuestion: (id: number, body: { choice: number; time_ms: number }) =>
    request<StudyAnswerResult>('POST', `/study/questions/${id}/answer`, body),
  flagStudyQuestion: (id: number) =>
    request<{ flagged: boolean; rating_restored: number }>('POST', `/study/questions/${id}/flag`),

  // Claude
  getClaudeSettings: () => request<ClaudeSettings>('GET', '/settings/claude'),
  updateClaudeSettings: (api_key: string) => request<ClaudeSettings>('PUT', '/settings/claude', { api_key }),

  // motore
  getEngineStatus: () => request<EngineStatus>('GET', '/engine/status'),
  updateEngineSettings: (body: EngineSettings) => request<EngineStatus>('PUT', '/engine/settings', body),
}
