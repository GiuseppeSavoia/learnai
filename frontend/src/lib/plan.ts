import type { Plan, PlanItem } from '../api/client'

function str(v: unknown): string | undefined {
  if (typeof v === 'string' && v) return v
  if (typeof v === 'number') return String(v)
  return undefined
}

/** Traduce un elemento del piano in un percorso dell'app (params è libero nel contratto: gestiamo più chiavi). */
export function planItemLink(item: PlanItem, plan: Plan): string {
  const p = item.params ?? {}
  switch (item.kind) {
    case 'warmup':
      return `/tattica?mode=${str(p.mode) ?? 'warmup'}${str(p.theme) ? `&theme=${str(p.theme)}` : ''}`
    case 'puzzles': {
      const themes = Array.isArray(p.themes) ? (p.themes as string[]) : []
      const theme = str(p.theme) ?? themes[0] ?? plan.focus_themes[0]
      return `/tattica?mode=${str(p.mode) ?? 'focus'}${theme ? `&theme=${encodeURIComponent(theme)}` : ''}`
    }
    case 'game': {
      const elo = str(p.bot_elo) ?? str(p.elo)
      return `/gioca${elo ? `?elo=${elo}` : ''}`
    }
    case 'review': {
      const id = str(p.game_id) ?? str(p.id)
      return id ? `/analisi/${id}` : '/analisi'
    }
    default:
      return '/'
  }
}
