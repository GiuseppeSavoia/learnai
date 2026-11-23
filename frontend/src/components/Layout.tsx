import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { USE_MOCK } from '../api/client'

interface NavLinkItem {
  to: string
  label: string
  icon: string
  end?: boolean
}

const NAV: { section?: string; items: NavLinkItem[] }[] = [
  { items: [{ to: '/', label: 'Home', icon: '◎', end: true }] },
  {
    section: 'Studio',
    items: [
      { to: '/studio/cfa1', label: 'CFA Livello I', icon: 'Ⅰ' },
      { to: '/studio/cfa2', label: 'CFA Livello II', icon: 'Ⅱ' },
      { to: '/studio/cfa3', label: 'CFA Livello III', icon: 'Ⅲ' },
      { to: '/studio/gmat', label: 'GMAT', icon: 'G' },
    ],
  },
  {
    section: 'Scacchi',
    items: [
      { to: '/scacchi', label: 'Il mio percorso', icon: '♚' },
      { to: '/tattica', label: 'Tattica', icon: '⚡' },
      { to: '/gioca', label: 'Gioca', icon: '♞' },
      { to: '/analisi', label: 'Analisi', icon: '📈' },
    ],
  },
  { items: [{ to: '/impostazioni', label: 'Impostazioni', icon: '⚙' }] },
]

type Theme = 'dark' | 'light'

function initialTheme(): Theme {
  try {
    const t = localStorage.getItem('chessai-theme')
    if (t === 'light' || t === 'dark') return t
  } catch {
    /* storage non disponibile */
  }
  return 'dark'
}

export default function Layout() {
  const [theme, setTheme] = useState<Theme>(initialTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('chessai-theme', theme)
    } catch {
      /* ignora */
    }
  }, [theme])

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-logo">✦</span>
          <span className="brand-name">
            Learn<b>AI</b>
          </span>
        </div>
        <nav className="nav">
          {NAV.map((group, gi) => (
            <div key={gi} className="nav-group">
              {group.section && <span className="nav-section">{group.section}</span>}
              {group.items.map((n) => (
                <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                  <span className="nav-icon">{n.icon}</span>
                  <span className="nav-label">{n.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-foot">
          {USE_MOCK && <span className="badge warn" title="Dati finti: VITE_MOCK=1">MOCK</span>}
          <button
            className="btn ghost small theme-toggle"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            title="Cambia tema"
          >
            <span>{theme === 'dark' ? '☀' : '☾'}</span>
            <span className="nav-label">{theme === 'dark' ? 'Chiaro' : 'Scuro'}</span>
          </button>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
