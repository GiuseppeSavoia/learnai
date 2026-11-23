import type { ReactNode } from 'react'

export function Card({ title, actions, children, className = '' }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          {title && <h2>{title}</h2>}
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  )
}

export function Loading({ text = 'Caricamento…' }: { text?: string }) {
  return (
    <div className="loading">
      <span className="spinner" /> {text}
    </div>
  )
}

export function ErrorBox({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="error-box">
      <span>⚠ {error}</span>
      {onRetry && (
        <button className="btn small" onClick={onRetry}>
          Riprova
        </button>
      )}
    </div>
  )
}

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {children && <div className="page-head-actions">{children}</div>}
    </div>
  )
}

export function ProgressBar({ value, label }: { value: number; label?: string }) {
  const v = Math.max(0, Math.min(100, value))
  return (
    <div className="progress" role="progressbar" aria-valuenow={Math.round(v)} aria-valuemin={0} aria-valuemax={100}>
      <div className="progress-fill" style={{ width: `${v}%` }} />
      {label && <span className="progress-label">{label}</span>}
    </div>
  )
}
