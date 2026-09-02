/**
 * The one line that says a newer release exists, on whatever page you are on.
 *
 * Buried in Settings it would be found by the people who already go looking; the
 * point of an update notice is to reach the ones who do not. It is dismissible
 * per release, though — a bar you cannot get rid of teaches you to stop reading
 * bars, and the next release brings it back on its own.
 *
 * The dismissal is per browser rather than per hub: it is a preference about
 * being told, not a fact about the hub, and nothing is lost if it is forgotten.
 *
 * What dismissing must not do is make the release invisible, which it did until
 * the dot next to *Settings* in the top bar existed. That dot is not dismissible
 * and is not meant to be: this bar is the interruption, the dot is the standing
 * fact, and the two are deliberately not the same thing.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { UpdateStatus } from '../api/types'
import { useT } from '../i18n'
import { Banner } from './ui'

const DISMISSED_KEY = 'adguardhub.update.dismissed'

function readDismissed(): string {
  try {
    return localStorage.getItem(DISMISSED_KEY) ?? ''
  } catch {
    // Private windows and blocked site data throw on access. Not being able to
    // remember a dismissal is not a reason to fail to render.
    return ''
  }
}

function remember(version: string): void {
  try {
    localStorage.setItem(DISMISSED_KEY, version)
  } catch {
    // Then it comes back on the next load. Harmless.
  }
}

/** The status is fetched once by the shell and shared with the nav dot. */
export function UpdateNotice({ status }: { status: UpdateStatus | null }) {
  const t = useT()
  const [dismissed, setDismissed] = useState(readDismissed)
  const data = status

  if (!data?.update_available) return null
  if (dismissed === data.latest) return null

  return (
    <Banner kind="ok">
      <div className="banner-row">
        <span>
          {/* Not "you are running X" — the footer says that on this very page. */}
          {t('AdGuardHub {version} is available.', { version: data.latest })}{' '}
          <a href={data.release_url} target="_blank" rel="noreferrer noopener">
            {t('Release notes')}
          </a>
          {' · '}
          <Link to="/settings/updates">{t('How to update')}</Link>
        </span>
        <button
          className="ghost small"
          type="button"
          onClick={() => {
            remember(data.latest)
            setDismissed(data.latest)
          }}
        >
          {t('Dismiss')}
        </button>
      </div>
    </Banner>
  )
}
