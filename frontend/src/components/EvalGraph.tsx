import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { MoveAnalysis } from '../api/client'
import { CLASS_META, formatEval, isError } from '../lib/chess'

interface Point {
  ply: number
  v: number
  raw: number
  label: string
  cls?: MoveAnalysis['classification']
}

const clamp = (cp: number) => Math.max(-800, Math.min(800, cp))

export default function EvalGraph({
  moves,
  current,
  onSelect,
}: {
  moves: MoveAnalysis[]
  current: number
  onSelect: (ply: number) => void
}) {
  const data: Point[] = [
    { ply: 0, v: clamp(moves[0]?.eval_before ?? 0), raw: moves[0]?.eval_before ?? 0, label: 'Inizio' },
    ...moves.map((m) => ({
      ply: m.ply,
      v: clamp(m.eval_after),
      raw: m.eval_after,
      label: `${Math.ceil(m.ply / 2)}${m.color === 'white' ? '.' : '...'}${m.san}`,
      cls: m.classification,
    })),
  ]

  return (
    <div className="evalgraph">
      <ResponsiveContainer width="100%" height={140}>
        <AreaChart
          data={data}
          margin={{ top: 6, right: 6, left: 6, bottom: 0 }}
          onClick={(s) => {
            const idx = s?.activeTooltipIndex
            if (idx !== undefined && idx !== null) onSelect(data[Number(idx)]?.ply ?? 0)
          }}
          style={{ cursor: 'pointer' }}
        >
          <defs>
            <linearGradient id="evalFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="50%" stopColor="var(--eval-white)" stopOpacity={0.95} />
              <stop offset="50%" stopColor="var(--eval-black)" stopOpacity={0.95} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="ply" hide />
          <YAxis domain={[-800, 800]} hide />
          <ReferenceLine y={0} stroke="var(--text-dim)" strokeWidth={1} />
          <ReferenceLine x={current} stroke="var(--accent)" strokeWidth={2} />
          <Tooltip
            cursor={{ stroke: 'var(--text-dim)' }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const p = payload[0].payload as Point
              return (
                <div className="chart-tip">
                  <strong>{p.label}</strong> {formatEval(p.raw)}
                  {p.cls && <span style={{ color: CLASS_META[p.cls].color }}> · {CLASS_META[p.cls].label}</span>}
                </div>
              )
            }}
          />
          <Area
            type="monotone"
            dataKey="v"
            baseValue={-800}
            stroke="var(--text-dim)"
            strokeWidth={1}
            fill="url(#evalFill)"
            isAnimationActive={false}
            dot={(props: { cx?: number; cy?: number; index?: number }) => {
              const p = data[props.index ?? 0]
              const key = `d${props.index}`
              if (!p?.cls || !isError(p.cls) || props.cx === undefined || props.cy === undefined) return <g key={key} />
              return <circle key={key} cx={props.cx} cy={props.cy} r={4} fill={CLASS_META[p.cls].color} stroke="var(--bg-elev)" strokeWidth={1.5} />
            }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
