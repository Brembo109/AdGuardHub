import { useState } from 'react'
import { api } from './api/client'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth'
import { Banner } from './components/ui'
import { useResource } from './hooks/useApi'
import { useEventStream } from './hooks/useEventStream'
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

export default function App() {
  const { state, loading, logout } = useAuth()

  if (loading) {
    return (
      <div className="login-shell">
        <div style={{ color: 'var(--text-dim)' }}>Loading…</div>
      </div>
    )
  }

  if (!state?.authenticated) return <Login />

  return (
    <div className="shell">
      <nav className="sidebar">
        <div className="brand">
          <img src="/logo.svg" alt="" />
          AdGuardHub
        </div>
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
          >
            {item.label}
          </NavLink>
        ))}
        <div className="sidebar-footer">
          <ConnectionBadge />
          <div style={{ marginTop: 8 }}>
            {state.username}{' '}
            <button className="small" onClick={() => void logout()}>
              Sign out
            </button>
          </div>
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

function ConnectionBadge() {
  const [lastEvent, setLastEvent] = useState('')
  const connected = useEventStream((event) => setLastEvent(event.event))

  return (
    <div title={lastEvent ? `last event: ${lastEvent}` : undefined}>
      <span className={`live-dot${connected ? ' on' : ''}`} />
      {connected ? 'live' : 'reconnecting…'}
    </div>
  )
}
