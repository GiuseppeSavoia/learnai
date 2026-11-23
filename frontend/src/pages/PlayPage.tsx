import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import type { Arrow } from 'react-chessboard'
import { api, type ColorChoice, type GameState, type Hint } from '../api/client'
import Board from '../components/Board'
import MoveList from '../components/MoveList'
import { Card, ErrorBox, Loading, PageHeader } from '../components/ui'
import { errMsg } from '../hooks/useAsync'
import { parseUci, resultText, tryMove } from '../lib/chess'

const COLORS: { v: ColorChoice; label: string; icon: string }[] = [
  { v: 'white', label: 'Bianco', icon: '♔' },
  { v: 'random', label: 'Casuale', icon: '⚄' },
  { v: 'black', label: 'Nero', icon: '♚' },
]

function eloLabel(elo: number) {
  if (elo < 1000) return 'Principiante'
  if (elo < 1300) return 'Base'
  if (elo < 1600) return 'Intermedio'
  if (elo < 1800) return 'Avanzato'
  if (elo < 2000) return 'Esperto'
  if (elo < 2400) return 'Maestro'
  return 'Fortissimo'
}

function NewGameSetup({ onStart }: { onStart: (elo: number, color: ColorChoice) => Promise<void> }) {
  const [params] = useSearchParams()
  const [elo, setElo] = useState<number | null>(params.get('elo') ? Number(params.get('elo')) : null)
  const [color, setColor] = useState<ColorChoice>('white')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [suggested, setSuggested] = useState<number | null>(null)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const plan = await api.getPlanToday()
        const it = plan.items.find((i) => i.kind === 'game')
        const v = Number(it?.params?.bot_elo ?? it?.params?.elo)
        if (v && alive) return setSuggested(Math.round(v))
      } catch {
        /* uso il profilo */
      }
      try {
        const p = await api.getProfile()
        if (alive) setSuggested(Math.round(p.game_rating + 100))
      } catch {
        if (alive) setSuggested(1200)
      }
    })()
    return () => {
      alive = false
    }
  }, [])

  const value = Math.max(600, Math.min(2800, elo ?? suggested ?? 1200))

  return (
    <Card title="Nuova partita" className="setup-card">
      <div className="setup">
        <label className="slider-label">
          <span>
            Forza del motore: <b className="elo-big">{value}</b> Elo <span className="muted small">({eloLabel(value)})</span>
          </span>
          <input type="range" min={600} max={2800} step={50} value={value} onChange={(e) => setElo(Number(e.target.value))} />
          <div className="slider-scale">
            <span>600</span>
            {suggested && (
              <button className="link small" onClick={() => setElo(suggested)}>
                Consigliato: {suggested}
              </button>
            )}
            <span>2800</span>
          </div>
        </label>

        <div>
          <span className="field-label">Il tuo colore</span>
          <div className="segmented">
            {COLORS.map((c) => (
              <button key={c.v} className={color === c.v ? 'active' : ''} onClick={() => setColor(c.v)}>
                <span className="seg-icon">{c.icon}</span> {c.label}
              </button>
            ))}
          </div>
        </div>

        {error && <ErrorBox error={error} />}
        <button
          className="btn primary big"
          disabled={busy}
          onClick={async () => {
            setBusy(true)
            setError(null)
            try {
              await onStart(value, color)
            } catch (e) {
              setError(errMsg(e))
              setBusy(false)
            }
          }}
        >
          {busy ? 'Avvio…' : 'Inizia partita'}
        </button>
      </div>
    </Card>
  )
}

