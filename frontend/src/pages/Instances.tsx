import { useState } from 'react'
import { api } from '../api/client'
import type { Instance } from '../api/types'
import { Badge, Banner, Card, Empty, PageHeader } from '../components/ui'
import { formatTime } from '../format'
import { errorMessage, useResource } from '../hooks/useApi'

const BLANK = {
  name: '',
  base_url: 'http://',
  username: '',
  password: '',
  verify_tls: true,
}

export default function Instances() {
  const instances = useResource<Instance[]>(() => api.instances())
  const [form, setForm] = useState({ ...BLANK })
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

  const add = (event: React.FormEvent) => {
    event.preventDefault()
    void run(async () => {
      const created = await api.createInstance(form)
      setForm({ ...BLANK })
      return `Added ${created.name}.`
    })
  }

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
      const result = await api.importInstance(instance.id, { replace: true, include_dns: false })
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

      <Card title="Add an instance">
        <form onSubmit={add}>
          <div className="row">
            <div className="field">
              <label htmlFor="name">Name</label>
              <input
                id="name"
                value={form.name}
                placeholder="adguard-primary"
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="url">Base URL</label>
              <input
                id="url"
                value={form.base_url}
                placeholder="http://192.168.1.2:3000"
                onChange={(event) => setForm({ ...form, base_url: event.target.value })}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="user">Admin username</label>
              <input
                id="user"
                value={form.username}
                autoComplete="off"
                onChange={(event) => setForm({ ...form, username: event.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="pass">Admin password</label>
              <input
                id="pass"
                type="password"
                value={form.password}
                autoComplete="new-password"
                onChange={(event) => setForm({ ...form, password: event.target.value })}
              />
            </div>
          </div>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={form.verify_tls}
              onChange={(event) => setForm({ ...form, verify_tls: event.target.checked })}
            />
            Verify the TLS certificate (turn off for a self-signed HTTPS instance)
          </label>
          <button className="primary" type="submit" disabled={busy}>
            Add instance
          </button>
        </form>
      </Card>

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
