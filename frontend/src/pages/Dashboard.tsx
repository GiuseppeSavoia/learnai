import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { planItemLink } from '../lib/plan'
import { useAsync } from '../hooks/useAsync'
import { Card, ErrorBox, Loading, PageHeader, ProgressBar } from '../components/ui'
import RatingChart from '../components/RatingChart'

const KIND_ICON: Record<string, string> = { warmup: '🔥', puzzles: '🎯', game: '♞', review: '🔍' }
const KIND_CTA: Record<string, string> = { warmup: 'Inizia', puzzles: 'Allenati', game: 'Gioca', review: 'Rivedi' }

export default function Dashboard() {
  const nav = useNavigate()
  const profile = useAsync(() => api.getProfile())
  const plan = useAsync(() => api.getPlanToday())
  const weak = useAsync(() => api.getWeaknesses())
  // etichette italiane dei temi (i temi di focus arrivano come chiavi Lichess, es. "mateIn2")
  const themeList = useAsync(() => api.getPuzzleThemes())
  const themeLabel = (t: string) =>
    weak.data?.themes.find((w) => w.theme === t)?.label_it ?? themeList.data?.find((x) => x.theme === t)?.label_it ?? t

  const p = profile.data
  // forza usata dal backend per livello e progresso (fallback: il miglior rating)
  const best = p ? p.strength ?? Math.max(p.puzzle_rating, p.game_rating) : 0
  const doneCount = plan.data?.items.filter((i) => i.done).length ?? 0

  return (
    <div className="page">
      <PageHeader title="Il mio percorso" subtitle={p ? `Livello: ${p.level_name} · obiettivo ${p.target_elo} Elo` : 'Il tuo cammino verso il 2000'} />

      {profile.error && <ErrorBox error={profile.error} onRetry={profile.reload} />}
      {profile.loading && !p && <Loading />}

      {p && (
        <>
          <div className="stats-row">
            <div className="stat">
              <span className="stat-label">Rating puzzle</span>
              <span className="stat-value">{Math.round(p.puzzle_rating)}</span>
              <span className="stat-sub">± {Math.round(p.puzzle_rd)} · {p.puzzles_solved} risolti / {p.puzzles_failed} sbagliati</span>
            </div>
            <div className="stat">
              <span className="stat-label">Rating partite</span>
              <span className="stat-value">{Math.round(p.game_rating)}</span>
              <span className="stat-sub">± {Math.round(p.game_rd)} · {p.games_played} partite</span>
            </div>
            <div className="stat">
              <span className="stat-label">Livello</span>
              <span className="stat-value level">{p.level_name}</span>
              <span className="stat-sub">Mancano {Math.max(0, p.target_elo - Math.round(best))} punti all'obiettivo</span>
            </div>
          </div>

          <Card title="Progresso verso l'obiettivo">
            <ProgressBar value={p.progress_pct} label={`${Math.round(p.progress_pct)}%`} />
            <div className="progress-scale">
              <span>Inizio{p.initial_rating ? ` (${p.initial_rating})` : ''}</span>
              <span>
                Forza attuale {Math.round(best)} / {p.target_elo} Elo
              </span>
            </div>
          </Card>
        </>
      )}

      <div className="grid-2">
        <Card
          title="Piano di oggi"
          actions={plan.data && <span className="badge">{doneCount}/{plan.data.items.length} completati</span>}
        >
          {plan.error && <ErrorBox error={plan.error} onRetry={plan.reload} />}
          {plan.loading && !plan.data && <Loading />}
          {plan.data && (
            <>
              {plan.data.focus_themes.length > 0 && (
                <p className="muted small">
                  Temi su cui concentrarti oggi:{' '}
                  {plan.data.focus_themes.map((t) => (
                    <span className="chip" key={t}>
                      {themeLabel(t)}
                    </span>
                  ))}
                </p>
              )}
              <ul className="checklist">
                {plan.data.items.map((it) => (
                  <li key={it.id} className={it.done ? 'done' : ''}>
                    <span className="check">{it.done ? '✓' : ''}</span>
                    <span className="check-icon">{KIND_ICON[it.kind] ?? '•'}</span>
                    <div className="check-body">
                      <strong>
                        {it.title}
                        {typeof it.params?.count === 'number' && typeof it.params?.completed === 'number' && (
                          <span className="muted small"> · {it.params.completed}/{it.params.count}</span>
                        )}
                      </strong>
                      <span className="muted small">{it.description}</span>
                    </div>
                    <button className={`btn small ${it.done ? 'ghost' : 'primary'}`} onClick={() => nav(planItemLink(it, plan.data!))}>
                      {it.done ? 'Ripeti' : KIND_CTA[it.kind] ?? 'Vai'}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>

        <Card title="Punti deboli">
          {weak.error && <ErrorBox error={weak.error} onRetry={weak.reload} />}
          {weak.loading && !weak.data && <Loading />}
          {weak.data && weak.data.themes.length === 0 && <div className="empty">Ancora nessun dato: risolvi qualche puzzle.</div>}
          {weak.data && (
            <ul className="weak-list">
              {weak.data.themes.slice(0, 6).map((w) => {
                const rate = w.success_rate <= 1 ? w.success_rate * 100 : w.success_rate
                return (
                  <li key={w.theme}>
                    <div className="weak-head">
                      <span>{w.label_it}</span>
                      <span className="muted small">
                        {w.errors} errori su {w.attempts} · {Math.round(rate)}% riuscita
                      </span>
                    </div>
                    <div className="weak-bar">
                      <div className="weak-fill" style={{ width: `${rate}%`, background: rate < 60 ? 'var(--c-mistake)' : rate < 75 ? 'var(--c-inaccuracy)' : 'var(--c-good)' }} />
                    </div>
                    <button className="link small" onClick={() => nav(`/tattica?mode=focus&theme=${encodeURIComponent(w.theme)}`)}>
                      Allena →
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </Card>
      </div>

      <div className="grid-2">
        <Card title="Andamento del rating">{p && <RatingChart history={p.rating_history} target={p.target_elo} />}</Card>
        <Card title="Consigli">
          {plan.data && plan.data.tips.length > 0 ? (
            <ul className="tips">
              {plan.data.tips.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          ) : (
            !plan.loading && <div className="empty">Nessun consiglio per oggi.</div>
          )}
        </Card>
      </div>
    </div>
  )
}
