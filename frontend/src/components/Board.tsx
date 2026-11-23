import { useMemo, useState, type CSSProperties } from 'react'
import { Chessboard, type Arrow } from 'react-chessboard'
import { Chess, type Square } from 'chess.js'
import PromotionDialog from './PromotionDialog'
import type { Orientation } from '../lib/chess'

export interface BoardProps {
  fen: string
  orientation: Orientation
  /** Se definito, l'utente può muovere solo pezzi di questo colore (e solo quando è il suo turno). */
  movableColor?: Orientation | null
  /** Ritorna true se la mossa è accettata. */
  onMove?: (uci: string) => boolean
  lastMove?: { from: string; to: string } | null
  highlight?: string[]
  arrows?: Arrow[]
  id?: string
  animationMs?: number
}

const LAST_MOVE: CSSProperties = { background: 'rgba(255, 213, 79, 0.42)' }
const SELECTED: CSSProperties = { background: 'rgba(95, 170, 255, 0.45)' }
const HINT: CSSProperties = { background: 'rgba(46, 204, 113, 0.5)', boxShadow: 'inset 0 0 0 3px rgba(46, 204, 113, 0.9)' }
const CHECK: CSSProperties = { background: 'radial-gradient(circle, rgba(255,60,60,0.85) 0%, rgba(255,60,60,0.35) 55%, transparent 75%)' }
const dot = (capture: boolean): CSSProperties =>
  capture
    ? { background: 'radial-gradient(circle, transparent 58%, rgba(20,20,20,0.32) 60%)' }
    : { background: 'radial-gradient(circle, rgba(20,20,20,0.28) 22%, transparent 24%)' }

export default function Board({
  fen,
  orientation,
  movableColor = null,
  onMove,
  lastMove,
  highlight = [],
  arrows = [],
  id = 'board',
  animationMs = 220,
}: BoardProps) {
  const [selected, setSelected] = useState<string | null>(null)
  const [selectedFen, setSelectedFen] = useState(fen)
  const [pendingPromo, setPendingPromo] = useState<{ from: string; to: string } | null>(null)

  // Reset della selezione quando cambia la posizione (pattern "adjust state during render").
  if (selectedFen !== fen) {
    setSelectedFen(fen)
    setSelected(null)
    setPendingPromo(null)
  }

  const chess = useMemo(() => {
    try {
      return new Chess(fen)
    } catch {
      return new Chess()
    }
  }, [fen])

  const turn: Orientation = chess.turn() === 'w' ? 'white' : 'black'
  const canMove = !!onMove && movableColor !== null && movableColor === turn && !chess.isGameOver()

  const targetsFrom = (sq: string | null) => {
    if (!sq) return []
    try {
      return chess.moves({ square: sq as Square, verbose: true })
    } catch {
      return []
    }
  }

  const ownPiece = (sq: string) => {
    const p = chess.get(sq as Square)
    return !!p && (p.color === 'w' ? 'white' : 'black') === turn
  }

  const attempt = (from: string, to: string): boolean => {
    if (!onMove) return false
    const moves = targetsFrom(from).filter((m) => m.to === to)
    if (!moves.length) return false
    if (moves.some((m) => m.promotion)) {
      setPendingPromo({ from, to })
      setSelected(null)
      return true
    }
    const ok = onMove(from + to)
    setSelected(null)
    return ok
  }

  const squareStyles = useMemo(() => {
    const s: Record<string, CSSProperties> = {}
    if (lastMove) {
      s[lastMove.from] = LAST_MOVE
      s[lastMove.to] = LAST_MOVE
    }
    if (chess.inCheck()) {
      for (const row of chess.board())
        for (const p of row) if (p && p.type === 'k' && p.color === chess.turn()) s[p.square] = CHECK
    }
    for (const h of highlight) s[h] = HINT
    if (selected) {
      s[selected] = SELECTED
      for (const m of targetsFrom(selected)) s[m.to] = { ...(s[m.to] ?? {}), ...dot(!!m.captured) }
    }
    return s
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chess, lastMove, highlight, selected])

  return (
    <div className="board-wrap">
      <Chessboard
        options={{
          id,
          position: fen,
          boardOrientation: orientation,
          animationDurationInMs: animationMs,
          arrows,
          squareStyles,
          allowDrawingArrows: true,
          clearArrowsOnPositionChange: true,
          darkSquareStyle: { backgroundColor: 'var(--sq-dark)' },
          lightSquareStyle: { backgroundColor: 'var(--sq-light)' },
          boardStyle: { borderRadius: 6, overflow: 'hidden', boxShadow: 'var(--shadow-board)' },
          allowDragging: canMove,
          canDragPiece: ({ piece }) => canMove && (piece.pieceType[0] === 'w' ? 'white' : 'black') === turn,
          onPieceDrag: ({ square }) => {
            if (canMove && square) setSelected(square)
          },
          onPieceDrop: ({ sourceSquare, targetSquare }) => {
            if (!canMove || !targetSquare || sourceSquare === targetSquare) return false
            return attempt(sourceSquare, targetSquare)
          },
          onSquareClick: ({ square }) => {
            if (!canMove) return
            if (selected && selected !== square && targetsFrom(selected).some((m) => m.to === square)) {
              attempt(selected, square)
              return
            }
            if (ownPiece(square)) setSelected(selected === square ? null : square)
            else setSelected(null)
          },
        }}
      />
      {pendingPromo && (
        <PromotionDialog
          color={turn}
          onSelect={(p) => {
            const { from, to } = pendingPromo
            setPendingPromo(null)
            onMove?.(from + to + p)
          }}
          onCancel={() => setPendingPromo(null)}
        />
      )}
    </div>
  )
}
