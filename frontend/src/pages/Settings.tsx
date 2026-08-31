import { useState } from 'react'
import { api } from '../api/client'
import type { Notifier, NotifierType } from '../api/types'
import { useAuth } from '../auth'
import { Banner, Card, Empty, PageHeader } from '../components/ui'
import { errorMessage, useResource } from '../hooks/useApi'

const EVENT_LABELS: Record<string, string> = {
  'reconcile.fixed': 'Reconciliation applied a fix',
  'instance.unreachable': 'An instance went unreachable',
  'push.failed': 'A push failed and was queued',
}

const URL_HINTS: Record<NotifierType, string> = {
  homeassistant: 'http://homeassistant.local:8123/api/webhook/<webhook-id>',
  discord: 'https://discord.com/api/webhooks/<id>/<token>',
  gotify: 'https://gotify.example.com/message',
}

export default function Settings() {
  const notifiers = useResource<Notifier[]>(() => api.notifiers())
  const meta = useResource(() => api.notifierMeta())

  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  async function run(action: () => Promise<string>, reload?: () => Promise<void>) {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      setMessage(await action())
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
      if (reload) await reload()
    }
  }

  return (
    <>
      <PageHeader
        title="Settings"
        description="Notification targets and your own credentials. The settings replicated to your instances live under Instance settings."
      />

      {error ? <Banner kind="error">{error}</Banner> : null}
      {message ? <Banner kind="ok">{message}</Banner> : null}

      <NotifierSection
        notifiers={notifiers.data ?? []}
        events={meta.data?.events ?? []}
        busy={busy}
        run={run}
        reload={notifiers.reload}
      />
      <PasswordSection busy={busy} run={run} />
    </>
  )
}

type Runner = (action: () => Promise<string>, reload?: () => Promise<void>) => Promise<void>

function NotifierSection({
  notifiers,
  events,
  busy,
  run,
  reload,
}: {
  notifiers: Notifier[]
  events: string[]
  busy: boolean
  run: Runner
  reload: () => Promise<void>
}) {
  const [form, setForm] = useState<{
    name: string
    type: NotifierType
    url: string
    token: string
    events: string[]
  }>({ name: '', type: 'homeassistant', url: '', token: '', events: [] })

  const submit = (submitEvent: React.FormEvent) => {
    submitEvent.preventDefault()
    void run(async () => {
      const created = await api.createNotifier(form)
      setForm({ name: '', type: 'homeassistant', url: '', token: '', events: [] })
      return `Added notifier ${created.name}.`
    }, reload)
  }

  const toggleEvent = (name: string) =>
    setForm({
      ...form,
      events: form.events.includes(name)
        ? form.events.filter((item) => item !== name)
        : [...form.events, name],
    })

  return (
    <Card
      title="Notifications"
      hint="Zero or more targets can be active at once. Leave every event unticked to receive all of them."
    >
      <form onSubmit={submit}>
        <div className="row">
          <div className="field">
            <label htmlFor="n-name">Name</label>
            <input
              id="n-name"
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              required
            />
          </div>
          <div className="field fixed" style={{ width: 170 }}>
            <label htmlFor="n-type">Type</label>
            <select
              id="n-type"
              value={form.type}
              onChange={(event) => setForm({ ...form, type: event.target.value as NotifierType })}
            >
              <option value="homeassistant">Home Assistant</option>
              <option value="discord">Discord</option>
              <option value="gotify">Gotify</option>
            </select>
          </div>
          <div className="field" style={{ flex: '2 1 320px' }}>
            <label htmlFor="n-url">Webhook URL</label>
            <input
              id="n-url"
              value={form.url}
              placeholder={URL_HINTS[form.type]}
              onChange={(event) => setForm({ ...form, url: event.target.value })}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="n-token">
              {form.type === 'gotify' ? 'Application token' : 'Bearer token (optional)'}
            </label>
            <input
              id="n-token"
              type="password"
              value={form.token}
              autoComplete="new-password"
              onChange={(event) => setForm({ ...form, token: event.target.value })}
            />
          </div>
        </div>

        <div style={{ margin: '4px 0 12px' }}>
          {events.map((name) => (
            <label className="checkbox" key={name}>
              <input
                type="checkbox"
                checked={form.events.includes(name)}
                onChange={() => toggleEvent(name)}
              />
              {EVENT_LABELS[name] ?? name}
            </label>
          ))}
        </div>

        <button className="primary" type="submit" disabled={busy}>
          Add notifier
        </button>
      </form>

      <div style={{ marginTop: 18 }}>
        {notifiers.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th>URL</th>
                  <th>Events</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {notifiers.map((target) => (
                  <tr key={target.id} style={{ opacity: target.enabled ? 1 : 0.55 }}>
                    <td>{target.name}</td>
                    <td>{target.type}</td>
                    <td className="mono">{target.url}</td>
                    <td>
                      {target.events.length
                        ? target.events.map((name) => EVENT_LABELS[name] ?? name).join(', ')
                        : 'all events'}
                      {target.last_error ? (
                        <div className="mono" style={{ color: 'var(--danger)', marginTop: 4 }}>
                          {target.last_error}
                        </div>
                      ) : null}
                    </td>
                    <td className="right">
                      <button
                        className="small"
                        disabled={busy}
                        onClick={() =>
                          void run(async () => {
                            const result = await api.testNotifier(target.id)
                            return result.error
                              ? `Test failed: ${result.error}`
                              : `Test notification sent to ${target.name}.`
                          }, reload)
                        }
                      >
                        Test
                      </button>{' '}
                      <button
                        className="small"
                        disabled={busy}
                        onClick={() =>
                          void run(async () => {
                            await api.updateNotifier(target.id, { enabled: !target.enabled })
                            return `${target.name} ${target.enabled ? 'disabled' : 'enabled'}.`
                          }, reload)
                        }
                      >
                        {target.enabled ? 'Disable' : 'Enable'}
                      </button>{' '}
                      <button
                        className="small danger"
                        disabled={busy}
                        onClick={() =>
                          void run(async () => {
                            await api.deleteNotifier(target.id)
                            return `Removed ${target.name}.`
                          }, reload)
                        }
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
          <Empty>No notification targets configured.</Empty>
        )}
      </div>
    </Card>
  )
}

function PasswordSection({ busy, run }: { busy: boolean; run: Runner }) {
  const { state, logout } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    void run(async () => {
      await api.changePassword(current, next)
      setCurrent('')
      setNext('')
      return 'Password changed.'
    })
  }

  return (
    <Card title="Account" hint={`Signed in as ${state?.username ?? 'unknown'}.`}>
      <form onSubmit={submit} className="row">
        <div className="field">
          <label htmlFor="cur">Current password</label>
          <input
            id="cur"
            type="password"
            value={current}
            autoComplete="current-password"
            onChange={(event) => setCurrent(event.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="new">New password</label>
          <input
            id="new"
            type="password"
            value={next}
            minLength={8}
            autoComplete="new-password"
            onChange={(event) => setNext(event.target.value)}
            required
          />
        </div>
        <div className="field fixed">
          <button className="primary" type="submit" disabled={busy}>
            Change password
          </button>
        </div>
        <div className="field fixed">
          <button type="button" onClick={() => void logout()}>
            Sign out
          </button>
        </div>
      </form>
    </Card>
  )
}
