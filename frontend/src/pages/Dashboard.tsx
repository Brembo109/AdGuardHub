import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { DriftEvent, Instance, PushJob, ReconcileReport, Traffic } from '../api/types'
import { Badge, Banner, Card, Empty, PageHeader } from '../components/ui'
import { BlockRateRing, RankList, SeriesChart } from '../components/charts'
import { formatCount, formatTime } from '../format'
import { errorMessage, useResource } from '../hooks/useApi'

/** How often the traffic numbers are re-read. The backend holds them for ~10s. */
const TRAFFIC_POLL_MS = 15_000

export default function Dashboard() {
  const stats = useResource(() => api.dashboard())
  const traffic = useResource<Traffic>(() => api.traffic())
  const instances = useResource<Instance[]>(() => api.instances())
  const jobs = useResource<PushJob[]>(() => api.jobs(true))
  const drift = useResource<DriftEvent[]>(() => api.drift(25))
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const reloadTraffic = traffic.reload
  useEffect(() => {
    const timer = setInterval(() => void reloadTraffic(), TRAFFIC_POLL_MS)
    return () => clearInterval(timer)
  }, [reloadTraffic])

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
      await Promise.all([stats.reload(), jobs.reload(), drift.reload(), instances.reload()])
    }
  }

  const forceSync = () =>
    run(async () => {
      const result = await api.sync()
      const failed = Object.keys(result.failed)
      return failed.length
        ? `Pushed to ${result.instances} instance(s); ${failed.join(', ')} failed and were queued for retry.`
        : `Pushed the full configuration to ${result.instances} instance(s).`
    })

  const reconcileNow = () =>
    run(async () => {
      const reports: ReconcileReport[] = await api.reconcile(true)
      // Report what was *found*, not just what was corrected: a difference that could
      // not be pushed away still belongs in the message, or the drift log below it
      // contradicts what this line says.
      const withDrift = reports.filter((report) => report.differences.length > 0)
      const corrected = withDrift.filter((report) => report.corrected)
      const failed = withDrift.filter((report) => report.checked && !report.corrected)
      const unreachable = reports.filter((report) => !report.checked)

      if (!withDrift.length && !unreachable.length) {
        return 'No drift found — every instance matches.'
      }

      const names = (list: ReconcileReport[]) => list.map((item) => item.instance_name).join(', ')
      const parts: string[] = []
      if (corrected.length) parts.push(`corrected ${names(corrected)}`)
      if (failed.length) {
        const detail = failed[0].error ? ` (${failed[0].error})` : ''
        parts.push(`found drift on ${names(failed)} that could not be applied${detail}`)
      }
      if (unreachable.length) parts.push(`could not reach ${names(unreachable)}`)
      return `Reconciliation: ${parts.join('; ')}.`
    })

  const retryQueue = () =>
    run(async () => {
      const result = await api.retryJobs()
      return result.recovered
        ? `Retried the queue — ${result.recovered} instance(s) are back in sync.`
        : 'Nothing in the retry queue could be applied yet.'
    })

  const value = stats.data
  const live = traffic.data
  const silent = live ? live.instances_total - live.instances_reporting : 0

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="AdGuardHub is the single source of truth. Every change here is pushed to all instances immediately; reconciliation catches anything that drifts."
        actions={
          <>
            <button onClick={forceSync} disabled={busy}>
              Push everything now
            </button>
            <button onClick={reconcileNow} disabled={busy}>
              Reconcile
            </button>
          </>
        }
      />

      {error ? <Banner kind="error">{error}</Banner> : null}
      {message ? <Banner kind="ok">{message}</Banner> : null}
      {stats.error ? <Banner kind="error">{stats.error}</Banner> : null}

      {value && value.instances_total === 0 ? (
        <Banner kind="warn">
          No instances yet. <Link to="/instances">Add your AdGuard Home instances</Link>, then import
          one of them as the master to seed the hub.
        </Banner>
      ) : null}

      {live && live.instances_total > 0 ? (
        <Card>
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              gap: 16,
              flexWrap: 'wrap',
              marginBottom: 18,
            }}
          >
            <div>
              <h2>Traffic across all nodes</h2>
              <p className="hint" style={{ margin: '3px 0 0' }}>
                Summed from every instance that answered.
              </p>
            </div>
            <Badge tone={silent ? 'pending' : 'applied'}>
              {live.instances_reporting} of {live.instances_total} nodes reporting
            </Badge>
          </div>

          {/* A total short by one node looks like a quiet day, so never let it pass silently. */}
          {silent ? (
            <Banner kind="warn">
              {silent} node{silent > 1 ? 's are' : ' is'} not reporting, so these numbers are lower
              than what your network actually did.
            </Banner>
          ) : null}

          <div className="grid" style={{ marginBottom: 22 }}>
            <div className="stat">
              <div className="value">{formatCount(live.queries)}</div>
              <div className="label">DNS queries</div>
            </div>
            <div className="stat">
              <div className="value" style={{ color: 'var(--series-b-ink)' }}>
                {formatCount(live.blocked)}
              </div>
              <div className="label">Blocked by filters</div>
            </div>
            <div className="stat">
              <div className="value">{formatCount(live.replaced_safebrowsing)}</div>
              <div className="label">Blocked by safe browsing</div>
            </div>
            <div className="stat">
              <div className="value">{live.avg_processing_time.toFixed(live.avg_processing_time < 1 ? 3 : 1)} ms</div>
              <div className="label">Average response time</div>
            </div>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'minmax(0, 1fr) 240px',
              gap: 30,
              alignItems: 'center',
            }}
            className="traffic-row"
          >
            <div>
              <div className="legend">
                <span>
                  <i style={{ background: 'var(--series-a)' }} />
                  DNS queries
                </span>
                <span>
                  <i style={{ background: 'var(--series-b)' }} />
                  Blocked
                </span>
              </div>
              <SeriesChart
                queries={live.series_queries}
                blocked={live.series_blocked}
                unit={live.time_units}
              />
            </div>
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 12,
              }}
            >
              <BlockRateRing rate={live.block_rate} />
              <p
                style={{
                  margin: 0,
                  fontSize: 12.5,
                  color: 'var(--dim)',
                  textAlign: 'center',
                  maxWidth: '30ch',
                }}
              >
                {formatCount(live.blocked)} of {formatCount(live.queries)} queries never left the
                network.
              </p>
            </div>
          </div>
        </Card>
      ) : null}

      {live && live.instances_reporting > 0 ? (
        <div className="cards-3" style={{ marginBottom: 16 }}>
          <Card title="Top queried domains">
            <RankList entries={live.top_queried} tone="a" />
          </Card>
          <Card title="Top blocked domains">
            <RankList entries={live.top_blocked} tone="b" />
          </Card>
          <Card title="Top clients">
            <RankList entries={live.top_clients} tone="a" />
          </Card>
        </div>
      ) : null}

      <div className="split">
        <Card>
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              gap: 16,
              marginBottom: 12,
              flexWrap: 'wrap',
            }}
          >
            <div>
              <h2>Nodes</h2>
              <p className="hint" style={{ margin: '3px 0 0' }}>
                Last successful push{' '}
                {value?.last_sync_at ? formatTime(value.last_sync_at) : 'never'}.
              </p>
            </div>
            <button className="small" onClick={retryQueue} disabled={busy}>
              Retry queue
            </button>
          </div>

          {instances.data?.length ? (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {instances.data.map((instance) => (
                <div
                  key={instance.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 14,
                    padding: '11px 2px',
                    borderBottom: '1px solid var(--line)',
                    flexWrap: 'wrap',
                  }}
                >
                  <span
                    className={`node-dot${
                      instance.status === 'unreachable'
                        ? ' down'
                        : instance.status === 'disabled'
                          ? ' off'
                          : ''
                    }`}
                    style={{ width: 8, height: 8 }}
                  />
                  <span style={{ fontWeight: 600, minWidth: 130 }}>{instance.name}</span>
                  <span className="mono" style={{ color: 'var(--dim)', minWidth: 170 }}>
                    {instance.base_url}
                  </span>
                  <Badge tone={instance.status}>{instance.status}</Badge>
                  <span style={{ marginLeft: 'auto', color: 'var(--dim)', fontSize: 13 }}>
                    {formatTime(instance.last_synced_at)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <Empty>No instances configured yet.</Empty>
          )}
        </Card>

        <Card title="Hub">
          {value ? (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
                gap: '16px 12px',
              }}
            >
              <Figure value={value.rules_total} label="Rules" />
              <Figure value={value.managed_sections} label="Replicated settings" to="/config" />
              <Figure value={value.filter_lists_enabled} label="Active subscriptions" />
              <Figure
                value={value.pending_jobs + value.failed_jobs}
                label="Queued pushes"
                alert={value.pending_jobs + value.failed_jobs > 0}
              />
              <Figure value={value.versions_total} label="Config versions" to="/history" />
              <Figure value={value.recent_drift} label="Drift events" />
            </div>
          ) : (
            <Empty>Loading…</Empty>
          )}
        </Card>
      </div>

      {jobs.data && jobs.data.length ? (
        <Card
          title="Retry queue"
          hint="A push that could not be delivered waits here and is retried automatically until it lands."
        >
          <div className="table-wrap">
            <table className="stack-on-phone">
              <thead>
                <tr>
                  <th>Instance</th>
                  <th>Payload</th>
                  <th>Status</th>
                  <th>Attempts</th>
                  <th>Last error</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {jobs.data.map((job) => (
                  <tr key={job.id}>
                    <td data-label="Instance">{job.instance_name}</td>
                    <td data-label="Payload">{job.payload_kind}</td>
                    <td data-label="Status">
                      <Badge tone={job.status}>{job.status}</Badge>
                    </td>
                    <td data-label="Attempts">{job.attempts}</td>
                    <td data-label="Last error" className="mono">
                      {job.last_error || '—'}
                    </td>
                    <td data-label="Updated">{formatTime(job.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}

      <Card
        title="Drift log"
        hint="Differences found by reconciliation. Corrections are applied automatically and never happen silently."
      >
        {drift.data && drift.data.length ? (
          <div className="table-wrap">
            <table className="stack-on-phone">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Instance</th>
                  <th>Payload</th>
                  <th>Summary</th>
                  <th>Fixed</th>
                </tr>
              </thead>
              <tbody>
                {drift.data.map((event) => (
                  <tr key={event.id}>
                    <td data-label="When">{formatTime(event.created_at)}</td>
                    <td data-label="Instance">{event.instance_name}</td>
                    <td data-label="Payload">{event.payload_kind}</td>
                    <td data-label="Summary">
                      {event.summary}
                      {event.details && event.details !== '{}' ? (
                        <details className="details">
                          <summary>details</summary>
                          <pre>{prettyJson(event.details)}</pre>
                        </details>
                      ) : null}
                    </td>
                    <td data-label="Fixed">
                      <Badge tone={event.corrected ? 'applied' : 'pending'}>
                        {event.corrected ? 'corrected' : 'detected'}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>No drift recorded yet.</Empty>
        )}
      </Card>
    </>
  )
}

function Figure({
  value,
  label,
  to,
  alert = false,
}: {
  value: number | string
  label: string
  to?: string
  alert?: boolean
}) {
  const body = (
    <div
      style={{
        fontSize: 22,
        fontWeight: 680,
        lineHeight: 1.1,
        fontVariantNumeric: 'tabular-nums',
        color: alert ? 'var(--danger-ink)' : undefined,
      }}
    >
      {value}
    </div>
  )
  return (
    <div>
      {to ? <Link to={to}>{body}</Link> : body}
      <div style={{ color: 'var(--dim)', fontSize: 12, marginTop: 5 }}>{label}</div>
    </div>
  )
}

function prettyJson(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw
  }
}
