import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Instance, QueryLogEntry } from '../api/types'
import { Badge, Banner, Card, Empty, PageHeader } from '../components/ui'
import { formatTime } from '../format'
import { errorMessage, useResource } from '../hooks/useApi'
import { useEventStream } from '../hooks/useEventStream'

const MAX_ROWS = 500

/**
 * The aggregated view across every instance. The "Allow"/"Block" buttons write to the
 * central rule model and push to all instances — no matter which instance logged the row.
 */
export default function QueryLog() {
  const instances = useResource<Instance[]>(() => api.instances())
  const [rows, setRows] = useState<QueryLogEntry[]>([])
  const [search, setSearch] = useState('')
  const [instance, setInstance] = useState('')
  const [blockedOnly, setBlockedOnly] = useState(false)
  const [live, setLive] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const filters = useRef({ search, instance, blockedOnly, live })
  filters.current = { search, instance, blockedOnly, live }

  const load = useCallback(async () => {
    try {
      setRows(
        await api.queryLog({
          limit: MAX_ROWS,
          search,
          instance,
          blocked_only: blockedOnly,
        }),
      )
      setError('')
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }, [search, instance, blockedOnly])

  useEffect(() => {
    void load()
  }, [load])

  // New entries arrive over SSE; re-reading the filtered snapshot keeps the
  // filter logic in one place (the backend) rather than duplicating it here.
  const connected = useEventStream((event) => {
    if (event.event === 'querylog' && filters.current.live) void load()
  })

  async function act(entry: QueryLogEntry, mode: 'allow' | 'block') {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const rule =
        mode === 'allow'
          ? await api.allowDomain(entry.question, 'querylog')
          : await api.blockDomain(entry.question, 'querylog')
      setMessage(`${rule.text} added to the hub and pushed to every instance.`)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function refresh() {
    setBusy(true)
    try {
      await api.refreshQueryLog()
      await load()
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Query log"
        description="Every instance's DNS queries in one stream. Allowing a domain here writes one rule that reaches all instances, so a failover cannot undo it."
        actions={
          <>
            <span style={{ alignSelf: 'center', color: 'var(--text-dim)', fontSize: 13 }}>
              <span className={`live-dot${connected && live ? ' on' : ''}`} />
              {connected ? (live ? 'live' : 'paused') : 'disconnected'}
            </span>
            <button onClick={() => setLive(!live)}>{live ? 'Pause' : 'Resume'}</button>
            <button onClick={refresh} disabled={busy}>
              Poll now
            </button>
          </>
        }
      />

      {error ? <Banner kind="error">{error}</Banner> : null}
      {message ? <Banner kind="ok">{message}</Banner> : null}

      <Card>
        <div className="row" style={{ marginBottom: 14 }}>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="log-search">Search</label>
            <input
              id="log-search"
              value={search}
              placeholder="domain or client"
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <div className="field fixed" style={{ marginBottom: 0, width: 200 }}>
            <label htmlFor="log-instance">Instance</label>
            <select
              id="log-instance"
              value={instance}
              onChange={(event) => setInstance(event.target.value)}
            >
              <option value="">All instances</option>
              {(instances.data ?? []).map((item) => (
                <option key={item.id} value={item.name}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field fixed" style={{ marginBottom: 0 }}>
            <label className="checkbox" style={{ marginTop: 18 }}>
              <input
                type="checkbox"
                checked={blockedOnly}
                onChange={(event) => setBlockedOnly(event.target.checked)}
              />
              Blocked only
            </label>
          </div>
        </div>

        {rows.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Instance</th>
                  <th>Domain</th>
                  <th>Client</th>
                  <th>Result</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((entry, index) => (
                  <tr key={`${entry.instance}-${entry.time}-${entry.question}-${index}`}>
                    <td>{formatTime(entry.time)}</td>
                    <td>{entry.instance}</td>
                    <td className="mono">{entry.question}</td>
                    <td className="mono">{entry.client}</td>
                    <td>
                      <Badge tone={entry.blocked ? 'blocked' : 'online'}>
                        {entry.blocked ? 'blocked' : 'allowed'}
                      </Badge>
                      {entry.rule ? (
                        <div className="mono" style={{ color: 'var(--text-dim)', marginTop: 4 }}>
                          {entry.rule}
                        </div>
                      ) : null}
                    </td>
                    <td className="right">
                      {entry.blocked ? (
                        <button
                          className="small"
                          onClick={() => act(entry, 'allow')}
                          disabled={busy || !entry.question}
                        >
                          Allow everywhere
                        </button>
                      ) : (
                        <button
                          className="small"
                          onClick={() => act(entry, 'block')}
                          disabled={busy || !entry.question}
                        >
                          Block everywhere
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>
            Nothing buffered yet. The hub polls each instance every few seconds — add an instance
            and give it a moment.
          </Empty>
        )}
      </Card>
    </>
  )
}
