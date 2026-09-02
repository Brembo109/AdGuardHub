/**
 * The one thing that survives losing the hub's volume.
 *
 * The file deliberately carries no instance password, so a restore brings the
 * nodes back needing theirs typed in again — said here rather than discovered
 * afterwards.
 */

import { useState } from 'react'
import { api } from '../../api/client'
import { Card } from '../../components/ui'
import { RunnerBanners } from '../../components/RunnerBanners'
import { useRunner } from '../../hooks/useRunner'
import { useT } from '../../i18n'

export default function SettingsBackup() {
  const t = useT()
  const runner = useRunner()
  const { busy, run } = runner
  const [file, setFile] = useState<File | null>(null)

  const restore = () => {
    if (!file) return
    if (
      !confirm(
        t('Replace every rule, subscription and instance setting in this hub with the contents of {name}?', {
          name: file.name,
        }) +
          '\n\n' +
          t('The current state stays in the history, so this can be rolled back.'),
      )
    )
      return
    void run(async () => {
      const parsed: unknown = JSON.parse(await file.text())
      const result = await api.restoreBackup(parsed)
      setFile(null)
      const restored = t(
        'Restored {rules} rule(s), {lists} subscription(s) and {sections} settings area(s).',
        { rules: result.rules, lists: result.filter_lists, sections: result.sections },
      )
      return result.instances_need_password
        ? `${restored} ${t('{count} instance(s) came back without a password — re-enter it under Instances.', { count: result.instances_need_password })}`
        : restored
    })
  }

  return (
    <>
      <RunnerBanners state={runner} />
      <Card
        title={t('Backup')}
        hint={t('Everything the hub owns — rules, subscriptions and instance settings — as one file. Instance passwords are never included.')}
      >
        <div className="actions" style={{ marginBottom: 16 }}>
          <a className="button" href={api.backupUrl()} download>
            {t('Download backup')}
          </a>
        </div>

        <div className="row" style={{ alignItems: 'flex-end' }}>
          {/* Bounded, so the button stays beside the picker rather than drifting
              to the far edge of a wide screen. */}
          <div className="field" style={{ flex: '0 1 420px' }}>
            <label htmlFor="backup-file">{t('Restore from a backup file')}</label>
            <input
              id="backup-file"
              type="file"
              accept="application/json,.json"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </div>
          <div className="field fixed">
            <button className="danger" onClick={restore} disabled={busy || !file}>
              {t('Restore')}
            </button>
          </div>
        </div>
        <p className="hint" style={{ margin: '8px 0 0' }}>
          {t(
            'Restoring replaces the hub\'s rules, subscriptions and instance settings, then pushes the result to every node. Nodes already connected keep their credentials; any the backup adds need their password entered again.',
          )}
        </p>
      </Card>
    </>
  )
}
