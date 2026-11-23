import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { Card, ErrorBox, Loading, PageHeader } from '../components/ui'
import { errMsg, useAsync } from '../hooks/useAsync'
import { resultText } from '../lib/chess'

const fmtDate = (d: string) => {
  const dt = new Date(d)
  return isNaN(dt.getTime()) ? d : dt.toLocaleString('it-IT', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function AnalysisList() {
  const nav = useNavigate()
  const games = useAsync(() => api.listGames())
  const [pgn, setPgn] = useState('')
  const [side, setSide] = useState<'white' | 'black'>('white')
  const [importing, setImporting] = useState(false)
  const [importError, setImportError] = useState<string | null>(null)

  const doImport = async () => {
    setImporting(true)
    setImportError(null)
    try {
      const { id } = await api.importPgn(pgn.trim(), side)
      setPgn('')
      nav(`/analisi/${id}?auto=1`)
    } catch (e) {
      setImportError(errMsg(e))
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="page">
      <PageHeader title="Revisione partite" subtitle="Analizza le tue partite con il motore e scopri dove hai sbagliato." />

      <div className="grid-2 wide-left">
        <Card title="Le tue partite" actions={<button className="btn ghost small" onClick={games.reload}>↻ Aggiorna</button>}>
          {games.error && <ErrorBox error={games.error} onRetry={games.reload} />}
          {games.loading && !games.data && <Loading />}
          {games.data && games.data.length === 0 && <div className="empty">Nessuna partita: gioca contro il motore o importa un PGN.</div>}
          {games.data && games.data.length > 0 && (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Data</th>
                    <th>Avversario</th>
                    <th>Colore</th>
                    <th>Risultato</th>
                    <th>Precisione</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {games.data.map((g) => {
                    const color = g.color === 'black' ? 'black' : 'white'
                    const r = g.status === 'active' ? { text: 'In corso', tone: 'none' } : resultText(g.result, color)
                    return (
                      <tr key={g.id}>
                        <td className="nowrap">{fmtDate(g.created_at)}</td>
                        <td>{g.bot_elo ? `Motore ${g.bot_elo}` : <span className="muted">Importata</span>}</td>
                        <td>
                          <span className={`turn-dot ${color}`} /> {color === 'white' ? 'Bianco' : 'Nero'}
                        </td>
                        <td>
                          <span className={`pill ${r.tone}`}>{r.text}</span> <span className="muted small">{g.result ?? ''}</span>
                        </td>
                        <td>{g.analyzed && g.accuracy != null ? `${Math.round(g.accuracy)}%` : <span className="muted">—</span>}</td>
                        <td className="right nowrap">
                          {g.status === 'active' ? (
                            <button className="btn small" onClick={() => nav(`/gioca/${g.id}`)}>
                              Continua
                            </button>
                          ) : g.analyzed ? (
                            <button className="btn small primary" onClick={() => nav(`/analisi/${g.id}`)}>
                              Rivedi
                            </button>
                          ) : (
                            <button className="btn small" onClick={() => nav(`/analisi/${g.id}?auto=1`)}>
                              Analizza
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="Importa PGN">
          <p className="muted small">Incolla una partita giocata altrove (es. Lichess o Chess.com) per analizzarla.</p>
          <textarea
            className="pgn-input"
            value={pgn}
            onChange={(e) => setPgn(e.target.value)}
            placeholder={'[Event "?"]\n\n1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 ...'}
            rows={10}
            spellCheck={false}
          />
          <div className="import-side">
            <span className="field-label">Hai giocato con</span>
            <div className="segmented small">
              <button className={side === 'white' ? 'active' : ''} onClick={() => setSide('white')}>
                ♔ Bianco
              </button>
              <button className={side === 'black' ? 'active' : ''} onClick={() => setSide('black')}>
                ♚ Nero
              </button>
            </div>
          </div>
          {importError && <ErrorBox error={importError} />}
          <button className="btn primary" disabled={!pgn.trim() || importing} onClick={doImport}>
            {importing ? 'Importazione…' : 'Importa e analizza'}
          </button>
        </Card>
      </div>
    </div>
  )
}
