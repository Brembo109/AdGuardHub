import type { ReactNode } from 'react'

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="actions">{actions}</div> : null}
    </header>
  )
}

export function Card({
  title,
  hint,
  children,
}: {
  title?: string
  hint?: string
  children: ReactNode
}) {
  return (
    <section className="card">
      {title ? <h2>{title}</h2> : null}
      {hint ? <p className="hint">{hint}</p> : null}
      {children}
    </section>
  )
}

export function Banner({ kind, children }: { kind: 'error' | 'ok' | 'warn'; children: ReactNode }) {
  return <div className={`banner ${kind}`}>{children}</div>
}

export function Badge({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>
}

/**
 * For settings the hub turns on or off for every node, where a state reads better
 * than a form field. Plain checkboxes stay for filters and one-off form options.
 */
export function Switch({
  checked,
  onChange,
  label,
  title,
}: {
  checked: boolean
  onChange: (value: boolean) => void
  label: string
  title?: string
}) {
  return (
    <label className="switch" title={title}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="track" />
      {label}
    </label>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>
}

export function Stat({
  value,
  label,
  alert = false,
}: {
  value: number | string
  label: string
  alert?: boolean
}) {
  return (
    <div className={`stat${alert ? ' alert' : ''}`}>
      <div className="value">{value}</div>
      <div className="label">{label}</div>
    </div>
  )
}
