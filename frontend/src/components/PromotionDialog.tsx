import { defaultPieces } from 'react-chessboard'
import type { Orientation } from '../lib/chess'

const CHOICES: { p: string; label: string }[] = [
  { p: 'q', label: 'Donna' },
  { p: 'r', label: 'Torre' },
  { p: 'b', label: 'Alfiere' },
  { p: 'n', label: 'Cavallo' },
]

export default function PromotionDialog({
  color,
  onSelect,
  onCancel,
}: {
  color: Orientation
  onSelect: (piece: string) => void
  onCancel: () => void
}) {
  const prefix = color === 'white' ? 'w' : 'b'
  return (
    <div className="promo-overlay" onClick={onCancel} role="dialog" aria-label="Promozione">
      <div className="promo-box" onClick={(e) => e.stopPropagation()}>
        <div className="promo-title">Promuovi a…</div>
        <div className="promo-choices">
          {CHOICES.map(({ p, label }) => {
            const Piece = defaultPieces[prefix + p.toUpperCase()]
            return (
              <button key={p} className="promo-btn" title={label} onClick={() => onSelect(p)}>
                <Piece />
                <span>{label}</span>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
