import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { Arrow } from 'react-chessboard'
import { api, type Puzzle, type PuzzleAttemptResult, type PuzzleMode } from '../api/client'
import Board from '../components/Board'
import { Card, ErrorBox, Loading, PageHeader } from '../components/ui'
import { useAsync, errMsg } from '../hooks/useAsync'
import { isMateAfter, parseUci, tryMove, turnColor, type Orientation } from '../lib/chess'

type Status = 'loading' | 'opponent' | 'playing' | 'solved' | 'failed' | 'error'

const MODES: { v: PuzzleMode; label: string }[] = [
  { v: 'normal', label: 'Normale' },
  { v: 'warmup', label: 'Riscaldamento' },
  { v: 'focus', label: 'Mirato (punti deboli)' },
]

function readNum(key: string): number {
  try {
    return Number(localStorage.getItem(key) ?? 0) || 0
  } catch {
    return 0
  }
}
function writeNum(key: string, v: number) {
  try {
    localStorage.setItem(key, String(v))
  } catch {
    /* ignora */
  }
}

/** Variazione di rating con segno esplicito (evita "+-3" o "-0"). */
function fmtDelta(d: number): string {
  const r = Math.round(d)
  return r > 0 ? `+${r}` : r < 0 ? `${r}` : '±0'
}

