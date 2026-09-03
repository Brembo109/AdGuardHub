/**
 * The one-click answer to "what does your setup look like?".
 *
 * Its own page rather than a button on the log page, because what it needs to
 * say is a paragraph and because this is where somebody about to file an issue
 * will look for it.
 *
 * A diagnostic bundle goes where a backup does not — into a public issue, read
 * by a stranger — so what is in it is stated here, before the download, rather
 * than left to be discovered in the file or, worse, in a reply.
 */

import { api } from '../../api/client'
import { Card } from '../../components/ui'
import { useT } from '../../i18n'

export default function SettingsDiagnostics() {
  const t = useT()
  return (
    <Card
      title={t('Diagnostics')}
      hint={t(
        'One file to attach to a bug report: this hub’s version and how it was installed, the state of each node, the retry queue, recent drift, and the last 200 log lines.',
      )}
    >
      <div className="actions" style={{ marginBottom: 14 }}>
        <a className="button" href={api.diagnosticsUrl()} download>
          {t('Download diagnostics')}
        </a>
      </div>
      <p className="hint" style={{ margin: 0 }}>
        {t(
          'Node names, addresses and usernames are taken out — each node reads as node-1, node-2 throughout the file, including inside error messages and log lines, so it can still be followed from one section to the next. Passwords, webhook paths and the values of your settings areas are never in it.',
        )}
      </p>
      <p className="hint" style={{ margin: '8px 0 0' }}>
        {t(
          'Your rules, subscription addresses and the domains in a drift entry are in it, because that is what most reports are about. It is plain JSON — open it before you post it.',
        )}
      </p>
    </Card>
  )
}
