import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ConfigSection } from '../api/types'
import { SectionFields } from '../components/SectionFields'
import { Badge, Banner, Card, Empty, PageHeader } from '../components/ui'
import { formatTime } from '../format'
import { errorMessage, useResource } from '../hooks/useApi'
import { useT } from '../i18n'

const SECTION = 'dns'

/**
 * DNS and upstreams, on a page of its own.
 *
 * Twenty-one settings is too many for one flat form, so they are laid out in the
 * groups AdGuard Home uses on its own DNS page. The grouping is declared with the
 * fields in adapters/sections.py — a field added there cannot end up outside
 * every group here.
 */
export default function Dns() {
  const t = useT()
  // One request for the whole list, then pick this section out of it — cheaper
  // than a second endpoint that would exist only for this page.
  const sections = useResource<ConfigSection[]>(() => api.configSections())
  const [draft, setDraft] = useState<Record<string, unknown>>({})
  const [raw, setRaw] = useState('')
  const [showRaw, setShowRaw] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const loaded = sections.data?.find((item) => item.name === SECTION) ?? null
  useEffect(() => {
    if (!loaded) return
    setDraft(loaded.data)
    setRaw(JSON.stringify(loaded.data, null, 2))
  }, [loaded])

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
      await sections.reload()
    }
  }

  if (!loaded) {
    return (
      <>
        <PageHeader title={t('DNS & upstreams')} />
        <Card>
          <Empty>{sections.error || t('Loading…')}</Empty>
        </Card>
      </>
    )
  }

  const toggle = () =>
    run(async () => {
      await api.updateSection(SECTION, { managed: !loaded.managed })
      return loaded.managed
        ? t('DNS settings are no longer pushed; each instance keeps its own.')
        : t('DNS settings are now pushed to every instance.')
    })

  const save = () => {
    let payload = draft
    if (showRaw) {
      try {
        payload = JSON.parse(raw)
      } catch {
        setError(t('That is not valid JSON.'))
        return
      }
    }
    return run(async () => {
      await api.updateSection(SECTION, { data: payload })
      return loaded.managed
        ? t('Saved and pushed to every instance.')
        : t('Saved. Switch on Replicate to send it to the instances.')
    })
  }

  const discard = () => {
    setDraft(loaded.data)
    setRaw(JSON.stringify(loaded.data, null, 2))
    setError('')
    setMessage('')
  }

  // Group order follows the field order in sections.py, so the page reads the
  // way the settings were declared rather than in an arbitrary alphabetical one.
  const groups: { name: string; fields: typeof loaded.fields }[] = []
  for (const field of loaded.fields) {
    const name = field.group || 'Other settings'
    const existing = groups.find((group) => group.name === name)
    if (existing) existing.fields.push(field)
    else groups.push({ name, fields: [field] })
  }

  return (
    <>
      <PageHeader
        title={t('DNS & upstreams')}
        description={t('How every instance resolves what it does not block. Saved here, these settings are pushed to all instances at once and put back by reconciliation if a node drifts.')}
        actions={
          <>
            <button onClick={() => setShowRaw(!showRaw)} disabled={busy}>
              {showRaw ? t('Back to the form') : t('Edit raw document')}
            </button>
            <button
              className={loaded.managed ? '' : 'primary'}
              onClick={toggle}
              disabled={busy}
            >
              {loaded.managed ? t('Stop replicating') : t('Replicate')}
            </button>
          </>
        }
      />

      {error ? <Banner kind="error">{error}</Banner> : null}
      {message ? <Banner kind="ok">{message}</Banner> : null}
      {sections.error ? <Banner kind="error">{sections.error}</Banner> : null}
      {loaded.skipped_reason ? (
        <Banner kind="warn">
          {t('Not pushed: {reason}', { reason: loaded.skipped_reason })}
        </Banner>
      ) : null}

      <Card>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 14,
            flexWrap: 'wrap',
          }}
        >
          <Badge tone={loaded.managed ? 'replicated' : 'pending'}>
            {loaded.managed ? t('replicated') : t('not replicated')}
          </Badge>
          <span style={{ color: 'var(--dim)', fontSize: 13 }}>
            {loaded.has_data
              ? t('{count} settings · last changed {when}', {
                  count: loaded.keys.length,
                  when: formatTime(loaded.updated_at),
                })
              : t('Empty — fill in only what the hub should own, or import a master.')}
          </span>
        </div>
      </Card>

      {showRaw ? (
        <Card
          title={t('Section document')}
          hint={t('Exactly what is pushed to each instance, including the keys without a form field above.')}
        >
          <textarea
            value={raw}
            spellCheck={false}
            style={{ minHeight: 380 }}
            onChange={(event) => setRaw(event.target.value)}
          />
        </Card>
      ) : (
        groups.map((group) => (
          <Card key={group.name} title={t(group.name)}>
            <SectionFields fields={group.fields} data={draft} onChange={setDraft} />
          </Card>
        ))
      )}

      <Card>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <button className="primary" onClick={save} disabled={busy}>
            {loaded.managed ? t('Save and push') : t('Save')}
          </button>
          <button onClick={discard} disabled={busy}>
            {t('Discard changes')}
          </button>
          <p style={{ margin: '0 0 0 6px', color: 'var(--dim)', fontSize: 12.5 }}>
            {loaded.managed
              ? t('Saving writes a new hub version and reaches every instance immediately.')
              : t('This area is stored in the hub but not pushed. Switch on Replicate to send it.')}
          </p>
        </div>
      </Card>
    </>
  )
}
