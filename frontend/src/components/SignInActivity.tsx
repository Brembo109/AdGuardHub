/**
 * Refused sign-ins, and whether an address is currently locked out.
 *
 * This exists because of a real afternoon: an operator could not connect a phone
 * app, saw "invalid authentication", and had no way from inside the hub to tell
 * a wrong password from a rate limit that was refusing the *right* one. The
 * answer was in the container log, which meant leaving the interface for a
 * shell — and the lockout, which the hub imposes itself, was the one thing it
 * would not admit to.
 *
 * So the lockout comes first and is stated plainly, before the list.
 */

import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { SignInActivity as Activity } from '../api/types'
import { formatTime } from '../format'
import { useResource } from '../hooks/useApi'
import { useT } from '../i18n'
import { Badge, Card, Empty } from './ui'

/** While a lockout is counting down, a stale number is worse than none. */
const REFRESH_MS = 15_000

function minutes(seconds: number): string {
  return String(Math.max(1, Math.ceil(seconds / 60)))
}

export function SignInActivity() {
  const t = useT()
  const activity = useResource<Activity>(() => api.signIns())
  const [, setTick] = useState(0)

  const reload = activity.reload
  useEffect(() => {
    const timer = setInterval(() => {
      void reload()
      setTick((value) => value + 1)
    }, REFRESH_MS)
    return () => clearInterval(timer)
  }, [reload])

  const data = activity.data
  if (!data) return null

  return (
    <Card
      title={t('Sign-in attempts')}
      hint={t(
        'Refused attempts on all three ways in. After {count} failures from one address within {minutes} minutes the hub stops answering it — including with the correct password.',
        { count: data.max_failures, minutes: minutes(data.window_seconds) },
      )}
    >
      {data.lockouts.length ? (
        <div className="banner warn" style={{ marginBottom: 14 }}>
          {data.lockouts.map((lockout) => (
            <div key={lockout.source}>
              {t('{source} is locked out for another {seconds} seconds. The correct password is refused too, until then.', {
                source: lockout.source,
                seconds: lockout.seconds_left,
              })}
            </div>
          ))}
        </div>
      ) : null}

      {data.failures.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('When')}</th>
                <th>{t('From')}</th>
                <th>{t('Way in')}</th>
                <th>{t('Reason')}</th>
              </tr>
            </thead>
            <tbody>
              {data.failures.map((failure, index) => (
                <tr key={`${failure.at}-${index}`}>
                  <td>{formatTime(failure.at)}</td>
                  <td className="mono">{failure.source}</td>
                  <td>{failure.door}</td>
                  <td>
                    <Badge tone="pending">{failure.reason}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty>{t('No refused sign-ins since the hub started.')}</Empty>
      )}

      <p className="hint" style={{ marginTop: 12 }}>
        {t('Kept in memory only, newest first, and cleared on restart — this is a diagnostic aid, not an audit trail. Neither the username nor the password attempted is ever recorded.')}
      </p>
    </Card>
  )
}
