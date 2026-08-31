import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { ConfigSection } from '../api/types'
import { SectionFields } from '../components/SectionFields'
import { Badge, Banner, Card, Empty, PageHeader } from '../components/ui'
import { IconWarning } from '../components/icons'
import { formatTime } from '../format'
import { errorMessage, useResource } from '../hooks/useApi'

/**
 * The instance-level settings AdGuardHub replicates. Everything the master exposes
 * is here except DHCP, which is per-host state and would be wrong to copy.
 */
export default function Config() {
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
    confirm(`${action}\n\n${section.notes}\n\nContinue?`)

  const toggle = (section: ConfigSection) => {
    if (!section.managed && !confirmRisk(section, `Start replicating ${section.title}?`)) return
    return run(async () => {
      await api.updateSection(section.name, { managed: !section.managed })
      return section.managed
        ? `${section.title} is no longer pushed; instances keep their own.`
        : `${section.title} is now pushed to every instance.`
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
        setError('That is not valid JSON.')
        return
      }
    }
    // Only ask when the change actually switches something on — a confirmation on
    // every save would be clicked through without being read.
    const turningOn = Boolean(payload.enabled) && !section.data.enabled
    if (turningOn && !confirmRisk(section, `Switch ${section.title} on for every instance?`)) {
      return
    }
    return run(async () => {
      await api.updateSection(section.name, { data: payload })
      return `${section.title} saved${section.managed ? ' and pushed to every instance' : ''}.`
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
        title="Instance settings"
        description="What the hub replicates to every node. A replicated area is owned by the hub — change it here, and reconciliation puts it back if a node drifts. DHCP is never touched: leases and interface bindings belong to the individual host."
      />

      {error ? <Banner kind="error">{error}</Banner> : null}
      {message ? <Banner kind="ok">{message}</Banner> : null}
      {sections.error ? <Banner kind="error">{sections.error}</Banner> : null}

      {elsewhere.length ? (
        <p style={{ margin: '0 0 16px', color: 'var(--dim)', fontSize: 13 }}>
          {elsewhere.map((item) => item.title).join(', ')} {elsewhere.length > 1 ? 'have' : 'has'}{' '}
          a page of {elsewhere.length > 1 ? 'their' : 'its' } own:{' '}
          {elsewhere.map((item, index) => (
            <span key={item.name}>
              {index ? ', ' : ''}
              <Link to={`/${item.name}`}>{item.title}</Link>
            </span>
          ))}
          .
        </p>
      ) : null}

      {list.length && managed === 0 ? (
        <Banner kind="warn">
          No settings are being replicated yet. Import an instance as the master on the Instances
          page — that adopts every area it exposes and switches them on.
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
                Areas
              </span>
              <span style={{ fontSize: 12, color: 'var(--dim)' }}>
                {managed} of {list.length} replicated
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
                  {section.title}
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
                replicated
              </span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span className="dot" style={dotStyle('var(--danger)')} />
                left to each node
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
                    <h2 style={{ fontSize: 16 }}>{current.title}</h2>
                    <Badge tone={current.managed ? 'replicated' : 'pending'}>
                      {current.managed ? 'replicated' : 'not replicated'}
                    </Badge>
                  </div>
                  <p className="hint" style={{ margin: '4px 0 0' }}>
                    {current.description}
                  </p>
                  <p className="hint" style={{ margin: '3px 0 0' }}>
                    {current.has_data
                      ? `${current.keys.length} setting(s) · updated ${formatTime(current.updated_at)}`
                      : 'Nothing imported yet — import an instance as the master first.'}
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
                          setError('That is not valid JSON — fix it before switching back.')
                          return
                        }
                      } else {
                        setRaw(JSON.stringify(draft, null, 2))
                      }
                      setShowRaw(!showRaw)
                    }}
                    disabled={busy || !current.has_data}
                  >
                    {showRaw ? 'Back to the form' : 'Edit raw document'}
                  </button>
                  <button
                    className={`small${current.managed ? '' : ' primary'}`}
                    onClick={() => toggle(current)}
                    disabled={busy || !current.has_data}
                  >
                    {current.managed ? 'Stop replicating' : 'Replicate'}
                  </button>
                </div>
              </div>

              {current.skipped_reason ? (
                <Banner kind="warn">Not pushed: {current.skipped_reason}</Banner>
              ) : null}
              {current.notes ? (
                <Banner kind={current.risky ? 'error' : 'warn'}>
                  {current.risky ? <strong>Before you enable this: </strong> : null}
                  {current.notes}
                </Banner>
              ) : null}

              {!current.has_data ? (
                <Empty>Nothing imported yet — import an instance as the master first.</Empty>
              ) : showRaw ? (
                <>
                  <label htmlFor={`data-${current.name}`}>
                    Section document — exactly what is pushed to each instance
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
                <p className="hint">This section has no editable fields of its own.</p>
              )}

              {current.has_data ? (
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
                    {current.managed ? 'Save and push' : 'Save'}
                  </button>
                  <button onClick={() => select(current)} disabled={busy}>
                    Discard changes
                  </button>
                  <p style={{ margin: '0 0 0 6px', color: 'var(--dim)', fontSize: 12.5 }}>
                    {current.managed
                      ? 'Saving writes a new hub version and pushes this area to every instance immediately.'
                      : 'This area is stored in the hub but not pushed. Switch on Replicate to send it.'}
                  </p>
                </div>
              ) : null}
            </Card>
          ) : null}
        </div>
      ) : (
        <Empty>{sections.loading ? 'Loading…' : 'No configuration sections.'}</Empty>
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
