import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { Card, ErrorBox, Loading, PageHeader, ProgressBar } from '../components/ui'
import { useAsync } from '../hooks/useAsync'

export default function Home() {
  const exams = useAsync(() => api.getStudyExams())
  const chess = useAsync(() => api.getProfile())

  return (
    <div className="page">
      <PageHeader title="LearnAI" subtitle="Il tuo allenatore personale: scacchi, CFA e GMAT con lo stesso metodo adattivo." />

      {exams.data && !exams.data.claude_enabled && (
        <div className="error-box">
          <span>
            Per generare le domande di CFA e GMAT serve una chiave API Anthropic: aggiungila in{' '}
            <Link to="/impostazioni" className="link">Impostazioni</Link>.
          </span>
        </div>
      )}

      <div className="subject-grid">
        <Card title="♞ Scacchi" className="subject-card">
          {chess.error && <ErrorBox error={chess.error} onRetry={chess.reload} />}
          {chess.loading && !chess.data && <Loading />}
          {chess.data && (
            <>
              <div className="subject-rating">
                <span className="stat-value">{Math.round(chess.data.game_rating)}</span>
                <span className="muted small">Elo partite · puzzle {Math.round(chess.data.puzzle_rating)}</span>
              </div>
              <ProgressBar value={chess.data.progress_pct} label={`Verso ${chess.data.target_elo}`} />
              <p className="muted small">{chess.data.level_name}</p>
            </>
          )}
          <div className="btn-row">
            <Link to="/scacchi" className="btn primary">Percorso</Link>
            <Link to="/tattica" className="btn">Tattica</Link>
          </div>
        </Card>

        {exams.error && <ErrorBox error={exams.error} onRetry={exams.reload} />}
        {exams.loading && !exams.data && <Loading />}
        {exams.data?.exams.map((e) => (
          <Card key={e.id} title={`📘 ${e.label}`} className="subject-card">
            <div className="subject-rating">
              <span className="stat-value">{e.rating}</span>
              <span className="muted small">
                rating · {e.answered} risposte
                {e.accuracy !== null && ` · ${Math.round(e.accuracy * 100)}% corrette`}
              </span>
            </div>
            <ProgressBar value={e.progress_pct} label={`Verso ${e.target_rating} (livello da esame)`} />
            <p className="muted small">{e.description}</p>
            <div className="btn-row">
              <Link to={`/studio/${e.id}`} className="btn primary">Studia</Link>
              <span className="muted small">{e.bank_unseen} domande pronte</span>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
