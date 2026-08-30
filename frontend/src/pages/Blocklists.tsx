import { useState } from 'react'
import { api } from '../api/client'
import type { FilterList, ListKind } from '../api/types'
import { Badge, Banner, Card, Empty, PageHeader } from '../components/ui'
import { errorMessage, useResource } from '../hooks/useApi'

export default function Blocklists() {
  const lists = useResource<FilterList[]>(() => api.filterLists())
  const [form, setForm] = useState<{ name: string; url: string; kind: ListKind }>({
    name: '',
    url: '',
    kind: 'blocklist',
  })
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
      await lists.reload()
    }
  }

  const add = (event: React.FormEvent) => {
    event.preventDefault()
    void run(async () => {
      const created = await api.createFilterList(form)
      setForm({ name: '', url: '', kind: 'blocklist' })
      return `Subscribed to ${created.name} — pushing to all instances.`
    })
  }

  const toggle = (item: FilterList) =>
    run(async () => {
      await api.updateFilterList(item.id, { enabled: !item.enabled })
      return `${item.name} is now ${item.enabled ? 'disabled' : 'enabled'} everywhere.`
    })

  const remove = (item: FilterList) =>
    run(async () => {
      await api.deleteFilterList(item.id)
      return `Removed ${item.name}.`
    })

  return (
    <>
      <PageHeader
        title="Subscriptions"
        description="Blocklist and allowlist subscription URLs. AdGuardHub tracks the URL and whether it is enabled — AdGuard Home still downloads and applies the list itself."
      />

      {error ? <Banner kind="error">{error}</Banner> : null}
      {message ? <Banner kind="ok">{message}</Banner> : null}
      {lists.error ? <Banner kind="error">{lists.error}</Banner> : null}

      <Card title="Add a subscription">
        <form onSubmit={add} className="row">
          <div className="field">
            <label htmlFor="list-name">Name</label>
            <input
              id="list-name"
              value={form.name}
              placeholder="AdGuard DNS filter"
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              required
            />
          </div>
          <div className="field" style={{ flex: '2 1 320px' }}>
            <label htmlFor="list-url">URL</label>
            <input
              id="list-url"
              value={form.url}
              placeholder="https://adguardteam.github.io/HostlistsRegistry/assets/filter_1.txt"
              onChange={(event) => setForm({ ...form, url: event.target.value })}
              required
            />
          </div>
          <div className="field fixed" style={{ width: 150 }}>
            <label htmlFor="list-kind">Type</label>
            <select
              id="list-kind"
              value={form.kind}
              onChange={(event) => setForm({ ...form, kind: event.target.value as ListKind })}
            >
              <option value="blocklist">Blocklist</option>
              <option value="allowlist">Allowlist</option>
            </select>
          </div>
          <div className="field fixed">
            <button className="primary" type="submit" disabled={busy}>
              Add
            </button>
          </div>
        </form>
      </Card>

      <Card title="Subscriptions">
        {lists.data && lists.data.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>URL</th>
                  <th>Type</th>
                  <th>State</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {lists.data.map((item) => (
                  <tr key={item.id} style={{ opacity: item.enabled ? 1 : 0.55 }}>
                    <td>{item.name}</td>
                    <td className="mono">{item.url}</td>
                    <td>
                      <Badge tone={item.kind === 'allowlist' ? 'allow' : 'block'}>{item.kind}</Badge>
                    </td>
                    <td>{item.enabled ? 'enabled' : 'disabled'}</td>
                    <td className="right">
                      <button className="small" onClick={() => toggle(item)} disabled={busy}>
                        {item.enabled ? 'Disable' : 'Enable'}
                      </button>{' '}
                      <button className="small danger" onClick={() => remove(item)} disabled={busy}>
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>No subscriptions yet.</Empty>
        )}
      </Card>
    </>
  )
}
