/**
 * The "update now" button, and watching what happens after it.
 *
 * The unusual part is that the thing being watched restarts the thing doing the
 * watching. Halfway through an upgrade this hub is stopped, replaced and started
 * again, so every request in here fails for a while and then starts working
 * against a *different build*. That is success, not an error, and the polling is
 * written for it: a failed poll during a run is a step forward, and the run's
 * state is read back from the log the updater writes rather than kept here.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { UpdateRun } from '../api/types'
import { errorMessage } from '../hooks/useApi'
import { useT } from '../i18n'
import { Banner } from './ui'

const POLL_MS = 3000

export function UpdateRunner({ onFinished }: { onFinished: () => void }) {
  const t = useT()
  const [run, setRun] = useState<UpdateRun | null>(null)
  const [error, setError] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [starting, setStarting] = useState(false)
  // While the hub is being replaced it stops answering. Counted rather than
  // shown as an error, because it is the expected middle of a successful
  // upgrade — the same failure before one has started is a real failure.
  const unreachable = useRef(0)
  const logRef = useRef<HTMLPreElement | null>(null)

  const poll = useCallback(async () => {
    try {
      const next = await api.updateRun()
      unreachable.current = 0
      setRun(next)
      return next
    } catch {
      unreachable.current += 1
      return null
    }
  }, [])

  // One read on mount, so a run started before this page was opened — or before
  // the browser reloaded into the new build — is picked up rather than lost.
  useEffect(() => {
    void poll()
  }, [poll])

  const active = run?.running || (run !== null && unreachable.current > 0 && !run.finished)

  useEffect(() => {
    if (!active) return
    const timer = setInterval(() => {
      void (async () => {
        const next = await poll()
        if (next?.finished) onFinished()
      })()
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [active, poll, onFinished])

  // Follow the log as it grows; an operator watching an upgrade wants the end.
  useEffect(() => {
    const node = logRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [run?.log])

  const start = () => {
    setStarting(true)
    setError('')
    void (async () => {
      try {
        setRun(await api.startUpdate())
        setConfirming(false)
      } catch (caught) {
        setError(errorMessage(caught))
      } finally {
        setStarting(false)
      }
    })()
  }

  return (
    <div style={{ marginTop: 14 }}>
      {error ? <Banner kind="error">{error}</Banner> : null}

      {run?.stalled ? (
        <Banner kind="warn">
          {t(
            'The upgrade was requested but nothing picked it up. This hub was probably installed before the updater existed — re-run the installer once by hand and the button will work from then on.',
          )}
        </Banner>
      ) : null}

      {run?.finished ? (
        run.exit_status === 0 ? (
          <Banner kind="ok">{t('The upgrade finished. Reload to see the new version.')}</Banner>
        ) : (
          <Banner kind="error">
            {t('The upgrade failed (status {status}). Nothing was rolled back — the hub is still running the version it was.', {
              status: String(run.exit_status),
            })}
          </Banner>
        )
      ) : null}

      {run?.log ? (
        <pre className="run-log" ref={logRef}>
          {run.log}
        </pre>
      ) : null}

      {active && !run?.log ? (
        <p className="hint">{t('Waiting for the upgrade to start…')}</p>
      ) : null}

      {confirming ? (
        <Banner kind="warn">
          <div className="banner-row">
            <span>
              {t(
                'The hub will be replaced with the newest release and restarted, so it is unreachable for a minute or two. Your database, your instance credentials and adguardhub.env are not touched. DNS on your nodes keeps working throughout — they answer queries on their own.',
              )}
            </span>
            <span className="actions">
              <button className="primary" type="button" onClick={start} disabled={starting}>
                {t('Update now')}
              </button>
              <button type="button" onClick={() => setConfirming(false)} disabled={starting}>
                {t('Cancel')}
              </button>
            </span>
          </div>
        </Banner>
      ) : (
        <div className="actions">
          <button
            className="primary"
            type="button"
            onClick={() => setConfirming(true)}
            disabled={active}
          >
            {active ? t('Upgrading…') : t('Update this hub')}
          </button>
        </div>
      )}
    </div>
  )
}
