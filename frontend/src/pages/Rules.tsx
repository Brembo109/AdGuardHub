import { useState } from 'react'
import { api } from '../api/client'
import type { Rule, RuleKind, RuleOrigin } from '../api/types'
import { Badge, Banner, Card, Empty, PageHeader } from '../components/ui'
import { formatTime } from '../format'
import { errorMessage, useResource } from '../hooks/useApi'

type Tab = 'all' | 'block' | 'allow'

/**
 * Two of the three AdGuard entry points live here: free-form custom rules and the
 * Allowlist tab. The third (the query log's whitelist action) writes the same model
 * from the Query log page.
 */
export default function Rules() {
  const [tab, setTab] = useState<Tab>('all')
  const [search, setSearch] = useState('')
  const kind: RuleKind | undefined = tab === 'all' ? undefined : tab
  const rules = useResource<Rule[]>(() => api.rules({ kind, search }), [tab, search])

  const [text, setText] = useState('')
  const [domain, setDomain] = useState('')
  const [bulk, setBulk] = useState('')
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
      await rules.reload()
    }
  }

  const addRule = (event: React.FormEvent) => {
    event.preventDefault()
    void run(async () => {
      const created = await api.createRule({ text, origin: 'custom' })
      setText('')
      return `Added ${created.text} — pushing to all instances.`
    })
  }

  const addAllow = (event: React.FormEvent) => {
    event.preventDefault()
    void run(async () => {
      const created = await api.allowDomain(domain, 'allowlist')
      setDomain('')
      return `Allowlisted ${created.text} — pushing to all instances.`
    })
  }

  const addBulk = (event: React.FormEvent) => {
    event.preventDefault()
    void run(async () => {
      const created = await api.bulkRules(bulk, 'custom')
      setBulk('')
      return created.length
        ? `Imported ${created.length} new rule(s).`
        : 'Nothing new — every line was a duplicate, blank or a comment.'
    })
  }

  const toggle = (rule: Rule) =>
    run(async () => {
      await api.updateRule(rule.id, { enabled: !rule.enabled })
      return `${rule.text} is now ${rule.enabled ? 'disabled' : 'enabled'}.`
    })

  const remove = (rule: Rule) =>
    run(async () => {
      await api.deleteRule(rule.id)
      return `Removed ${rule.text}.`
    })

  return (
    <>
      <PageHeader
        title="Filtering rules"
        description="The central rule set, in native AdGuard syntax. Every change is pushed to all instances straight away."
      />

      {error ? <Banner kind="error">{error}</Banner> : null}
      {message ? <Banner kind="ok">{message}</Banner> : null}
      {rules.error ? <Banner kind="error">{rules.error}</Banner> : null}

      <div className="row" style={{ alignItems: 'stretch' }}>
        <Card title="Custom rule" hint="Any AdGuard rule, e.g. ||ads.example.com^ or @@||shop.example.com^">
          <form onSubmit={addRule} className="row">
            <input
              value={text}
              placeholder="||ads.example.com^"
              onChange={(event) => setText(event.target.value)}
              required
            />
            <button className="primary fixed" type="submit" disabled={busy}>
              Add
            </button>
          </form>
        </Card>

        <Card title="Allowlist" hint="A domain to never block; stored as an @@ exception rule.">
          <form onSubmit={addAllow} className="row">
            <input
              value={domain}
              placeholder="shop.example.com"
              onChange={(event) => setDomain(event.target.value)}
              required
            />
            <button className="primary fixed" type="submit" disabled={busy}>
              Allow
            </button>
          </form>
        </Card>
      </div>

      <Card
        title="Bulk import"
        hint="Paste AdGuard syntax, one rule per line. Blank lines and ! / # comments are skipped."
      >
        <form onSubmit={addBulk}>
          <textarea
            value={bulk}
            onChange={(event) => setBulk(event.target.value)}
            placeholder={'||ads.example.com^\n@@||shop.example.com^'}
          />
          <button type="submit" disabled={busy || !bulk.trim()} style={{ marginTop: 10 }}>
            Import rules
          </button>
        </form>
      </Card>

      <Card>
        <div className="tabs">
          {(['all', 'block', 'allow'] as Tab[]).map((item) => (
            <button
              key={item}
              className={`tab${tab === item ? ' active' : ''}`}
              onClick={() => setTab(item)}
            >
              {item === 'all' ? 'All' : item === 'block' ? 'Block' : 'Allow'}
            </button>
          ))}
          <div style={{ marginLeft: 'auto', paddingBottom: 6, width: 220 }}>
            <input
              value={search}
              placeholder="Search rules…"
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
        </div>

        {rules.data && rules.data.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Rule</th>
                  <th>Kind</th>
                  <th>Added via</th>
                  <th>Updated</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rules.data.map((rule) => (
                  <tr key={rule.id} style={{ opacity: rule.enabled ? 1 : 0.55 }}>
                    <td className="mono">{rule.text}</td>
                    <td>
                      <Badge tone={rule.kind}>{rule.kind}</Badge>
                    </td>
                    <td>{originLabel(rule.origin)}</td>
                    <td>{formatTime(rule.updated_at)}</td>
                    <td className="right">
                      <button className="small" onClick={() => toggle(rule)} disabled={busy}>
                        {rule.enabled ? 'Disable' : 'Enable'}
                      </button>{' '}
                      <button className="small danger" onClick={() => remove(rule)} disabled={busy}>
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>{rules.loading ? 'Loading…' : 'No rules match.'}</Empty>
        )}
      </Card>
    </>
  )
}

function originLabel(origin: RuleOrigin): string {
  if (origin === 'querylog') return 'Query log'
  if (origin === 'allowlist') return 'Allowlist'
  return 'Custom rule'
}
