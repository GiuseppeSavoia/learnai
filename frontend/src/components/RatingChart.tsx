import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { RatingPoint } from '../api/client'

const fmtDate = (d: string) => {
  const dt = new Date(d)
  return isNaN(dt.getTime()) ? d : dt.toLocaleDateString('it-IT', { day: '2-digit', month: 'short' })
}

export default function RatingChart({ history, target }: { history: RatingPoint[]; target: number }) {
  if (!history.length) return <div className="empty">Nessuno storico ancora: risolvi qualche puzzle o gioca una partita.</div>
  const values = history.flatMap((h) => [h.puzzle_rating, h.game_rating])
  const min = Math.floor((Math.min(...values) - 50) / 50) * 50
  const max = Math.ceil((Math.max(...values) + 50) / 50) * 50
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={history} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
        <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="date" tickFormatter={fmtDate} stroke="var(--text-dim)" fontSize={12} tickLine={false} axisLine={false} minTickGap={24} />
        <YAxis domain={[min, Math.max(max, min + 100)]} stroke="var(--text-dim)" fontSize={12} tickLine={false} axisLine={false} width={48} />
        {target <= max + 200 && <ReferenceLine y={target} stroke="var(--accent)" strokeDasharray="4 4" label={{ value: `Obiettivo ${target}`, fill: 'var(--accent)', fontSize: 11, position: 'insideTopRight' }} />}
        <Tooltip
          contentStyle={{ background: 'var(--bg-elev)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)' }}
          labelFormatter={(l) => fmtDate(String(l))}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line type="monotone" dataKey="puzzle_rating" name="Puzzle" stroke="var(--series-1)" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="game_rating" name="Partite" stroke="var(--series-2)" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}
