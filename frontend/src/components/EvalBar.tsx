import { formatEval, winPct, type Orientation } from '../lib/chess'

export default function EvalBar({ evalCp, orientation }: { evalCp: number | null; orientation: Orientation }) {
  const pct = evalCp === null ? 50 : winPct(evalCp)
  const label = formatEval(evalCp)
  const whiteAhead = (evalCp ?? 0) >= 0
  return (
    <div className={`evalbar ${orientation === 'black' ? 'flipped' : ''}`} title={`Valutazione: ${label}`}>
      <div className="evalbar-white" style={{ height: `${pct}%` }} />
      <span className={`evalbar-label ${whiteAhead ? 'on-white' : 'on-black'}`}>{label}</span>
    </div>
  )
}
