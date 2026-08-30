import { useState } from 'react'
import { api } from '../api/client'
import type { InstanceDraft } from './instanceDraft'
import { errorMessage } from '../hooks/useApi'
import { Banner } from './ui'

/**
 * Add/edit form with an inline connection check, so credentials are verified
 * against the real instance before anything is saved.
 */
export function InstanceForm({
  draft,
  onChange,
  onSubmit,
  onCancel,
  submitLabel,
  busy = false,
  existingId,
  requireName = true,
}: {
  draft: InstanceDraft
  onChange: (draft: InstanceDraft) => void
  onSubmit: () => void | Promise<void>
  onCancel?: () => void
  submitLabel: string
  busy?: boolean
  existingId?: number
  requireName?: boolean
}) {
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null)

  async function test() {
    setTesting(true)
    setResult(null)
    try {
      const outcome = await api.testConnection({
        base_url: draft.base_url,
        username: draft.username,
        password: draft.password,
        verify_tls: draft.verify_tls,
        instance_id: existingId,
      })
      setResult(
        outcome.ok
          ? { ok: true, message: `Connected — AdGuard Home ${outcome.version}.` }
          : { ok: false, message: outcome.error },
      )
    } catch (caught) {
      setResult({ ok: false, message: errorMessage(caught) })
    } finally {
      setTesting(false)
    }
  }

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    void onSubmit()
  }

  return (
    <form onSubmit={submit}>
      <div className="row">
        {requireName ? (
          <div className="field">
            <label htmlFor="if-name">Name</label>
            <input
              id="if-name"
              value={draft.name}
              placeholder="adguard-primary"
              onChange={(event) => onChange({ ...draft, name: event.target.value })}
              required
            />
          </div>
        ) : null}
        <div className="field">
          <label htmlFor="if-url">Base URL</label>
          <input
            id="if-url"
            value={draft.base_url}
            placeholder="http://192.168.1.2:3000"
            onChange={(event) => onChange({ ...draft, base_url: event.target.value })}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="if-user">Admin username</label>
          <input
            id="if-user"
            value={draft.username}
            autoComplete="off"
            onChange={(event) => onChange({ ...draft, username: event.target.value })}
          />
        </div>
        <div className="field">
          <label htmlFor="if-pass">
            Admin password{existingId ? ' (blank keeps the current one)' : ''}
          </label>
          <input
            id="if-pass"
            type="password"
            value={draft.password}
            autoComplete="new-password"
            onChange={(event) => onChange({ ...draft, password: event.target.value })}
          />
        </div>
      </div>

      <label className="checkbox">
        <input
          type="checkbox"
          checked={draft.verify_tls}
          onChange={(event) => onChange({ ...draft, verify_tls: event.target.checked })}
        />
        Verify the TLS certificate (turn off for a self-signed HTTPS instance)
      </label>

      {result ? (
        <Banner kind={result.ok ? 'ok' : 'error'}>{result.message}</Banner>
      ) : null}

      <div className="actions">
        <button type="button" onClick={test} disabled={testing || busy || !draft.base_url}>
          {testing ? 'Testing…' : 'Test connection'}
        </button>
        <button className="primary" type="submit" disabled={busy}>
          {submitLabel}
        </button>
        {onCancel ? (
          <button type="button" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
        ) : null}
      </div>
    </form>
  )
}
