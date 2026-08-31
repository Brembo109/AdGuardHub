import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Instance } from '../api/types'
import { InstanceForm } from '../components/InstanceForm'
import { BLANK_DRAFT, type InstanceDraft, draftFrom } from '../components/instanceDraft'
import { Badge, Banner, Card, Empty, PageHeader } from '../components/ui'
import { IconDots } from '../components/icons'
import { formatTime } from '../format'
import { errorMessage, useResource } from '../hooks/useApi'

export default function Instances() {
  const instances = useResource<Instance[]>(() => api.instances())
  const [draft, setDraft] = useState<InstanceDraft>({ ...BLANK_DRAFT })
  const [editing, setEditing] = useState<Instance | null>(null)
  const [editDraft, setEditDraft] = useState<InstanceDraft>({ ...BLANK_DRAFT })
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
      await instances.reload()
    }
  }

  const add = () =>
    run(async () => {
      const created = await api.createInstance(draft)
      setDraft({ ...BLANK_DRAFT })
      return `Added ${created.name}.`
    })

  const startEdit = (instance: Instance) => {
    setEditing(instance)
    setEditDraft(draftFrom(instance))
    setError('')
    setMessage('')
  }

  const saveEdit = () =>
    run(async () => {
      if (!editing) return ''
      // An untouched password field must not wipe the stored credential.
      const payload: Record<string, unknown> = {
        name: editDraft.name,
        base_url: editDraft.base_url,
        username: editDraft.username,
        verify_tls: editDraft.verify_tls,
      }
      if (editDraft.password) payload.password = editDraft.password
      const updated = await api.updateInstance(editing.id, payload)
      setEditing(null)
      return `Saved ${updated.name}.`
    })

  const toggle = (instance: Instance) =>
    run(async () => {
      await api.updateInstance(instance.id, { enabled: !instance.enabled })
      return `${instance.name} is now ${instance.enabled ? 'disabled' : 'enabled'}.`
    })

  const test = (instance: Instance) =>
    run(async () => {
      const result = await api.testInstance(instance.id)
      return `${instance.name} responded — AdGuard Home ${result.version}.`
    })

  const push = (instance: Instance) =>
    run(async () => {
      const result = await api.pushInstance(instance.id)
      return result.error
        ? `Push to ${instance.name} failed: ${result.error}`
        : `${instance.name} now has the full hub configuration.`
    })

  const remove = (instance: Instance) => {
    if (!confirm(`Remove ${instance.name} from AdGuardHub? Its own configuration is left as-is.`))
      return
    void run(async () => {
      await api.deleteInstance(instance.id)
      if (editing?.id === instance.id) setEditing(null)
      return `Removed ${instance.name}.`
    })
  }

  const importFrom = (instance: Instance) => {
    if (
      !confirm(
        `Import ${instance.name}'s configuration as the hub's state?\n\n` +
          'This replaces every rule, subscription and instance setting in AdGuardHub, then ' +
          'pushes the result to all other instances — overwriting whatever they currently have.\n\n' +
          'Encryption is the exception: it is adopted but left switched off, because enabling it ' +
          'on a node without a valid certificate would make that node unreachable.',
      )
    )
      return
    void run(async () => {
      const result = await api.importInstance(instance.id, { replace: true })
      const review = result.sections_needing_review.length
        ? ` ${result.sections_needing_review.join(', ')} was adopted but left switched off — enabling it can make a node unreachable, so review it under Instance settings first.`
        : ''
      return `Imported ${result.rules_imported} rule(s), ${result.filter_lists_imported} subscription(s) and ${result.sections_imported.length} settings area(s) from ${result.instance}; pushing to the other instances now.${review}`
    })
  }

  return (
    <>
      <PageHeader
        title="Instances"
        description="Add each AdGuard Home instance once. Credentials are encrypted at rest with the key from ADGUARDHUB_SECRET_KEY and are never sent back to the browser."
      />

      {error ? <Banner kind="error">{error}</Banner> : null}
      {message ? <Banner kind="ok">{message}</Banner> : null}
      {instances.error ? <Banner kind="error">{instances.error}</Banner> : null}

      {editing ? (
        <Card title={`Edit ${editing.name}`} hint="Test the connection before saving.">
          <InstanceForm
            draft={editDraft}
            onChange={setEditDraft}
            onSubmit={saveEdit}
            onCancel={() => setEditing(null)}
            submitLabel="Save changes"
            busy={busy}
            existingId={editing.id}
          />
        </Card>
      ) : (
        <Card
          title="Add an instance"
          hint="Test the connection first — it verifies the URL and credentials without saving anything."
        >
          <InstanceForm
            draft={draft}
            onChange={setDraft}
            onSubmit={add}
            submitLabel="Add instance"
            busy={busy}
          />
        </Card>
      )}

      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          gap: 16,
          margin: '22px 0 12px',
          flexWrap: 'wrap',
        }}
      >
        <h2 style={{ margin: 0, fontSize: 16, fontWeight: 620 }}>Connected instances</h2>
        <p style={{ margin: 0, color: 'var(--dim)', fontSize: 13 }}>
          Importing one instance as the master replaces the hub state and overwrites every other
          node on the next push.
        </p>
      </div>

      {instances.data && instances.data.length ? (
        <div className="cards-3">
          {instances.data.map((instance) => (
            <NodeCard
              key={instance.id}
              instance={instance}
              busy={busy}
              onEdit={() => startEdit(instance)}
              onTest={() => test(instance)}
              onPush={() => push(instance)}
              onImport={() => importFrom(instance)}
              onToggle={() => toggle(instance)}
              onRemove={() => remove(instance)}
            />
          ))}
        </div>
      ) : (
        <Card>
          <Empty>No instances configured yet.</Empty>
        </Card>
      )}
    </>
  )
}

