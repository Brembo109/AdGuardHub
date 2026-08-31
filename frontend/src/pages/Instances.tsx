import { useState } from 'react'
import { api } from '../api/client'
import type { Instance } from '../api/types'
import { InstanceForm } from '../components/InstanceForm'
import { BLANK_DRAFT, type InstanceDraft, draftFrom } from '../components/instanceDraft'
import { Badge, Banner, Card, Empty, PageHeader } from '../components/ui'
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
          'This replaces every rule and subscription in AdGuardHub, then pushes the result to all ' +
          'other instances — overwriting whatever they currently have.',
      )
    )
      return
    void run(async () => {
      const result = await api.importInstance(instance.id, { replace: true })
      return `Imported ${result.rules_imported} rule(s) and ${result.filter_lists_imported} subscription(s) from ${result.instance}; pushing to the other instances now.`
    })
  }

  return (
    <>
      <PageHeader
        title="Instances"
        description="Add each AdGuard Home instance once. Credentials are encrypted at rest and never sent back to the browser."
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
        <Card title="Add an instance" hint="Test the connection first — it verifies the URL and credentials without saving.">
          <InstanceForm
            draft={draft}
            onChange={setDraft}
            onSubmit={add}
            submitLabel="Add instance"
            busy={busy}
          />
        </Card>
      )}

      <Card
        title="Connected instances"
        hint="Import one instance as the master to seed the hub; the others are overwritten on the next push."
      >
        {instances.data && instances.data.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>URL</th>
                  <th>Status</th>
                  <th>Last synced</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {instances.data.map((instance) => (
                  <tr key={instance.id}>
                    <td>{instance.name}</td>
                    <td className="mono">{instance.base_url}</td>
                    <td>
                      <Badge tone={instance.status}>{instance.status}</Badge>
                      {instance.last_error ? (
                        <div className="mono" style={{ color: 'var(--danger)', marginTop: 4 }}>
                          {instance.last_error}
                        </div>
                      ) : null}
                    </td>
                    <td>{formatTime(instance.last_synced_at)}</td>
                    <td className="right">
                      <button className="small" onClick={() => startEdit(instance)} disabled={busy}>
                        Edit
                      </button>{' '}
                      <button className="small" onClick={() => test(instance)} disabled={busy}>
                        Test
                      </button>{' '}
                      <button className="small" onClick={() => push(instance)} disabled={busy}>
                        Push
                      </button>{' '}
                      <button className="small" onClick={() => importFrom(instance)} disabled={busy}>
                        Import as master
                      </button>{' '}
                      <button className="small" onClick={() => toggle(instance)} disabled={busy}>
                        {instance.enabled ? 'Disable' : 'Enable'}
                      </button>{' '}
                      <button
                        className="small danger"
                        onClick={() => remove(instance)}
                        disabled={busy}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>No instances configured yet.</Empty>
        )}
      </Card>
    </>
  )
}
