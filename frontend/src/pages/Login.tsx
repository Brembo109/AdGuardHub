import { useState } from 'react'
import { useAuth } from '../auth'
import { Banner } from '../components/ui'
import { errorMessage } from '../hooks/useApi'

export default function Login() {
  const { state, login, setup } = useAuth()
  const isSetup = state?.setup_required ?? false
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError('')
    if (isSetup && password !== confirm) {
      setError('The two passwords do not match.')
      return
    }
    setBusy(true)
    try {
      if (isSetup) {
        await setup(username, password)
      } else {
        await login(username, password)
      }
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-shell">
      <form className="login-card" onSubmit={submit}>
        <div className="brand">
          <img src="/logo.svg" alt="" />
          AdGuardHub
        </div>
        <p className="hint">
          {isSetup
            ? 'Create the admin account for this hub.'
            : 'Sign in to manage your AdGuard Home instances.'}
        </p>

        {error ? <Banner kind="error">{error}</Banner> : null}

        <div className="field">
          <label htmlFor="username">Username</label>
          <input
            id="username"
            value={username}
            autoComplete="username"
            onChange={(event) => setUsername(event.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            autoComplete={isSetup ? 'new-password' : 'current-password'}
            onChange={(event) => setPassword(event.target.value)}
            required
            minLength={isSetup ? 8 : undefined}
          />
        </div>
        {isSetup ? (
          <div className="field">
            <label htmlFor="confirm">Repeat password</label>
            <input
              id="confirm"
              type="password"
              value={confirm}
              autoComplete="new-password"
              onChange={(event) => setConfirm(event.target.value)}
              required
              minLength={8}
            />
          </div>
        ) : null}

        <button className="primary" type="submit" disabled={busy} style={{ width: '100%' }}>
          {busy ? 'Please wait…' : isSetup ? 'Create account' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
