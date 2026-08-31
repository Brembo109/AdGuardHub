import { useState } from 'react'
import { api } from '../api/client'
import type { FilterList, ListKind } from '../api/types'
import { Badge, Banner, Card, Empty, PageHeader } from '../components/ui'
import { errorMessage, useResource } from '../hooks/useApi'
import { useT } from '../i18n'

export default function Blocklists() {
  const t = useT()
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
      return t('Subscribed to {name} — pushing to all instances.', { name: created.name })
    })
  }

  const toggle = (item: FilterList) =>
    run(async () => {
      await api.updateFilterList(item.id, { enabled: !item.enabled })
      return item.enabled
        ? t('{name} is now disabled everywhere.', { name: item.name })
        : t('{name} is now enabled everywhere.', { name: item.name })
    })

  const remove = (item: FilterList) =>
    run(async () => {
      await api.deleteFilterList(item.id)
      return t('Removed {name}.', { name: item.name })
    })

  return (
    <>
      <PageHeader
        title={t('Subscriptions')}
        description={t(
          'Blocklist and allowlist subscription URLs. AdGuardHub tracks the URL and whether it is enabled — AdGuard Home still downloads and applies the list itself.',
        )}
      />

      {error ? <Banner kind="error">{error}</Banner> : null}
      {message ? <Banner kind="ok">{message}</Banner> : null}
      {lists.error ? <Banner kind="error">{lists.error}</Banner> : null}

      <Card title={t('Add a subscription')}>
        <form onSubmit={add} className="row">
          <div className="field">
            <label htmlFor="list-name">{t('Name')}</label>
            <input
              id="list-name"
              value={form.name}
              placeholder={t('AdGuard DNS filter')}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              required
            />
          </div>
          <div className="field" style={{ flex: '2 1 320px' }}>
            <label htmlFor="list-url">{t('URL')}</label>
            <input
              id="list-url"
              value={form.url}
              placeholder="https://adguardteam.github.io/HostlistsRegistry/assets/filter_1.txt"
              onChange={(event) => setForm({ ...form, url: event.target.value })}
              required
            />
          </div>
          <div className="field fixed" style={{ width: 150 }}>
            <label htmlFor="list-kind">{t('Type')}</label>
            <select
              id="list-kind"
              value={form.kind}
              onChange={(event) => setForm({ ...form, kind: event.target.value as ListKind })}
            >
              <option value="blocklist">{t('Blocklist')}</option>
              <option value="allowlist">{t('Allowlist')}</option>
            </select>
          </div>
          <div className="field fixed">
            <button className="primary" type="submit" disabled={busy}>
              {t('Add')}
            </button>
          </div>
        </form>
      </Card>

      <Card title={t('Subscriptions')}>
        {lists.data && lists.data.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t('Name')}</th>
                  <th>{t('URL')}</th>
                  <th>{t('Type')}</th>
                  <th>{t('State')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {lists.data.map((item) => (
                  <tr key={item.id} style={{ opacity: item.enabled ? 1 : 0.55 }}>
                    <td>{item.name}</td>
                    <td className="mono">{item.url}</td>
                    <td>
                      <Badge tone={item.kind === 'allowlist' ? 'allow' : 'block'}>{t(item.kind)}</Badge>
                    </td>
                    <td>{item.enabled ? 'enabled' : 'disabled'}</td>
                    <td className="right">
                      <button className="small" onClick={() => toggle(item)} disabled={busy}>
                        {item.enabled ? t('Disable') : t('Enable')}
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
          <Empty>{t('No subscriptions yet.')}</Empty>
        )}
      </Card>
    </>
  )
}
