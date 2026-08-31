import { useState } from 'react'
import { api } from './api/client'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth'
import { SyncStatus } from './components/SyncStatus'
import { IconMenu, IconMonitor, IconMoon, IconSun } from './components/icons'
import { Banner } from './components/ui'
import { useResource } from './hooks/useApi'
import { useEventStream } from './hooks/useEventStream'
import { useTheme } from './hooks/useTheme'
import { isOnboardingDone } from './onboarding'
import Blocklists from './pages/Blocklists'
import Config from './pages/Config'
import Dashboard from './pages/Dashboard'
import Instances from './pages/Instances'
import Login from './pages/Login'
import Onboarding from './pages/Onboarding'
import QueryLog from './pages/QueryLog'
import Rules from './pages/Rules'
import Settings from './pages/Settings'
import Versions from './pages/Versions'

const NAV = [
  { to: '/', label: 'Dashboard' },
  { to: '/querylog', label: 'Query log' },
  { to: '/rules', label: 'Rules' },
  { to: '/subscriptions', label: 'Subscriptions' },
  { to: '/instances', label: 'Instances' },
  { to: '/config', label: 'Instance settings' },
  { to: '/history', label: 'History' },
  { to: '/settings', label: 'Settings' },
]

// The names the backend actually publishes (services/sync.py, reconcile.py) that
// change what the status pill should say. Query log traffic is deliberately not
// among them — it fires constantly and says nothing about whether nodes agree.
const SYNC_EVENTS = new Set(['instance.status', 'sync', 'retry', 'drift'])

export default function App() {
  const { state, loading, logout } = useAuth()
  const { theme, cycle } = useTheme()
  const [tick, setTick] = useState(0)
  const [menuOpen, setMenuOpen] = useState(false)

  // One stream for the whole shell; pages that need their own open theirs.
  const connected = useEventStream((event) => {
    if (SYNC_EVENTS.has(event.event)) setTick((value) => value + 1)
  })

  if (loading) {
    return (
      <div className="login-shell">
        <div style={{ color: 'var(--dim)' }}>Loading…</div>
      </div>
    )
  }

  if (!state?.authenticated) return <Login />

  const ThemeIcon = theme === 'light' ? IconSun : theme === 'dark' ? IconMoon : IconMonitor

  return (
    <div className="shell">
      <nav className="band">
        <div className="brand">
          <img src="/logo.svg" alt="" />
          AdGuardHub
        </div>

        <button
          className="icon-button burger"
          onClick={() => setMenuOpen(!menuOpen)}
          aria-label="Menu"
          aria-expanded={menuOpen}
        >
          <IconMenu />
        </button>

        <div className={`band-nav${menuOpen ? ' open' : ''}`}>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              onClick={() => setMenuOpen(false)}
              className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}
        </div>

        <div className="band-right">
          <SyncStatus connected={connected} tick={tick} />
          <button
            className="icon-button"
            onClick={cycle}
            title={`Theme: ${theme}. Click to change.`}
            aria-label={`Theme: ${theme}`}
          >
            <ThemeIcon />
          </button>
          <span className="band-user">{state.username}</span>
          <button className="icon-button" onClick={() => void logout()} title="Sign out">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M14 20H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h8M17 15l4-3-4-3M21 12H9" />
            </svg>
          </button>
        </div>
      </nav>

      <main className="main">
        {state.ephemeral_secret ? (
          <Banner kind="warn">
            <strong>ADGUARDHUB_SECRET_KEY is not set.</strong> A random key is in use, so your login
            session and the stored instance credentials will be lost on the next restart. Set the
            variable and re-enter the instance passwords.
          </Banner>
        ) : null}

        <Routes>
          <Route path="/onboarding" element={<Onboarding />} />
          <Route path="/" element={<Home />} />
          <Route path="/querylog" element={<QueryLog />} />
          <Route path="/rules" element={<Rules />} />
          <Route path="/subscriptions" element={<Blocklists />} />
          <Route path="/instances" element={<Instances />} />
          <Route path="/config" element={<Config />} />
          <Route path="/history" element={<Versions />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}

/**
 * A fresh install lands on the walkthrough instead of an empty dashboard; once the
 * hub has instances (or the operator skipped), the dashboard takes over.
 */
function Home() {
  const stats = useResource(() => api.dashboard())
  if (stats.loading && !stats.data) return null
  if (stats.data && stats.data.instances_total === 0 && !isOnboardingDone()) {
    return <Navigate to="/onboarding" replace />
  }
  return <Dashboard />
}
