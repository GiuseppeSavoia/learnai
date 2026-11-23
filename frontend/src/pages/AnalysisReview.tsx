import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import type { Arrow } from 'react-chessboard'
import { api, ApiError, type GameAnalysis, type GameState, type MoveAnalysis } from '../api/client'
import Board from '../components/Board'
import EvalBar from '../components/EvalBar'
import EvalGraph from '../components/EvalGraph'
import MoveList from '../components/MoveList'
import { Card, ErrorBox, Loading, PageHeader, ProgressBar } from '../components/ui'
import { errMsg } from '../hooks/useAsync'
import { CLASS_META, formatEval, isError, parseUci, resultText, type Orientation } from '../lib/chess'

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
const COUNT_KEYS = ['blunder', 'mistake', 'inaccuracy'] as const

function moveLabel(m: MoveAnalysis) {
  return `${Math.ceil(m.ply / 2)}${m.color === 'white' ? '.' : '...'}${m.san}`
}

export default function AnalysisReview() {
  const { id = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const [game, setGame] = useState<GameState | null>(null)
  const [analysis, setAnalysis] = useState<GameAnalysis | null>(null)
  const [state, setState] = useState<'loading' | 'none' | 'running' | 'done' | 'error'>('loading')
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [ply, setPly] = useState(0)
  const [showAlt, setShowAlt] = useState(false)
  const pollRef = useRef<number | null>(null)

  const stopPoll = () => {
    if (pollRef.current) window.clearTimeout(pollRef.current)
    pollRef.current = null
  }

  const pollGen = useRef(0)

  const poll = useCallback(() => {
    stopPoll()
    const myGen = ++pollGen.current
    const tick = async () => {
      try {
        const a = await api.getAnalysis(id)
        if (myGen !== pollGen.current) return
        if (a.status === 'done') {
          setAnalysis(a)
          setState('done')
          return
        }
        if (a.status === 'error') {
          setState('error')
          setError(a.summary_it || 'Analisi fallita')
          return
        }
        setProgress(a.progress ?? 0)
        setState('running')
      } catch (e) {
        if (myGen !== pollGen.current) return
        // 404 subito dopo l'avvio: l'analisi potrebbe non essere ancora registrata
        if (!(e instanceof ApiError && e.status === 404)) {
          setState('error')
          setError(errMsg(e))
          return
        }
      }
      pollRef.current = window.setTimeout(tick, 1000)
    }
    tick()
  }, [id])

  const startAnalysis = useCallback(async () => {
    setError(null)
    setState('running')
    setProgress(0)
    try {
      const r = await api.analyzeGame(id)
      setProgress(r.progress ?? 0)
      poll()
    } catch (e) {
      setState('error')
      setError(errMsg(e))
    }
  }, [id, poll])

  // caricamento iniziale
  useEffect(() => {
    let alive = true
    setState('loading')
    setAnalysis(null)
    setPly(0)
    api.getGame(id).then((g) => alive && setGame(g)).catch(() => {})
    api
      .getAnalysis(id)
      .then((a) => {
        if (!alive) return
        if (a.status === 'done') {
          setAnalysis(a)
          setState('done')
        } else if (a.status === 'error') {
          setState('error')
          setError(a.summary_it || 'Analisi fallita')
        } else if (a.status === 'queued' || a.status === 'running') {
          setProgress(a.progress ?? 0)
          setState('running')
          poll()
        } else setState('none')
      })
      .catch((e) => {
        if (!alive) return
        if (e instanceof ApiError && e.status === 404) setState('none')
        else {
          setState('error')
          setError(errMsg(e))
        }
      })
    return () => {
      alive = false
      pollGen.current++
      stopPoll()
    }
  }, [id, poll])

  // avvio automatico (?auto=1)
  useEffect(() => {
    if (state === 'none' && params.get('auto') === '1') {
      const next = new URLSearchParams(params)
      next.delete('auto')
      setParams(next, { replace: true })
      startAnalysis()
    }
  }, [state, params, setParams, startAnalysis])

  const moves = analysis?.moves ?? []
  const n = moves.length

  const go = useCallback(
    (p: number) => {
      setPly(Math.max(0, Math.min(n, p)))
      setShowAlt(false)
    },
    [n],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT')) return
      if (e.key === 'ArrowLeft') go(ply - 1)
      else if (e.key === 'ArrowRight') go(ply + 1)
      else if (e.key === 'Home') go(0)
      else if (e.key === 'End') go(n)
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [go, ply, n])

  const userColor: Orientation = game?.color === 'black' ? 'black' : 'white'

  const nextError = () => {
    const m = moves.find((x) => x.ply > ply && x.color === userColor && isError(x.classification))
    if (m) go(m.ply)
  }
  const hasNextError = moves.some((x) => x.ply > ply && x.color === userColor && isError(x.classification))

  // ---------------- schermate di stato
  const header = (
    <PageHeader
      title="Revisione"
      subtitle={game ? `${game.bot_elo ? `Contro il motore ${game.bot_elo}` : 'Partita importata'} · ${resultText(game.result, userColor).text} ${game.result ?? ''}` : `Partita #${id}`}
    >
      <Link className="btn ghost" to="/analisi">
        ← Tutte le partite
      </Link>
    </PageHeader>
  )

  if (state !== 'done' || !analysis) {
    return (
      <div className="page">
        {header}
        <Card className="narrow">
          {state === 'loading' && <Loading />}
          {state === 'none' && (
            <div className="center-col">
              <p>Questa partita non è ancora stata analizzata.</p>
              <button className="btn primary big" onClick={startAnalysis}>
                Avvia analisi
              </button>
              <p className="muted small">L'analisi gira in background sul tuo computer (circa 150 ms per posizione).</p>
            </div>
          )}
          {state === 'running' && (
            <div className="center-col">
              <p>Analisi in corso… il motore sta esaminando ogni mossa.</p>
              <ProgressBar value={progress * 100} label={`${Math.round(progress * 100)}%`} />
            </div>
          )}
          {state === 'error' && <ErrorBox error={error ?? 'Errore'} onRetry={startAnalysis} />}
        </Card>
      </div>
    )
  }

  // ---------------- vista di revisione
  const cur = ply > 0 ? moves[ply - 1] : null
  const nextMove = moves[ply] ?? null
  const fen = showAlt && cur ? cur.fen_before : cur ? cur.fen_after : moves[0]?.fen_before ?? START_FEN
  const evalCp = cur ? cur.eval_after : moves[0]?.eval_before ?? 0

  let arrows: Arrow[] = []
  if (showAlt && cur) {
    const played = parseUci(cur.uci)
    arrows.push({ startSquare: played.from, endSquare: played.to, color: 'rgba(231,76,60,0.8)' })
    if (cur.best_move_uci) {
      const b = parseUci(cur.best_move_uci)
      arrows.push({ startSquare: b.from, endSquare: b.to, color: 'rgba(46,204,113,0.85)' })
    }
  } else if (nextMove?.best_move_uci) {
    const b = parseUci(nextMove.best_move_uci)
    arrows = [{ startSquare: b.from, endSquare: b.to, color: 'rgba(52,152,219,0.8)' }]
  }

  const lastMove = cur && !showAlt ? parseUci(cur.uci) : null
  const meta = cur ? CLASS_META[cur.classification] : null
  const userCounts = (cls: string) => moves.filter((m) => m.color === userColor && m.classification === cls).length
  const oppCounts = (cls: string) => moves.filter((m) => m.color !== userColor && m.classification === cls).length

  return (
    <div className="page">
      {header}

      <div className="board-layout">
        <div className="board-col compact">
          <div className="board-with-eval">
            <EvalBar evalCp={evalCp} orientation={userColor} />
            <Board id="review" fen={fen} orientation={userColor} lastMove={lastMove} arrows={arrows} animationMs={150} />
          </div>
          <div className="nav-buttons">
            <button className="btn" onClick={() => go(0)} title="Inizio (Home)">⏮</button>
            <button className="btn" onClick={() => go(ply - 1)} title="Indietro (←)">◀</button>
            <span className="ply-indicator">
              {ply}/{n}
            </span>
            <button className="btn" onClick={() => go(ply + 1)} title="Avanti (→)">▶</button>
            <button className="btn" onClick={() => go(n)} title="Fine (End)">⏭</button>
            <button className="btn primary" onClick={nextError} disabled={!hasNextError} title="Salta al prossimo errore del tuo colore">
              Prossimo errore ⤼
            </button>
          </div>
          <Card className="graph-card">
            <EvalGraph moves={moves} current={ply} onSelect={go} />
          </Card>
        </div>

        <div className="side-col">
          <Card>
            <div className="accuracy-row">
              {(['white', 'black'] as const).map((c) => {
                const acc = c === 'white' ? analysis.accuracy_white : analysis.accuracy_black
                return (
                  <div key={c} className={`accuracy ${c === userColor ? 'mine' : ''}`}>
                    <span className="muted small">
                      <span className={`turn-dot ${c}`} /> {c === 'white' ? 'Bianco' : 'Nero'} {c === userColor ? '(tu)' : ''}
                    </span>
                    <span className="accuracy-val">{acc != null ? `${Math.round(acc)}%` : '—'}</span>
                    <span className="muted small">precisione</span>
                  </div>
                )
              })}
            </div>
            <div className="counts">
              {COUNT_KEYS.map((k) => (
                <div key={k} className="count" style={{ color: CLASS_META[k].color }}>
                  <b>{userCounts(k)}</b>
                  <span>
                    {CLASS_META[k].symbol} {CLASS_META[k].label}
                  </span>
                  <span className="muted small">avv. {oppCounts(k)}</span>
                </div>
              ))}
            </div>
            {analysis.summary_it && <p className="summary">{analysis.summary_it}</p>}
          </Card>

          <Card className="explain-card">
            {!cur && <p className="muted">Posizione iniziale. Usa ← → o clicca una mossa per navigare.</p>}
            {cur && meta && (
              <>
                <div className="explain-head">
                  <span className="cls-badge" style={{ background: meta.color }}>
                    {meta.symbol}
                  </span>
                  <div>
                    <strong>{moveLabel(cur)}</strong> <span style={{ color: meta.color }}>{meta.label}</span>
                    <div className="muted small">
                      Valutazione {formatEval(cur.eval_before)} → {formatEval(cur.eval_after)}
                      {cur.cp_loss > 0 && ` · perdita ${(cur.cp_loss / 100).toFixed(1)}`}
                    </div>
                  </div>
                </div>
                {cur.explanation_it && <p className="explanation">{cur.explanation_it}</p>}
                {cur.best_move_san && cur.best_move_uci !== cur.uci && (
                  <div className="best-line">
                    <span className="muted small">Migliore:</span> <b>{cur.best_move_san}</b>
                    {cur.best_line_san.length > 1 && <span className="muted small"> ({cur.best_line_san.join(' ')})</span>}
                    <button className="btn small" onClick={() => setShowAlt((s) => !s)}>
                      {showAlt ? 'Torna alla partita' : 'Vedi sulla scacchiera'}
                    </button>
                  </div>
                )}
              </>
            )}
            {nextMove?.best_move_san && !showAlt && (
              <p className="muted small arrow-legend">
                <span className="legend-arrow" /> Freccia blu: mossa migliore del motore qui ({nextMove.best_move_san})
              </p>
            )}
          </Card>

          <Card title="Mosse">
            <MoveList moves={moves.map((m) => ({ san: m.san, classification: m.classification }))} current={ply} onSelect={go} />
          </Card>
        </div>
      </div>
    </div>
  )
}
