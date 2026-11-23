import { useEffect, useState } from 'react'
import { api, type EngineProfile } from '../api/client'
import { Card, ErrorBox, Loading, PageHeader } from '../components/ui'
import { errMsg, useAsync } from '../hooks/useAsync'

const PROFILES: { v: EngineProfile; label: string; desc: string }[] = [
  { v: 'eco', label: 'Risparmio', desc: '1 thread, 64 MB, tempi dimezzati. Ideale a batteria.' },
  { v: 'balanced', label: 'Bilanciato', desc: '2 thread, 128 MB. Consigliato.' },
  { v: 'performance', label: 'Prestazioni', desc: '6 thread, 256 MB. Analisi più rapide e profonde.' },
]

export default function Settings() {
  const engine = useAsync(() => api.getEngineStatus())
  const profile = useAsync(() => api.getProfile())
  const [engineBusy, setEngineBusy] = useState(false)
  const [engineErr, setEngineErr] = useState<string | null>(null)

  const [target, setTarget] = useState('')
  const [initial, setInitial] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    if (profile.data) setTarget(String(profile.data.target_elo))
  }, [profile.data])

  const setProfileEngine = async (p: EngineProfile) => {
    setEngineBusy(true)
    setEngineErr(null)
    try {
      engine.setData(await api.updateEngineSettings({ profile: p }))
    } catch (e) {
      setEngineErr(errMsg(e))
    } finally {
      setEngineBusy(false)
    }
  }

  const saveProfile = async () => {
    setSaving(true)
    setSaveMsg(null)
    const body: { target_elo?: number; initial_rating?: number } = {}
    const t = Number(target)
    if (target && t !== profile.data?.target_elo) body.target_elo = t
    if (initial) body.initial_rating = Number(initial)
    try {
      profile.setData(await api.updateProfile(body))
      setInitial('')
      setSaveMsg({ ok: true, text: 'Profilo aggiornato.' })
    } catch (e) {
      setSaveMsg({ ok: false, text: errMsg(e) })
    } finally {
      setSaving(false)
    }
  }

  const e = engine.data
  const targetNum = Number(target)
  const initialNum = Number(initial)
  const invalid =
    (target !== '' && (isNaN(targetNum) || targetNum < 800 || targetNum > 3000)) ||
    (initial !== '' && (isNaN(initialNum) || initialNum < 400 || initialNum > 2800))

  return (
    <div className="page">
      <PageHeader title="Impostazioni" subtitle="Claude, motore degli scacchi, consumo di CPU e obiettivi." />

      <div className="grid-2">
        <Card title="Motore (Stockfish)" actions={<button className="btn ghost small" onClick={engine.reload}>↻</button>}>
          {engine.error && <ErrorBox error={engine.error} onRetry={engine.reload} />}
          {engine.loading && !e && <Loading />}
          {e && (
            <>
              <div className="engine-status">
                <div>
                  <span className="muted small">Stato</span>
                  <span>
                    {!e.available ? (
                      <span className="pill loss">Non trovato</span>
                    ) : e.running ? (
                      <span className="pill win">In esecuzione</span>
                    ) : (
                      <span className="pill none">In attesa (0% CPU)</span>
                    )}
                  </span>
                </div>
                <div>
                  <span className="muted small">Versione</span>
                  <span>{e.version ?? '—'}</span>
                </div>
                <div>
                  <span className="muted small">Thread</span>
                  <span>
                    {e.threads} <span className="muted small">/ {e.cpu_count} CPU</span>
                  </span>
                </div>
                <div>
                  <span className="muted small">Hash</span>
                  <span>{e.hash_mb} MB</span>
                </div>
                <div className="span-2">
                  <span className="muted small">Percorso</span>
                  <code className="small">{e.path ?? '—'}</code>
                </div>
              </div>
              {!e.available && <p className="muted small">Installa Stockfish con <code>brew install stockfish</code> e riavvia il backend.</p>}

              <span className="field-label">Profilo di consumo</span>
              <div className="profile-options">
                {PROFILES.map((p) => (
                  <button key={p.v} className={`profile-opt ${e.profile === p.v ? 'active' : ''}`} disabled={engineBusy} onClick={() => setProfileEngine(p.v)}>
                    <strong>{p.label}</strong>
                    <span className="muted small">{p.desc}</span>
                  </button>
                ))}
              </div>
              {engineErr && <ErrorBox error={engineErr} />}
            </>
          )}
        </Card>

        <ClaudeCard />

        <Card title="Profilo e obiettivo">
          {profile.error && <ErrorBox error={profile.error} onRetry={profile.reload} />}
          {profile.loading && !profile.data && <Loading />}
          {profile.data && (
            <div className="form-grid">
              <label>
                <span>Elo obiettivo</span>
                <input type="number" min={800} max={3000} step={50} value={target} onChange={(ev) => setTarget(ev.target.value)} />
                <span className="muted small">Predefinito: 2000.</span>
              </label>
              <label>
                <span>Rating iniziale stimato</span>
                <input type="number" min={400} max={2800} step={50} value={initial} placeholder={`attuale: ${Math.round(profile.data.game_rating)}`} onChange={(ev) => setInitial(ev.target.value)} />
                <span className="muted small">Reimposta la stima di partenza dei rating (es. il tuo Elo online).</span>
              </label>
              {invalid && <div className="error-box">Valori non validi (obiettivo 800–3000, rating 400–2800).</div>}
              {saveMsg && <div className={saveMsg.ok ? 'ok-box' : 'error-box'}>{saveMsg.text}</div>}
              <button className="btn primary" disabled={saving || invalid} onClick={saveProfile}>
                {saving ? 'Salvataggio…' : 'Salva'}
              </button>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

function ClaudeCard() {
  const status = useAsync(() => api.getClaudeSettings())
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const save = async (value: string) => {
    setBusy(true)
    setMsg(null)
    try {
      status.setData(await api.updateClaudeSettings(value))
      setKey('')
      setMsg({ ok: true, text: value ? 'Chiave salvata.' : 'Chiave rimossa.' })
    } catch (e) {
      setMsg({ ok: false, text: errMsg(e) })
    } finally {
      setBusy(false)
    }
  }

  const s = status.data
  return (
    <Card title="Claude (domande CFA e GMAT)">
      {status.error && <ErrorBox error={status.error} onRetry={status.reload} />}
      {status.loading && !s && <Loading />}
      {s && (
        <div className="form-grid">
          <p className="muted small">
            Claude genera le domande d'esame e le spiegazioni (e arricchisce le spiegazioni degli errori negli scacchi). Le domande
            generate restano sul tuo Mac: il costo a consumo si paga solo la prima volta. Modello: <code>{s.model}</code>.
          </p>
          <div>
            <span className="muted small">Stato </span>
            {s.enabled ? <span className="pill win">Attivo</span> : <span className="pill loss">Chiave mancante</span>}
          </div>
          {s.source === 'env' ? (
            <p className="muted small">
              La chiave arriva dalla variabile d'ambiente <code>ANTHROPIC_API_KEY</code>.
            </p>
          ) : (
            <>
              <label>
                <span>Chiave API Anthropic</span>
                <div className="api-key-row">
                  <input
                    type="password"
                    autoComplete="off"
                    placeholder={s.enabled ? '•••••••• (salvata)' : 'sk-ant-…'}
                    value={key}
                    onChange={(ev) => setKey(ev.target.value)}
                  />
                  <button className="btn primary" disabled={busy || !key.trim()} onClick={() => save(key)}>
                    Salva
                  </button>
                </div>
                <span className="muted small">Salvata solo nel database locale dell'app. La trovi su console.anthropic.com.</span>
              </label>
              {s.enabled && (
                <button className="btn ghost small" disabled={busy} onClick={() => save('')}>
                  Rimuovi chiave
                </button>
              )}
            </>
          )}
          {msg && <div className={msg.ok ? 'ok-box' : 'error-box'}>{msg.text}</div>}
        </div>
      )}
    </Card>
  )
}
