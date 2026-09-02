import { useState } from 'react'
import { api } from '../api/client'
import type { Version, VersionDiff } from '../api/types'
import { Badge, Banner, Card, Empty, PageHeader } from '../components/ui'
import { formatTime } from '../format'
import { errorMessage, useResource } from '../hooks/useApi'
import { useT } from '../i18n'

/**
 * Configuration history. Every change snapshots the central state, so what a sync
 * carried can be inspected after the fact, compared, and rolled back.
 */
export default function Versions() {
  const t = useT()
  const versions = useResource<Version[]>(() => api.versions(100))
  const [diff, setDiff] = useState<VersionDiff | null>(null)
  const [compareWith, setCompareWith] = useState<number | ''>('')
  const [selected, setSelected] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const list = versions.data ?? []

  async function run(action: () => Promise<string>) {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      setMessage(await action())
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
      await versions.reload()
    }
  }

  const show = async (version: Version, against: number | '') => {
    setSelected(version.id)
    setError('')
    try {
      setDiff(await api.versionDiff(version.id, against === '' ? undefined : against))
    } catch (caught) {
      setError(errorMessage(caught))
      setDiff(null)
    }
  }

  const restore = (version: Version) => {
    if (
      !confirm(
        t('Roll back to version {id}?', { id: version.id }) +
          '\n\n' +
          t(
            "The hub's rules, subscriptions and settings are replaced with that snapshot and pushed to every instance. The rollback itself is recorded, so it can be undone.",
          ),
      )
    )
      return
    void run(async () => {
      const result = await api.restoreVersion(version.id)
      setDiff(null)
      setSelected(null)
      return t(
        'Rolled back to version {id}: {rules} rule(s), {lists} subscription(s), {sections} section(s) — pushing to all instances.',
        {
          id: version.id,
          rules: result.rules,
          lists: result.filter_lists,
          sections: result.sections,
        },
      )
    })
  }

  return (
    <>
      <PageHeader
        title={t('History')}
        description={t('Every change to the hub is snapshotted. Compare any two points, see exactly what a sync carried, and roll back if it was wrong.')}
      />

      {error ? <Banner kind="error">{error}</Banner> : null}
      {message ? <Banner kind="ok">{message}</Banner> : null}
      {versions.error ? <Banner kind="error">{versions.error}</Banner> : null}

      <Card>
        {list.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>{t('When')}</th>
                  <th>{t('Change')}</th>
                  <th>{t('By')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.map((version) => (
                  <tr key={version.id} className={selected === version.id ? 'selected' : undefined}>
                    <td>{version.id}</td>
                    <td>{formatTime(version.created_at)}</td>
                    <td>
                      {version.label}
                      <div className="hint" style={{ margin: 0 }}>
                        {version.summary}
                      </div>
                    </td>
                    <td>
                      {version.author || '—'}
                      {version.kind !== 'change' ? (
                        <>
                          {' '}
                          <Badge tone={version.kind === 'restore' ? 'pending' : 'allow'}>
                            {t(version.kind)}
                          </Badge>
                        </>
                      ) : null}
                    </td>
                    <td className="right">
                      <button
                        className="small"
                        onClick={() => show(version, compareWith)}
                        disabled={busy}
                      >
                        {t('Compare')}
                      </button>{' '}
                      <button
                        className="small danger"
                        onClick={() => restore(version)}
                        disabled={busy}
                      >
                        {t('Roll back')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>
            {versions.loading
              ? t('Loading…')
              : t('No history yet — make a change and it appears here.')}
          </Empty>
        )}
      </Card>

      {diff ? (
        <Card
          title={t('Version {id} → {label}', { id: diff.from_id, label: diff.to_label })}
          hint={diff.summary}
        >
          <div className="row" style={{ marginBottom: 12 }}>
            <div className="field fixed" style={{ width: 280, marginBottom: 0 }}>
              <label htmlFor="against">{t('Compare against')}</label>
              <select
                id="against"
                value={compareWith}
                onChange={(event) => {
                  const value = event.target.value === '' ? '' : Number(event.target.value)
                  setCompareWith(value)
                  const version = list.find((item) => item.id === diff.from_id)
                  if (version) void show(version, value)
                }}
              >
                <option value="">{t('Current state')}</option>
                {list
                  .filter((item) => item.id !== diff.from_id)
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {t('Version {id} — {label}', { id: item.id, label: item.label })}
                    </option>
                  ))}
              </select>
            </div>
          </div>

          {diff.changes.empty ? (
            <Empty>{t('Identical — nothing differs between these two points.')}</Empty>
          ) : (
            <>
              <EntryDiff title={t('Rules')} entry={diff.changes.rules} />
              <EntryDiff title={t('Filter lists')} entry={diff.changes.filter_lists} />
              <SectionDiff sections={diff.changes.sections} />
            </>
          )}
        </Card>
      ) : null}
    </>
  )
}

function EntryDiff({
  title,
  entry,
}: {
  title: string
  entry: { added: string[]; removed: string[]; changed: { key: string }[] }
}) {
  if (!entry.added.length && !entry.removed.length && !entry.changed.length) return null
  return (
    <div style={{ marginBottom: 16 }}>
      <h3 style={{ fontSize: 14, margin: '0 0 6px' }}>{title}</h3>
      {entry.added.map((item) => (
        <div key={`+${item}`} className="mono diff-add">
          + {item}
        </div>
      ))}
      {entry.removed.map((item) => (
        <div key={`-${item}`} className="mono diff-remove">
          − {item}
        </div>
      ))}
      {entry.changed.map((item) => (
        <div key={`~${item.key}`} className="mono diff-change">
          ~ {item.key}
        </div>
      ))}
    </div>
  )
}

function SectionDiff({
  sections,
}: {
  sections: Record<
    string,
    {
      keys: Record<string, { before: unknown; after: unknown }>
      managed?: { before: boolean; after: boolean }
    }
  >
}) {
  const t = useT()
  const names = Object.keys(sections)
  if (!names.length) return null
  return (
    <div>
      <h3 style={{ fontSize: 14, margin: '0 0 6px' }}>{t('Instance settings')}</h3>
      {names.map((name) => (
        <div key={name} style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>{name}</div>
          {sections[name].managed ? (
            <div className="mono diff-change">
              ~ replicated: {String(sections[name].managed?.before)} →{' '}
              {String(sections[name].managed?.after)}
            </div>
          ) : null}
          {Object.entries(sections[name].keys).map(([key, change]) => (
            <div key={key} className="mono diff-change">
              ~ {key}: {render(change.before)} → {render(change.after)}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

function render(value: unknown): string {
  if (value === undefined) return '—'
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}