export default function PlayPage() {
  const { id } = useParams()
  const nav = useNavigate()
  const [game, setGame] = useState<GameState | null>(null)
  const [fen, setFen] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [hint, setHint] = useState<Hint | null>(null)
  const [hintBusy, setHintBusy] = useState(false)
  const [confirmResign, setConfirmResign] = useState(false)
  const [optimistic, setOptimistic] = useState<{ san: string; uci: string } | null>(null)

  useEffect(() => {
    if (!id) {
      setGame(null)
      setFen(null)
      return
    }
    let alive = true
    setLoading(true)
    setError(null)
    api
      .getGame(id)
      .then((g) => {
        if (!alive) return
        setGame(g)
        setFen(g.fen)
      })
      .catch((e) => alive && setError(errMsg(e)))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [id])

  const start = async (elo: number, color: ColorChoice) => {
    const g = await api.newGame({ bot_elo: elo, color })
    setGame(g)
    setFen(g.fen)
    setHint(null)
    nav(`/gioca/${g.id}`, { replace: true })
  }

  const onMove = (uci: string): boolean => {
    if (!game || !fen || pending || game.status !== 'active') return false
    const local = tryMove(fen, uci)
    if (!local) return false
    const prevFen = fen
    setFen(local.fen)
    setOptimistic({ san: local.san, uci })
    setPending(true)
    setHint(null)
    setError(null)
    api
      .move(game.id, uci)
      .then((g) => {
        setGame(g)
        setFen(g.fen)
      })
      .catch((e) => {
        setFen(prevFen)
        setError(errMsg(e))
      })
      .finally(() => {
        setPending(false)
        setOptimistic(null)
      })
    return true
  }

  const askHint = async () => {
    if (!game) return
    setHintBusy(true)
    try {
      setHint(await api.hint(game.id))
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setHintBusy(false)
    }
  }

  const resign = async () => {
    if (!game) return
    setConfirmResign(false)
    try {
      const g = await api.resign(game.id)
      setGame(g)
      setFen(g.fen)
    } catch (e) {
      setError(errMsg(e))
    }
  }

  if (!id && !game)
    return (
      <div className="page">
        <PageHeader title="Partita contro il motore" subtitle="Scegli la forza del bot e il tuo colore." />
        <NewGameSetup onStart={start} />
      </div>
    )

  if (loading && !game)
    return (
      <div className="page">
        <Loading text="Carico la partita…" />
      </div>
    )

  if (!game || !fen)
    return (
      <div className="page">
        <PageHeader title="Partita contro il motore" />
        {error && <ErrorBox error={error} />}
        <button className="btn primary" onClick={() => nav('/gioca')}>
          Nuova partita
        </button>
      </div>
    )

  const movesSan = optimistic ? [...game.moves_san, optimistic.san] : game.moves_san
  const lastUci = optimistic?.uci ?? game.last_bot_move ?? game.moves_uci[game.moves_uci.length - 1] ?? null
  const lastMove = lastUci ? parseUci(lastUci) : null
  const finished = game.status === 'finished'
  const res = resultText(game.result, game.color)
  const hintArrow: Arrow[] = hint ? [{ startSquare: hint.uci.slice(0, 2), endSquare: hint.uci.slice(2, 4), color: 'rgba(46,204,113,0.85)' }] : []
  const myTurn = !finished && !pending && (fen.split(' ')[1] === 'w' ? 'white' : 'black') === game.color

  return (
    <div className="page">
      <PageHeader title="Partita contro il motore" subtitle={`Bot ${game.bot_elo} Elo · giochi con il ${game.color === 'white' ? 'Bianco' : 'Nero'}`}>
        <button className="btn ghost" onClick={() => nav('/gioca')}>
          + Nuova partita
        </button>
      </PageHeader>

      <div className="board-layout">
        <div className="board-col">
          <div className="player-tag top">
            <span className={`turn-dot ${game.color === 'white' ? 'black' : 'white'}`} /> Motore ({game.bot_elo})
            {pending && <span className="thinking">sta pensando…</span>}
          </div>
          <Board id="play" fen={fen} orientation={game.color} movableColor={myTurn ? game.color : null} onMove={onMove} lastMove={lastMove} arrows={hintArrow} />
          <div className="player-tag">
            <span className={`turn-dot ${game.color}`} /> Tu
          </div>
        </div>

        <div className="side-col">
          {finished && (
            <div className={`result-banner big ${res.tone}`}>
              <div>
                <strong>{res.text}</strong>
                <div className="small">
                  {game.result} {game.termination ? `· ${game.termination}` : ''}
                </div>
              </div>
              <button className="btn primary" onClick={() => nav(`/analisi/${game.id}?auto=1`)}>
                Analizza partita
              </button>
            </div>
          )}

          <Card title="Mosse">
            <MoveList moves={movesSan.map((san) => ({ san }))} current={movesSan.length} emptyText="Ancora nessuna mossa" />
          </Card>

          {error && <ErrorBox error={error} />}

          {!finished && (
            <Card>
              <div className="status-line">
                {pending ? 'Il motore sta rispondendo…' : myTurn ? 'Tocca a te.' : 'Turno del motore.'}
              </div>
              {hint && (
                <div className="hint-box">
                  <strong>💡 {hint.san}</strong>
                  <p>{hint.explanation_it}</p>
                </div>
              )}
              <div className="btn-row">
                <button className="btn" onClick={askHint} disabled={!myTurn || hintBusy}>
                  💡 {hintBusy ? 'Ci penso…' : 'Suggerimento'}
                </button>
                {confirmResign ? (
                  <>
                    <button className="btn danger" onClick={resign}>
                      Conferma abbandono
                    </button>
                    <button className="btn ghost" onClick={() => setConfirmResign(false)}>
                      Annulla
                    </button>
                  </>
                ) : (
                  <button className="btn ghost" onClick={() => setConfirmResign(true)}>
                    🏳 Abbandona
                  </button>
                )}
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
