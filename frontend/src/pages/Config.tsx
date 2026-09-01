import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { ConfigSection } from '../api/types'
import { SectionFields } from '../components/SectionFields'
import { Badge, Banner, Card, Empty, PageHeader } from '../components/ui'
import { IconWarning } from '../components/icons'
import { formatTime } from '../format'
import { errorMessage, useResource } from '../hooks/useApi'
import { useT } from '../i18n'

/**
 * The instance-level settings AdGuardHub replicates. Everything the master exposes
 * is here except DHCP, which is per-host state and would be wrong to copy.
 */
export default function Config() {
  const t = useT()
  const sections = useResource<ConfigSection[]>(() => api.configSections())
  const [open, setOpen] = useState<string | null>(null)
  const [draft, setDraft] = useState<Record<string, unknown>>({})
  const [raw, setRaw] = useState('')
  const [showRaw, setShowRaw] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

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

  const confirmRisk = (section: ConfigSection, action: string) =>
    !section.risky ||
    confirm(`${action}\n\n${section.notes}\n\n` + t('Continue?'))

  const toggle = (section: ConfigSection) => {
    if (
      !section.managed &&
      !confirmRisk(section, t('Start replicating {title}?', { title: t(section.title) }))
    )
      return
    return run(async () => {
      await api.updateSection(section.name, { managed: !section.managed })
      return section.managed
        ? t('{title} is no longer pushed; instances keep their own.', { title: t(section.title) })
        : t('{title} is now pushed to every instance.', { title: t(section.title) })
    })
  }

  const select = (section: ConfigSection) => {
    setOpen(section.name)
    setDraft(section.data)
    setRaw(JSON.stringify(section.data, null, 2))
    setShowRaw(false)
    setError('')
    setMessage('')
  }

  const save = (section: ConfigSection) => {
    let payload = draft
    if (showRaw) {
      try {
        payload = JSON.parse(raw)
      } catch {
        setError(t('That is not valid JSON.'))
        return
      }
    }
    // Only ask when the change actually switches something on — a confirmation on
    // every save would be clicked through without being read.
    const turningOn = Boolean(payload.enabled) && !section.data.enabled
    if (
      turningOn &&
      !confirmRisk(section, t('Switch {title} on for every instance?', { title: t(section.title) }))
    ) {
      return
    }
    return run(async () => {
      await api.updateSection(section.name, { data: payload })
      return section.managed
        ? t('{title} saved and pushed to every instance.', { title: t(section.title) })
        : t('{title} saved.', { title: t(section.title) })
    })
  }

  // Sections with a page of their own are edited there, not in this list. The
  // convention is that such a section is routed at /<its name> — see App.tsx.
  const all = sections.data ?? []
  const list = all.filter((item) => !item.own_page)
  const elsewhere = all.filter((item) => item.own_page)
  const managed = list.filter((item) => item.managed).length
  const current = list.find((item) => item.name === open) ?? list[0] ?? null

  // The right pane always shows something, so the first section loaded seeds the
  // form. Done in an effect, not during render — setting state while rendering is
  // how you get an update loop.
  const first = list[0]
  useEffect(() => {
    if (!first || open !== null) return
    setOpen(first.name)
    setDraft(first.data)
    setRaw(JSON.stringify(first.data, null, 2))
  }, [first, open])

  return (
    <>
      <PageHeader
        title={t('Instance settings')}
        description={t('What the hub replicates to every node. A replicated area is owned by the hub — change it here, and reconciliation puts it back if a node drifts. DHCP is never touched: leases and interface bindings belong to the individual host.')}
      />

      {error ? <Banner kind="error">{error}</Banner> : null}
      {message ? <Banner kind="ok">{message}</Banner> : null}
      {sections.error ? <Banner kind="error">{sections.error}</Banner> : null}

      {elsewhere.length ? (
        <p style={{ margin: '0 0 16px', color: 'var(--dim)', fontSize: 13 }}>
          {elsewhere.length > 1
            ? t('{titles} have pages of their own:', {
                titles: elsewhere.map((item) => t(item.title)).join(', '),
              })
            : t('{title} has a page of its own:', { title: t(elsewhere[0].title) })}{' '}
          {elsewhere.map((item, index) => (
            <span key={item.name}>
              {index ? ', ' : ''}
              <Link to={`/${item.name}`}>{t(item.title)}</Link>
            </span>
          ))}
          .
        </p>
      ) : null}

      {list.length && managed === 0 ? (
        <Banner kind="warn">
          {t(
            'No settings are being replicated yet. Either import an instance as the master on the Instances page, or fill in an area below and switch on Replicate.',
          )}
        </Banner>
      ) : null}

      {list.length ? (
        <div className="split-wide">
          <Card>
            <div
              style={{
                display: 'flex',
                alignItems: 'baseline',
                justifyContent: 'space-between',
                padding: '0 4px 12px',
              }}
            >
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 650,
                  letterSpacing: '0.05em',
                  textTransform: 'uppercase',
                  color: 'var(--dim)',
                }}
              >
                {t('Areas')}
              </span>
              <span style={{ fontSize: 12, color: 'var(--dim)' }}>
                {t('{managed} of {total} replicated', { managed, total: list.length })}
              </span>
            </div>

            <div className="sections">
              {list.map((section) => (
                <button
                  key={section.name}
                  className={`section-item${section.name === current?.name ? ' active' : ''}${
                    section.risky && !section.managed ? ' risky' : ''
                  }`}
                  onClick={() => select(section)}
                >
                  <span className={`dot${section.managed ? '' : ' off'}`} />
                  {t(section.title)}
                  {section.risky && !section.managed ? (
                    <span style={{ color: 'var(--danger-ink)', display: 'inline-flex' }}>
                      <IconWarning size={14} />
                    </span>
                  ) : null}
                  <span className="count">
                    {section.has_data ? section.keys.length : '—'}
                  </span>
                </button>
              ))}
            </div>

            <div
              style={{
                borderTop: '1px solid var(--line)',
                marginTop: 12,
                padding: '12px 4px 2px',
                color: 'var(--dim)',
                fontSize: 12,
                display: 'flex',
                gap: 16,
                flexWrap: 'wrap',
              }}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span className="dot" style={dotStyle('var(--accent)')} />
                {t('replicated')}
              </span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span className="dot" style={dotStyle('var(--danger)')} />
                {t('left to each node')}
              </span>
            </div>
          </Card>

          {current ? (
            <Card>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  justifyContent: 'space-between',
                  gap: 16,
                  borderBottom: '1px solid var(--line)',
                  paddingBottom: 16,
                  marginBottom: 18,
                  flexWrap: 'wrap',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap' }}>
                    <h2 style={{ fontSize: 16 }}>{t(current.title)}</h2>
                    <Badge tone={current.managed ? 'replicated' : 'pending'}>
                      {current.managed ? t('replicated') : t('not replicated')}
                    </Badge>
                  </div>
                  <p className="hint" style={{ margin: '4px 0 0' }}>
                    {t(current.description)}
                  </p>
                  <p className="hint" style={{ margin: '3px 0 0' }}>
                    {current.has_data
                      ? t('{count} setting(s) · updated {when}', {
                          count: current.keys.length,
                          when: formatTime(current.updated_at),
                        })
                      : t('Empty — fill in only what the hub should own, or import a master.')}
                  </p>
                </div>
                <div className="actions">
                  <button
                    className="small"
                    onClick={() => {
                      if (showRaw) {
                        // Switching views carries the edits across, so neither is a dead end.
                        try {
                          setDraft(JSON.parse(raw))
                        } catch {
                          setError(t('That is not valid JSON — fix it before switching back.'))
                          return
                        }
                      } else {
                        setRaw(JSON.stringify(draft, null, 2))
                      }
                      setShowRaw(!showRaw)
                    }}
                    disabled={busy}
                  >
                    {showRaw ? t('Back to the form') : t('Edit raw document')}
                  </button>
                  <button
                    className={`small${current.managed ? '' : ' primary'}`}
                    onClick={() => toggle(current)}
                    disabled={busy}
                  >
                    {current.managed ? t('Stop replicating') : t('Replicate')}
                  </button>
                </div>
              </div>

              {current.skipped_reason ? (
                <Banner kind="warn">{t('Not pushed: {reason}', { reason: current.skipped_reason })}</Banner>
              ) : null}
              {current.notes ? (
                <Banner kind={current.risky ? 'error' : 'warn'}>
                  {current.risky ? <strong>{t('Before you enable this:')} </strong> : null}
                  {t(current.notes)}
                </Banner>
              ) : null}

              {showRaw ? (
                <>
                  <label htmlFor={`data-${current.name}`}>
                    {t('Section document — exactly what is pushed to each instance')}
                  </label>
                  <textarea
                    id={`data-${current.name}`}
                    value={raw}
                    spellCheck={false}
                    style={{ minHeight: 300 }}
                    onChange={(event) => setRaw(event.target.value)}
                  />
                </>
              ) : current.fields.length ? (
                <SectionFields fields={current.fields} data={draft} onChange={setDraft} />
              ) : (
                <p className="hint">{t('This section has no editable fields of its own.')}</p>
              )}

              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  borderTop: '1px solid var(--line)',
                  marginTop: 20,
                  paddingTop: 16,
                  flexWrap: 'wrap',
                }}
              >
                <button className="primary" onClick={() => save(current)} disabled={busy}>
                  {current.managed ? t('Save and push') : t('Save')}
                </button>
                <button onClick={() => select(current)} disabled={busy}>
                  {t('Discard changes')}
                </button>
                <p style={{ margin: '0 0 0 6px', color: 'var(--dim)', fontSize: 12.5 }}>
                  {current.managed
                    ? t(
                        'Saving writes a new hub version and pushes this area to every instance immediately.',
                      )
                    : t(
                        'This area is stored in the hub but not pushed. Switch on Replicate to send it.',
                      )}
                </p>
              </div>
            </Card>
          ) : null}
        </div>
      ) : (
        <Empty>{sections.loading ? t('Loading…') : t('No configuration sections.')}</Empty>
      )}
    </>
  )
}

const dotStyle = (background: string) => ({
  width: 7,
  height: 7,
  borderRadius: '50%',
  display: 'inline-block',
  background,
})
