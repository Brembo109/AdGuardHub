/**
 * The account, and who has been trying to use it.
 *
 * Together on purpose: the password and the record of refused attempts on it
 * are the same question asked forwards and backwards, and an operator who came
 * here because something looked wrong wants both in one place.
 */

import { useState } from 'react'
import { api } from '../../api/client'
import { useAuth } from '../../auth'
import { SignInActivity } from '../../components/SignInActivity'
import { Card } from '../../components/ui'
import { RunnerBanners } from '../../components/RunnerBanners'
import { useRunner } from '../../hooks/useRunner'
import { useT } from '../../i18n'

export default function SettingsSecurity() {
  const t = useT()
  const { state, logout } = useAuth()
  const runner = useRunner()
  const { busy, run } = runner
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    void run(async () => {
      await api.changePassword(current, next)
      setCurrent('')
      setNext('')
      return t('Password changed.')
    })
  }

  return (
    <>
      <RunnerBanners state={runner} />
      <Card
        title={t('Account')}
        hint={t('Signed in as {name}.', { name: state?.username ?? t('unknown') })}
      >
        <form onSubmit={submit} className="row">
          <div className="field">
            <label htmlFor="cur">{t('Current password')}</label>
            <input
              id="cur"
              type="password"
              value={current}
              autoComplete="current-password"
              onChange={(event) => setCurrent(event.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="new">{t('New password')}</label>
            <input
              id="new"
              type="password"
              value={next}
              minLength={8}
              autoComplete="new-password"
              onChange={(event) => setNext(event.target.value)}
              required
            />
          </div>
          <div className="field fixed">
            <button className="primary" type="submit" disabled={busy}>
              {t('Change password')}
            </button>
          </div>
          <div className="field fixed">
            <button type="button" onClick={() => void logout()}>
              {t('Sign out')}
            </button>
          </div>
        </form>
      </Card>

      <SignInActivity />
    </>
  )
}
