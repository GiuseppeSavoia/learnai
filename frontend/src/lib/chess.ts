import { Chess } from 'chess.js'
import type { Classification } from '../api/client'

export type Orientation = 'white' | 'black'

export interface UciMove {
  from: string
  to: string
  promotion?: string
}

export function parseUci(uci: string): UciMove {
  return { from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci.length > 4 ? uci[4] : undefined }
}

export const turnColor = (fen: string): Orientation => (fen.split(' ')[1] === 'b' ? 'black' : 'white')

/** Prova ad applicare una mossa UCI a una copia della posizione. Ritorna null se illegale. */
export function tryMove(fen: string, uci: string): { fen: string; san: string } | null {
  const c = new Chess(fen)
  try {
    const m = c.move(parseUci(uci))
    return { fen: c.fen(), san: m.san }
  } catch {
    return null
  }
}

export function isMateAfter(fen: string, uci: string): boolean {
  const c = new Chess(fen)
  try {
    c.move(parseUci(uci))
    return c.isCheckmate()
  } catch {
    return false
  }
}

export function uciToSan(fen: string, uci: string): string {
  return tryMove(fen, uci)?.san ?? uci
}

/** Formatta una valutazione in centipedoni (punto di vista del Bianco). */
export function formatEval(cp: number | null | undefined): string {
  if (cp === null || cp === undefined) return '–'
  if (Math.abs(cp) >= 9000) {
    const n = Math.max(1, 10000 - Math.abs(cp))
    return `${cp > 0 ? '' : '-'}M${n}`
  }
  const v = cp / 100
  return `${v > 0 ? '+' : ''}${v.toFixed(1)}`
}

/** Percentuale di vittoria del Bianco (formula Lichess). */
export function winPct(cp: number): number {
  const c = Math.max(-1000, Math.min(1000, cp))
  return 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * c)) - 1)
}

export interface ClassMeta {
  label: string
  symbol: string
  color: string
}

export const CLASS_META: Record<Classification, ClassMeta> = {
  best: { label: 'Migliore', symbol: '★', color: 'var(--c-best)' },
  excellent: { label: 'Ottima', symbol: '!', color: 'var(--c-excellent)' },
  good: { label: 'Buona', symbol: '✓', color: 'var(--c-good)' },
  book: { label: 'Teoria', symbol: '📖', color: 'var(--c-book)' },
  forced: { label: 'Forzata', symbol: '□', color: 'var(--c-forced)' },
  inaccuracy: { label: 'Imprecisione', symbol: '?!', color: 'var(--c-inaccuracy)' },
  mistake: { label: 'Errore', symbol: '?', color: 'var(--c-mistake)' },
  blunder: { label: 'Errore grave', symbol: '??', color: 'var(--c-blunder)' },
}

export const isError = (c: Classification) => c === 'inaccuracy' || c === 'mistake' || c === 'blunder'

export function resultText(result: string | null, userColor: Orientation): { text: string; tone: 'win' | 'loss' | 'draw' | 'none' } {
  if (!result) return { text: 'In corso', tone: 'none' }
  if (result === '1/2-1/2') return { text: 'Patta', tone: 'draw' }
  const whiteWon = result === '1-0'
  const userWon = (whiteWon && userColor === 'white') || (!whiteWon && userColor === 'black')
  return userWon ? { text: 'Vittoria', tone: 'win' } : { text: 'Sconfitta', tone: 'loss' }
}
