/**
 * Whether a newer AdGuardHub exists, and what to do about it here.
 *
 * The "what to do about it" half is the reason this is a card rather than a
 * banner. How you upgrade depends on how you installed: a container is replaced
 * by pulling a new image, a native install by re-running the installer, and a
 * checkout by whatever you normally do. Telling everybody to run one of those
 * three would be wrong for two thirds of them, so the hub works out which it is
 * and shows only that.
 */

import { useState } from 'react'
import { api } from '../api/client'
import type { HubSettings, InstallMethod, UpdateStatus } from '../api/types'
import { formatDate } from '../format'
import { errorMessage, useResource } from '../hooks/useApi'
import { useT } from '../i18n'
import { Banner, Card } from './ui'

/** The command that upgrades this kind of install, or nothing for a checkout. */
const UPGRADE_COMMAND: Record<InstallMethod, string> = {
  docker: 'docker compose pull && docker compose up -d',
  native: 'curl -sSL https://raw.githubusercontent.com/fgrfn/adguardhub/main/install.sh | sudo sh',
  source: '',
}

const METHOD_HINT: Record<InstallMethod, string> = {
  docker:
    'This hub runs in a container, so it cannot replace its own image — pull the new one on the host and recreate the container. Your data volume is untouched.',
  native:
    'This hub was installed by the installer, which upgrades in place when it is run again. Your data directory and /etc/adguardhub/adguardhub.env are never touched.',
  source:
    'This hub is running from a checkout rather than a release, so upgrading it is whatever you normally do with that checkout.',
}

export function UpdateCard() {
  const t = useT()
  const status = useResource<UpdateStatus>(() => api.updateStatus())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const data = status.data
  if (!data) return null

  const setEnabled = (enabled: boolean) => {
    setBusy(true)
    setError('')
    void (async () => {
      try {
        await api.saveHubSettings({ update_check_enabled: enabled } as Partial<
          Omit<HubSettings, 'limits'>
        >)
        await status.reload()
      } catch (caught) {
        setError(errorMessage(caught))
      } finally {
        setBusy(false)
      }
    })()
  }

  const checkNow = () => {
    setBusy(true)
    setError('')
    void (async () => {
      try {
        status.setData(await api.updateStatus(true))
      } catch (caught) {
        setError(errorMessage(caught))
      } finally {
        setBusy(false)
      }
    })()
  }

  const command = UPGRADE_COMMAND[data.install_method]

  return (
    <Card
      title={t('Updates')}
      hint={t(
        'One request to github.com every few hours, asking only what the newest release is. Nothing about this hub is sent.',
      )}
    >
      {error ? <Banner kind="error">{error}</Banner> : null}

      <label className="checkbox">
        <input
          type="checkbox"
          checked={data.enabled}
          disabled={busy}
          onChange={(event) => setEnabled(event.target.checked)}
        />
        {t('Check for new releases')}
      </label>

      <p style={{ margin: '10px 0 0' }}>
        {t('Running {version}.', { version: data.current })}{' '}
        {data.update_available ? (
          <strong>
            <a href={data.release_url} target="_blank" rel="noreferrer noopener">
              {t('{version} is available.', { version: data.latest })}
            </a>
          </strong>
        ) : data.latest ? (
          t('That is the newest release.')
        ) : data.enabled ? (
          t('No release has been found yet.')
        ) : (
          t('Update checks are off.')
        )}
        {data.update_available && data.published_at
          ? ` ${t('Released {date}.', { date: formatDate(data.published_at) })}`
          : ''}
      </p>

      {data.error ? (
        <p className="hint" style={{ marginTop: 6 }}>
          {/* Not an error banner: a hub with no route to the internet is working
              exactly as intended, and this is the one thing it cannot do. */}
          {t('The last check did not get an answer ({reason}).', { reason: data.error })}
        </p>
      ) : null}

      {data.update_available ? (
        <div style={{ marginTop: 14 }}>
          <p className="hint" style={{ margin: '0 0 6px' }}>
            {t(METHOD_HINT[data.install_method])}
          </p>
          {command ? <pre className="command">{command}</pre> : null}
        </div>
      ) : null}

      <div className="actions" style={{ marginTop: 14 }}>
        <button type="button" onClick={checkNow} disabled={busy || !data.enabled}>
          {t('Check now')}
        </button>
      </div>
    </Card>
  )
}
