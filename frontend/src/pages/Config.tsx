import { useState } from 'react'
import { api } from '../api/client'
import type { ConfigSection } from '../api/types'
import { SectionFields } from '../components/SectionFields'
import { Badge, Banner, Card, Empty, PageHeader } from '../components/ui'
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

  const startEdit = (section: ConfigSection) => {
    setOpen(open === section.name ? null : section.name)
    setDraft(section.data)
    setRaw(JSON.stringify(section.data, null, 2))
    setShowRaw(false)
    setError('')
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
      setOpen(null)
      return `${section.title} saved${section.managed ? ' and pushed to every instance' : ''}.`
    })
  }

  const list = sections.data ?? []
  const managed = list.filter((item) => item.managed).length

  return (
    <>
      <PageHeader
        title="Instance settings"
        description="Configuration areas replicated from the hub to every instance. DHCP is deliberately excluded — leases and interface bindings are per-host state."
      />

      {error ? <Banner kind="error">{error}</Banner> : null}
      {message ? <Banner kind="ok">{message}</Banner> : null}
      {sections.error ? <Banner kind="error">{sections.error}</Banner> : null}

      {list.length && managed === 0 ? (
        <Banner kind="warn">
          No settings are being replicated yet. Import an instance as the master on the Instances
          page — that adopts every area it exposes and switches them on.
        </Banner>
      ) : null}

      {list.length ? (
        list.map((section) => (
          <Card key={section.name}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                gap: 14,
                alignItems: 'flex-start',
                flexWrap: 'wrap',
              }}
            >
              <div style={{ flex: '1 1 320px' }}>
                <h2 style={{ marginBottom: 4 }}>
                  {section.title}{' '}
                  <Badge tone={section.managed ? 'applied' : 'pending'}>
                    {section.managed ? 'replicated' : 'not replicated'}
                  </Badge>
                </h2>
                <p className="hint" style={{ marginBottom: 6 }}>
                  {section.description}
                </p>
                <p className="hint" style={{ marginBottom: 0 }}>
                  {section.has_data
                    ? `${section.keys.length} setting(s) · updated ${formatTime(section.updated_at)}`
                    : 'Nothing imported yet — import an instance as the master first.'}
                </p>
                {section.skipped_reason ? (
                  <Banner kind="warn">Not pushed: {section.skipped_reason}</Banner>
                ) : null}
                {section.notes ? (
                  <Banner kind={section.risky ? 'error' : 'warn'}>
                    {section.risky ? <strong>Before you enable this: </strong> : null}
                    {section.notes}
                  </Banner>
                ) : null}
              </div>
              <div className="actions">
                <button
                  className="small"
                  onClick={() => startEdit(section)}
                  disabled={busy || !section.has_data}
                >
                  {open === section.name ? 'Close' : 'View / edit'}
                </button>
                <button
                  className={`small${section.managed ? '' : ' primary'}`}
                  onClick={() => toggle(section)}
                  disabled={busy || !section.has_data}
                >
                  {section.managed ? 'Stop replicating' : 'Replicate'}
                </button>
              </div>
            </div>

            {open === section.name ? (
              <div style={{ marginTop: 14, borderTop: '1px solid var(--border)', paddingTop: 14 }}>
                {showRaw ? (
                  <>
                    <label htmlFor={`data-${section.name}`}>
                      Section document — exactly what is pushed to each instance
                    </label>
                    <textarea
                      id={`data-${section.name}`}
                      value={raw}
                      spellCheck={false}
                      style={{ minHeight: 260 }}
                      onChange={(event) => setRaw(event.target.value)}
                    />
                  </>
                ) : section.fields.length ? (
                  <SectionFields fields={section.fields} data={draft} onChange={setDraft} />
                ) : (
                  <p className="hint">This section has no editable fields of its own.</p>
                )}

                <div className="actions" style={{ marginTop: 12 }}>
                  <button className="primary" onClick={() => save(section)} disabled={busy}>
                    Save
                  </button>
                  <button
                    onClick={() => {
                      // Switching views carries the edits across, so neither is a dead end.
                      if (showRaw) {
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
                    disabled={busy}
                  >
                    {showRaw ? 'Back to the form' : 'Edit raw document'}
                  </button>
                  <button onClick={() => setOpen(null)} disabled={busy}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : null}
          </Card>
        ))
      ) : (
        <Empty>{sections.loading ? 'Loading…' : 'No configuration sections.'}</Empty>
      )}
    </>
  )
}