export default function PuzzlePage() {
  const [params, setParams] = useSearchParams()
  const mode = (params.get('mode') as PuzzleMode) || 'normal'
  const theme = params.get('theme') || ''

  const themes = useAsync(() => api.getPuzzleThemes())

  const [puzzle, setPuzzle] = useState<Puzzle | null>(null)
  const [fen, setFen] = useState('')
  const [step, setStep] = useState(1)
  const [status, setStatus] = useState<Status>('loading')
  const [lastMove, setLastMove] = useState<{ from: string; to: string } | null>(null)
  const [orientation, setOrientation] = useState<Orientation>('white')
  const [hintStage, setHintStage] = useState(0)
  const [hintsUsed, setHintsUsed] = useState(0)
  const [result, setResult] = useState<PuzzleAttemptResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [failFen, setFailFen] = useState<string | null>(null)
  const [streak, setStreak] = useState(() => readNum('chessai-streak'))
  const [bestStreak, setBestStreak] = useState(() => readNum('chessai-best-streak'))
  const [showingSolution, setShowingSolution] = useState(false)

  const gen = useRef(0)
  const startedAt = useRef(0)
  const timers = useRef<number[]>([])

  const later = (fn: () => void, ms: number) => {
    const g = gen.current
    timers.current.push(window.setTimeout(() => g === gen.current && fn(), ms))
  }

  const load = useCallback(async () => {
    gen.current++
    timers.current.forEach(clearTimeout)
    timers.current = []
    const g = gen.current
    setStatus('loading')
    setResult(null)
    setError(null)
    setHintStage(0)
    setHintsUsed(0)
    setFailFen(null)
    setShowingSolution(false)
    setLastMove(null)
    try {
      const p = await api.nextPuzzle({ mode, theme: theme || undefined })
      if (g !== gen.current) return
      setPuzzle(p)
      setFen(p.fen)
      setStep(1)
      // il giocatore muove col colore opposto a chi muove nella FEN iniziale
      setOrientation(turnColor(p.fen) === 'white' ? 'black' : 'white')
      setStatus('opponent')
      timers.current.push(
        window.setTimeout(() => {
          if (g !== gen.current) return
          const r = tryMove(p.fen, p.moves[0])
          if (!r) {
            setStatus('error')
            setError('Puzzle non valido (prima mossa illegale).')
            return
          }
          setFen(r.fen)
          setLastMove(parseUci(p.moves[0]))
          setStatus('playing')
          startedAt.current = performance.now()
        }, 700),
      )
    } catch (e) {
      if (g !== gen.current) return
      setStatus('error')
      setError(errMsg(e))
    }
  }, [mode, theme])

  useEffect(() => {
    load()
    const t = timers
    return () => {
      gen.current++
      t.current.forEach(clearTimeout)
    }
  }, [load])

  const submit = async (success: boolean) => {
    if (!puzzle) return
    const newStreak = success ? streak + 1 : 0
    setStreak(newStreak)
    writeNum('chessai-streak', newStreak)
    if (newStreak > bestStreak) {
      setBestStreak(newStreak)
      writeNum('chessai-best-streak', newStreak)
    }
    try {
      const r = await api.attemptPuzzle(puzzle.id, {
        success,
        time_ms: Math.round(performance.now() - startedAt.current),
        hints_used: hintsUsed,
      })
      setResult(r)
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const onMove = (uci: string): boolean => {
    if (!puzzle || status !== 'playing') return false
    const expected = puzzle.moves[step]
    const isLast = step >= puzzle.moves.length - 1
    const played = tryMove(fen, uci)
    if (!played) return false
    setHintStage(0)
    const correct = uci === expected || (isLast && isMateAfter(fen, uci))
    if (!correct) {
      setFailFen(fen)
      setFen(played.fen)
      setLastMove(parseUci(uci))
      setStatus('failed')
      submit(false)
      return true
    }
    setFen(played.fen)
    setLastMove(parseUci(uci))
    if (isLast) {
      setStatus('solved')
      submit(true)
      return true
    }
    // risposta automatica dell'avversario
    const reply = puzzle.moves[step + 1]
    setStatus('opponent')
    later(() => {
      const r = tryMove(played.fen, reply)
      if (!r) return
      setFen(r.fen)
      setLastMove(parseUci(reply))
      const next = step + 2
      setStep(next)
      if (next >= puzzle.moves.length) {
        setStatus('solved')
        submit(true)
      } else setStatus('playing')
    }, 450)
    return true
  }

  const hint = () => {
    if (status !== 'playing' || !puzzle) return
    setHintStage((s) => Math.min(2, s + 1))
    if (hintStage < 2) setHintsUsed((h) => h + 1)
  }

  const showSolution = () => {
    if (!puzzle || !failFen) return
    setShowingSolution(true)
    let f = failFen
    setFen(f)
    puzzle.moves.slice(step).forEach((m, i) => {
      later(() => {
        const r = tryMove(f, m)
        if (!r) return
        f = r.fen
        setFen(r.fen)
        setLastMove(parseUci(m))
      }, 500 + i * 650)
    })
  }

  const expected = puzzle && status === 'playing' ? parseUci(puzzle.moves[step]) : null
  const highlight = expected && hintStage >= 1 ? [expected.from] : []
  const arrows: Arrow[] = expected && hintStage >= 2 ? [{ startSquare: expected.from, endSquare: expected.to, color: 'rgba(46,204,113,0.85)' }] : []

  const setFilter = (k: 'mode' | 'theme', v: string) => {
    const next = new URLSearchParams(params)
    if (v) next.set(k, v)
    else next.delete(k)
    setParams(next)
  }

  const toMoveText = orientation === 'white' ? 'il Bianco' : 'il Nero'

  return (
    <div className="page">
      <PageHeader title="Tattica" subtitle="Trova la mossa migliore: gioca la combinazione completa.">
        <div className="streak" title={`Record: ${bestStreak}`}>
          🔥 <b>{streak}</b> <span className="muted small">serie · record {bestStreak}</span>
        </div>
      </PageHeader>

      <div className="board-layout">
        <div className="board-col">
          {fen ? (
            <Board id="puzzle" fen={fen} orientation={orientation} movableColor={status === 'playing' ? orientation : null} onMove={onMove} lastMove={lastMove} highlight={highlight} arrows={arrows} />
          ) : (
            <div className="board-placeholder">{status === 'error' ? null : <Loading />}</div>
          )}
        </div>

        <div className="side-col">
          <Card>
            {error && <ErrorBox error={error} onRetry={status === 'error' ? load : undefined} />}
            {puzzle && (
              <div className="puzzle-meta">
                <span className="badge">Puzzle {puzzle.rating}</span>
                {puzzle.themes_it.length > 0 && (status === 'solved' || status === 'failed') && puzzle.themes_it.map((t) => <span className="chip" key={t}>{t}</span>)}
              </div>
            )}

            {status === 'loading' && <Loading text="Carico il puzzle…" />}
            {status === 'opponent' && <div className="status-line">L'avversario sta muovendo…</div>}
            {status === 'playing' && (
              <div className="status-line">
                <span className={`turn-dot ${orientation}`} /> Tocca a te: muove <b>{toMoveText}</b>. Trova la mossa migliore!
              </div>
            )}
            {status === 'solved' && (
              <div className="result-banner win">
                <strong>Risolto! 🎉</strong>
                {result && <span className={`delta ${Math.round(result.delta) < 0 ? 'neg' : 'pos'}`}>{fmtDelta(result.delta)}</span>}
              </div>
            )}
            {status === 'failed' && (
              <div className="result-banner loss">
                <strong>Mossa sbagliata</strong>
                {result && <span className="delta neg">{fmtDelta(result.delta)}</span>}
              </div>
            )}
            {result && (
              <>
                <p className="explanation">{result.explanation_it}</p>
                <p className="muted small">Nuovo rating puzzle: <b>{Math.round(result.puzzle_rating)}</b></p>
              </>
            )}

            <div className="btn-row">
              {status === 'playing' && (
                <button className="btn" onClick={hint} disabled={hintStage >= 2}>
                  💡 {hintStage === 0 ? 'Suggerimento' : hintStage === 1 ? 'Mostra la mossa' : 'Suggerimento usato'}
                </button>
              )}
              {status === 'failed' && !showingSolution && (
                <button className="btn" onClick={showSolution}>
                  Mostra soluzione
                </button>
              )}
              {(status === 'solved' || status === 'failed' || status === 'error') && (
                <button className="btn primary" onClick={load}>
                  Prossimo →
                </button>
              )}
              {(status === 'playing' || status === 'opponent') && (
                <button className="btn ghost" onClick={load} title="Salta (non conta come tentativo)">
                  Salta
                </button>
              )}
            </div>
            {hintsUsed > 0 && status === 'playing' && <p className="muted small">Suggerimenti usati: {hintsUsed} (riducono il guadagno di rating)</p>}
          </Card>
          <Card title="Filtri">
            <div className="form-grid">
              <label>
                <span>Modalità</span>
                <select value={mode} onChange={(e) => setFilter('mode', e.target.value === 'normal' ? '' : e.target.value)}>
                  {MODES.map((m) => (
                    <option key={m.v} value={m.v}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Tema</span>
                <select value={theme} onChange={(e) => setFilter('theme', e.target.value)}>
                  <option value="">Tutti i temi</option>
                  {themes.data?.map((t) => (
                    <option key={t.theme} value={t.theme}>
                      {t.label_it} ({t.count})
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