interface NodeCardProps {
  instance: Instance
  busy: boolean
  onEdit: () => void
  onTest: () => void
  onPush: () => void
  onImport: () => void
  onToggle: () => void
  onRemove: () => void
}

/**
 * One node per card. Only the everyday actions get a button; importing as master,
 * disabling and removing sit in the overflow — putting "Remove" next to "Push now"
 * at the same weight is how the wrong one gets clicked.
 */
function NodeCard({
  instance,
  busy,
  onEdit,
  onTest,
  onPush,
  onImport,
  onToggle,
  onRemove,
}: NodeCardProps) {
  const [menu, setMenu] = useState(false)
  const wrap = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!menu) return
    const close = (event: MouseEvent) => {
      if (!wrap.current?.contains(event.target as Node)) setMenu(false)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMenu(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', escape)
    }
  }, [menu])

  const down = instance.status === 'unreachable'
  const run = (action: () => void) => () => {
    setMenu(false)
    action()
  }

  return (
    <div className={`node-card${down ? ' down' : ''}`}>
      <div className="node-head">
        <span
          className={`node-dot${down ? ' down' : instance.enabled ? '' : ' off'}`}
        />
        <span className="name">{instance.name}</span>
        <Badge tone={instance.status}>{instance.status}</Badge>
      </div>
      <div className="mono" style={{ color: 'var(--dim)', marginBottom: 16 }}>
        {instance.base_url}
      </div>

      <div className="node-facts">
        <div>
          <div className="dl">Adapter</div>
          <div style={{ fontSize: 13 }}>{instance.adapter}</div>
        </div>
        <div>
          <div className="dl">Last synced</div>
          <div style={{ fontSize: 13 }}>{formatTime(instance.last_synced_at)}</div>
        </div>
        <div>
          <div className="dl">Last seen</div>
          <div style={{ fontSize: 13 }}>{formatTime(instance.last_seen_at)}</div>
        </div>
      </div>

      {instance.last_error ? (
        <div
          className="mono"
          style={{
            color: 'var(--danger-ink)',
            background: 'var(--danger-soft)',
            borderRadius: 6,
            padding: '7px 10px',
            marginBottom: 14,
          }}
        >
          {instance.last_error}
        </div>
      ) : null}

      <div className="node-actions">
        <button className="small" onClick={onEdit} disabled={busy}>
          Edit
        </button>
        <button className="small" onClick={onTest} disabled={busy}>
          Test
        </button>
        <button className="small" onClick={onPush} disabled={busy}>
          Push now
        </button>
        <div className="menu" ref={wrap}>
          <button
            className="small"
            onClick={() => setMenu(!menu)}
            disabled={busy}
            aria-label={`More actions for ${instance.name}`}
            aria-expanded={menu}
          >
            <IconDots />
          </button>
          {menu ? (
            <div className="menu-list">
              <button onClick={run(onImport)}>Import as master</button>
              <button onClick={run(onToggle)}>{instance.enabled ? 'Disable' : 'Enable'}</button>
              <button className="danger" onClick={run(onRemove)}>
                Remove
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
