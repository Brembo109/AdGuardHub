import { useState } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth'
import { Banner } from './components/ui'
import { useEventStream } from './hooks/useEventStream'
import Blocklists from './pages/Blocklists'
import Dashboard from './pages/Dashboard'
import Instances from './pages/Instances'
import Login from './pages/Login'
import QueryLog from './pages/QueryLog'
import Rules from './pages/Rules'
import Settings from './pages/Settings'

const NAV = [
  { to: '/', label: 'Dashboard' },
  { to: '/querylog', label: 'Query log' },
  { to: '/rules', label: 'Rules' },
  { to: '/subscriptions', label: 'Subscriptions' },
  { to: '/instances', label: 'Instances' },
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
          <Route path="/" element={<Dashboard />} />
          <Route path="/querylog" element={<QueryLog />} />
          <Route path="/rules" element={<Rules />} />
          <Route path="/subscriptions" element={<Blocklists />} />
          <Route path="/instances" element={<Instances />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
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
