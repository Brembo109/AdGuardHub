/**
 * Which build is running, and where it came from.
 *
 * The version used to be a line at the bottom of Settings, which is the one page
 * you are not on when you ask "did my update actually land?". It belongs under
 * every page instead.
 *
 * The project link is here for the same reason it is on any self-hosted tool: an
 * operator who hits something strange wants the issue tracker, and hunting for
 * the repository by name is a worse experience than a link that was always
 * there. A released build points at its own tag, so the link answers "what is in
 * this version" rather than "what is on main".
 */

import { api } from '../api/client'
import { useResource } from '../hooks/useApi'
import { useT } from '../i18n'
import { REPO_URL, releaseUrl } from '../repo'
import { IconGitHub } from './icons'

export function Footer() {
  const t = useT()
  const health = useResource(() => api.health())
  const version = health.data?.version

  return (
    <footer className="footer">
      {version ? (
        <a href={releaseUrl(version)} target="_blank" rel="noreferrer noopener">
          {t('AdGuardHub {version}', { version })}
        </a>
      ) : null}
      <a href={REPO_URL} target="_blank" rel="noreferrer noopener">
        <IconGitHub />
        {t('Source & issues')}
      </a>
    </footer>
  )
}
