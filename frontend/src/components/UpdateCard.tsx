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
import { UpdateRunner } from './UpdateRunner'
import { Banner, Card } from './ui'

/** The command that upgrades this kind of install, or nothing for a checkout.
 *
 * Docker is not in here because there is no single command for it: what to run
 * depends on whether the container came from a compose file, which cannot be
 * seen from inside the container. See {@link DockerUpgrade}.
 */
const UPGRADE_COMMAND: Record<InstallMethod, string> = {
  docker: '',
  native: 'curl -fsSL https://raw.githubusercontent.com/fgrfn/adguardhub/main/install.sh | sudo sh',
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

/**
 * The two ways a container gets replaced, because the hub cannot tell them apart.
 *
 * Compose leaves no trace inside the container it started — no environment
 * variable, no file — so a hub that shows only `docker compose pull` is telling
 * everybody who used plain `docker run` to run a command that cannot work, and
 * everybody else to run it in a directory they may not be standing in. The error
 * that follows ("no configuration file provided") reads like a broken hub rather
 * than a wrong working directory, so it is named here rather than left to search.
 */
function DockerUpgrade() {
  const t = useT()

  return (
    <>
      <p className="hint" style={{ margin: '10px 0 6px' }}>
        {t(
          'With Compose, in the directory that holds your docker-compose.yml — “no configuration file provided” means you are somewhere else, or there is no compose file at all:',
        )}
      </p>
      <pre className="command">docker compose pull &amp;&amp; docker compose up -d</pre>

      <p className="hint" style={{ margin: '10px 0 6px' }}>
        {t(
          'Started with docker run instead? Pull the image, drop the container, and start it again with exactly the command you used the first time — the data volume it mounts is not touched by any of this:',
        )}
      </p>
      <pre className="command">
        {'docker pull ghcr.io/fgrfn/adguardhub:latest\ndocker rm -f adguardhub'}
      </pre>
    </>
  )
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

      {/* The running version is in the footer under every page, so repeating it
          here only made the one sentence that matters harder to find. */}
      <p style={{ margin: '10px 0 0' }}>
        {data.update_available ? (
          <>
            <strong>
              <a href={data.release_url} target="_blank" rel="noreferrer noopener">
                {t('Update to {version} available', { version: data.latest })}
              </a>
            </strong>
            {data.published_at
              ? ` — ${t('released {date}', { date: formatDate(data.published_at) })}`
              : ''}
          </>
        ) : data.latest ? (
          t('Up to date.')
        ) : data.enabled ? (
          t('No release has been found yet.')
        ) : (
          t('Update checks are off.')
        )}
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
          {/* A native install can be told to do this itself, so the command is
              the fallback for whoever would rather run it in a terminal. */}
          {command ? <pre className="command">{command}</pre> : null}
          {data.install_method === 'docker' ? <DockerUpgrade /> : null}
          {data.self_update ? <UpdateRunner onFinished={() => void status.reload()} /> : null}
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
