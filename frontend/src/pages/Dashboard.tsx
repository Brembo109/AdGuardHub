import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { DriftEvent, PushJob, ReconcileReport } from '../api/types'
import { Badge, Banner, Card, Empty, PageHeader, Stat } from '../components/ui'
import { formatTime } from '../format'
import { errorMessage, useResource } from '../hooks/useApi'

export default function Dashboard() {
  const stats = useResource(() => api.dashboard())
  const jobs = useResource<PushJob[]>(() => api.jobs(true))
  const drift = useResource<DriftEvent[]>(() => api.drift(25))
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
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
      await Promise.all([stats.reload(), jobs.reload(), drift.reload()])
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
      const corrected = reports.filter((report) => report.corrected)
      const unreachable = reports.filter((report) => !report.checked)
      if (!corrected.length && !unreachable.length) return 'No drift found — every instance matches.'
      const parts: string[] = []
      if (corrected.length) parts.push(`corrected ${corrected.map((r) => r.instance_name).join(', ')}`)
      if (unreachable.length)
        parts.push(`could not reach ${unreachable.map((r) => r.instance_name).join(', ')}`)
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

      {value ? (
        <Card>
          <div className="sync-line">
            <div>
              <div className="hint" style={{ margin: 0 }}>
                Last successful push
              </div>
              <div style={{ fontSize: 17, fontWeight: 600 }}>
                {value.last_sync_at ? formatTime(value.last_sync_at) : 'never'}
              </div>
            </div>
            <div>
              <div className="hint" style={{ margin: 0 }}>
                Instances carrying it
              </div>
              <div style={{ fontSize: 17, fontWeight: 600 }}>
                {value.instances_synced}/{value.instances_total}
              </div>
            </div>
            <div>
              <div className="hint" style={{ margin: 0 }}>
                Config versions
              </div>
              <div style={{ fontSize: 17, fontWeight: 600 }}>
                <Link to="/history">{value.versions_total}</Link>
              </div>
            </div>
          </div>
        </Card>
      ) : null}

      {error ? <Banner kind="error">{error}</Banner> : null}
      {message ? <Banner kind="ok">{message}</Banner> : null}
      {stats.error ? <Banner kind="error">{stats.error}</Banner> : null}

      {value ? (
        <div className="grid" style={{ marginBottom: 16 }}>
          <Stat value={`${value.instances_online}/${value.instances_total}`} label="Instances online" />
          <Stat
            value={value.instances_unreachable}
            label="Unreachable"
            alert={value.instances_unreachable > 0}
          />
          <Stat value={value.rules_total} label="Rules" />
          <Stat value={value.managed_sections} label="Replicated settings" />
          <Stat value={value.rules_allow} label="Allow rules" />
          <Stat value={value.filter_lists_enabled} label="Active subscriptions" />
          <Stat
            value={value.pending_jobs + value.failed_jobs}
            label="Queued pushes"
            alert={value.pending_jobs + value.failed_jobs > 0}
          />
          <Stat value={value.recent_drift} label="Drift events" />
          <Stat value={value.querylog_buffered} label="Log entries buffered" />
        </div>
      ) : null}

      {value && value.instances_total === 0 ? (
        <Banner kind="warn">
          No instances yet. <Link to="/instances">Add your AdGuard Home instances</Link>, then import
          one of them as the master to seed the hub.
        </Banner>
      ) : null}

      <Card
        title="Retry queue"
        hint="A push that could not be delivered waits here and is retried automatically until it lands."
      >
        <div className="actions" style={{ marginBottom: 12 }}>
          <button className="small" onClick={retryQueue} disabled={busy}>
            Retry now
          </button>
        </div>
        {jobs.data && jobs.data.length ? (
          <div className="table-wrap">
            <table>
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
                    <td>{job.instance_name}</td>
                    <td>{job.payload_kind}</td>
                    <td>
                      <Badge tone={job.status}>{job.status}</Badge>
                    </td>
                    <td>{job.attempts}</td>
                    <td className="mono">{job.last_error || '—'}</td>
                    <td>{formatTime(job.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>Nothing queued — every instance has the current configuration.</Empty>
        )}
      </Card>

      <Card
        title="Drift log"
        hint="Differences found by reconciliation. Corrections are applied automatically and never happen silently."
      >
        {drift.data && drift.data.length ? (
          <div className="table-wrap">
            <table>
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
                    <td>{formatTime(event.created_at)}</td>
                    <td>{event.instance_name}</td>
                    <td>{event.payload_kind}</td>
                    <td>
                      {event.summary}
                      {event.details && event.details !== '{}' ? (
                        <details className="details">
                          <summary>details</summary>
                          <pre>{prettyJson(event.details)}</pre>
                        </details>
                      ) : null}
                    </td>
                    <td>
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

function prettyJson(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw
  }
}
