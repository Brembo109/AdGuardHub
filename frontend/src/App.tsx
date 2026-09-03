import { useState } from 'react'
import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { api } from './api/client'
import type { UpdateStatus } from './api/types'
import { useAuth } from './auth'
import { Footer } from './components/Footer'
import { SyncStatus } from './components/SyncStatus'
import { UpdateNotice } from './components/UpdateNotice'
import { IconMenu, IconMonitor, IconMoon, IconSun } from './components/icons'
import { Banner } from './components/ui'
import { useResource } from './hooks/useApi'
import { useEventStream } from './hooks/useEventStream'
import { useTheme } from './hooks/useTheme'
import { LANGUAGES, useI18n } from './i18n'
import { covers } from './nav'
import Blocklists from './pages/Blocklists'
import Config from './pages/Config'
import Dashboard from './pages/Dashboard'
import Dns from './pages/Dns'
import Instances from './pages/Instances'
import Login from './pages/Login'
import Onboarding from './pages/Onboarding'
import QueryLog from './pages/QueryLog'
import Rules from './pages/Rules'
import SettingsLayout from './pages/settings/Layout'
import SettingsBackup from './pages/settings/Backup'
import SettingsDiagnostics from './pages/settings/Diagnostics'
import SettingsGeneral from './pages/settings/General'
import SettingsLog from './pages/settings/Log'
import SettingsNotifications from './pages/settings/Notifications'
import SettingsSecurity from './pages/settings/Security'
import SettingsUpdates from './pages/settings/Updates'
import Versions from './pages/Versions'

/**
 * The top level, and only the top level.
 *
 * Nine entries was more than a bar can carry legibly, and the pairs that
 * belonged together were sitting apart: rules beside subscriptions, instances
 * beside their settings. Each pair is now one entry whose page carries tabs, so
 * the bar names seven places rather than nine destinations.
 *
 * `covers` is what keeps the top-level entry lit while you are on its second
 * tab — a NavLink only knows about its own path, and "Filter" going dark
 * because you clicked "Filterlisten" would say you had left it.
 */
const NAV: { to: string; label: string; covers?: string[] }[] = [
  { to: '/', label: 'Dashboard' },
  { to: '/querylog', label: 'Query log' },
  { to: '/rules', label: 'Filtering', covers: ['/rules', '/subscriptions'] },
  { to: '/dns', label: 'DNS & upstreams' },
  { to: '/instances', label: 'Instances', covers: ['/instances', '/config'] },
  { to: '/history', label: 'History' },
  { to: '/settings', label: 'Settings' },
]

/**
 * The one nav entry that carries a state rather than only a destination.
 *
 * A newer release is announced by the bar under the nav, which is dismissible on
 * purpose. Dismissing it used to leave nothing at all: the only remaining trace
 * was a page you had to already suspect and go looking at. The dot is that trace
 * — never in the way, never dismissible, gone when the hub is current.
 */
const UPDATES_LIVE_UNDER = '/settings'

// The names the backend actually publishes (services/sync.py, reconcile.py) that
// change what the status pill should say. Query log traffic is deliberately not
// among them — it fires constantly and says nothing about whether nodes agree.
const SYNC_EVENTS = new Set(['instance.status', 'instances', 'sync', 'retry', 'drift'])

export default function App() {
  const { state, loading, logout } = useAuth()
  const { theme, cycle } = useTheme()
  const { t, language, setLanguage } = useI18n()
  const [tick, setTick] = useState(0)
  const [menuOpen, setMenuOpen] = useState(false)
  const { pathname } = useLocation()

  // One stream for the whole shell; pages that need their own open theirs.
  const connected = useEventStream((event) => {
    if (SYNC_EVENTS.has(event.event)) setTick((value) => value + 1)
  })

  // Fetched here rather than in each of the two things that show it, so opening
  // any page is one question about releases instead of two.
  const update = useResource<UpdateStatus>(() => api.updateStatus())
  const updateAvailable = Boolean(update.data?.update_available)

  if (loading) {
    return (
      <div className="login-shell">
        <div style={{ color: 'var(--dim)' }}>{t('Loading…')}</div>
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
          aria-label={t('Menu')}
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
              className={({ isActive }) =>
                `nav-link${isActive || covers(item, pathname) ? ' active' : ''}`
              }
            >
              {t(item.label)}
              {item.to === UPDATES_LIVE_UNDER && updateAvailable ? (
                <span
                  className="nav-dot"
                  role="img"
                  aria-label={t('An update is available')}
                  title={t('An update is available')}
                />
              ) : null}
            </NavLink>
          ))}
        </div>

        <div className="band-right">
          <SyncStatus connected={connected} tick={tick} />
          <button
            className="icon-button lang"
            onClick={() =>
              setLanguage(
                LANGUAGES[(LANGUAGES.findIndex((item) => item.code === language) + 1) %
                  LANGUAGES.length].code,
              )
            }
            title={t('Language: {name}. Click to change.', {
              name: LANGUAGES.find((item) => item.code === language)?.label ?? language,
            })}
            aria-label={t('Language')}
          >
            {language.toUpperCase()}
          </button>
          <button
            className="icon-button"
            onClick={cycle}
            title={t('Theme: {name}. Click to change.', { name: t(theme) })}
            aria-label={t('Theme')}
          >
            <ThemeIcon />
          </button>
          <span className="band-user">{state.username}</span>
          <button className="icon-button" onClick={() => void logout()} title={t('Sign out')}>
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
            <strong>{t('ADGUARDHUB_SECRET_KEY is not set.')}</strong>{' '}
            {t(
              'A random key is in use, so your login session and the stored instance credentials will be lost on the next restart. Set the variable and re-enter the instance passwords.',
            )}
          </Banner>
        ) : null}

        <UpdateNotice status={update.data} />

        <Routes>
          <Route path="/onboarding" element={<Onboarding />} />
          {/* Until the walkthrough is finished or skipped, the hub opens on it
              rather than on a dashboard with nothing to show. */}
          <Route
            path="/"
            element={state.onboarding_done ? <Dashboard /> : <Navigate to="/onboarding" replace />}
          />
          <Route path="/querylog" element={<QueryLog />} />
          <Route path="/rules" element={<Rules />} />
          <Route path="/subscriptions" element={<Blocklists />} />
          <Route path="/dns" element={<Dns />} />
          <Route path="/instances" element={<Instances />} />
          <Route path="/config" element={<Config />} />
          <Route path="/history" element={<Versions />} />
          {/* Real routes rather than tab state, so every one can be linked to. */}
          <Route path="/settings" element={<SettingsLayout />}>
            <Route index element={<SettingsGeneral />} />
            <Route path="notifications" element={<SettingsNotifications />} />
            <Route path="updates" element={<SettingsUpdates />} />
            <Route path="security" element={<SettingsSecurity />} />
            <Route path="log" element={<SettingsLog />} />
            <Route path="backup" element={<SettingsBackup />} />
            <Route path="diagnostics" element={<SettingsDiagnostics />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <Footer />
    </div>
  )
}

