import { useEffect, useRef } from 'react'
import type { Classification } from '../api/client'
import { CLASS_META } from '../lib/chess'

export interface MoveItem {
  san: string
  classification?: Classification
}

/** Lista mosse a coppie. `current` è il numero di semimosse giocate (0 = posizione iniziale). */
export default function MoveList({
  moves,
  current,
  onSelect,
  startPly = 1,
  emptyText = 'Nessuna mossa',
}: {
  moves: MoveItem[]
  current?: number
  onSelect?: (ply: number) => void
  startPly?: number
  emptyText?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current?.querySelector('.mv.active') as HTMLElement | null
    if (el && ref.current) {
      const box = ref.current
      const top = el.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop
      if (top < box.scrollTop || top > box.scrollTop + box.clientHeight - el.clientHeight)
        box.scrollTo({ top: top - box.clientHeight / 2, behavior: 'smooth' })
    }
  }, [current, moves.length])

  const rows: { no: number; w?: { m: MoveItem; ply: number }; b?: { m: MoveItem; ply: number } }[] = []
  moves.forEach((m, i) => {
    const ply = startPly + i
    const no = Math.ceil(ply / 2)
    const isWhite = ply % 2 === 1
    let row = rows[rows.length - 1]
    if (!row || row.no !== no) {
      row = { no }
      rows.push(row)
    }
    if (isWhite) row.w = { m, ply }
    else row.b = { m, ply }
  })

  const cell = (c?: { m: MoveItem; ply: number }) => {
    if (!c) return <span className="mv empty">…</span>
    const meta = c.m.classification ? CLASS_META[c.m.classification] : null
    const cls = c.m.classification
    const showSym = !!cls && ['inaccuracy', 'mistake', 'blunder', 'excellent'].includes(cls)
    const colored = !!cls && cls !== 'book' && cls !== 'good' && cls !== 'forced'
    return (
      <button
        className={`mv ${current === c.ply ? 'active' : ''} ${onSelect ? 'clickable' : ''}`}
        onClick={() => onSelect?.(c.ply)}
        style={meta && colored ? { color: meta.color } : undefined}
        title={meta?.label}
      >
        {c.m.san}
        {meta && showSym && <span className="mv-sym">{meta.symbol}</span>}
      </button>
    )
  }

  return (
    <div className="movelist" ref={ref}>
      {rows.length === 0 && <div className="muted small pad">{emptyText}</div>}
      {rows.map((r) => (
        <div className="mv-row" key={r.no}>
          <span className="mv-no">{r.no}.</span>
          {cell(r.w)}
          {cell(r.b)}
        </div>
      ))}
    </div>
  )
}
