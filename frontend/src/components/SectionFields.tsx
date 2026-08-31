import type { ConfigField } from '../api/types'
import { useT } from '../i18n'
import { Switch } from './ui'

type Doc = Record<string, unknown>

/**
 * Renders a section's curated fields. The field list comes from the backend, so the
 * form and the sync layer cannot describe a setting differently.
 *
 * Anything without a curated field stays reachable through the raw document view —
 * a setting is never unreachable just because it has no form here.
 */
export function SectionFields({
  fields,
  data,
  onChange,
}: {
  fields: ConfigField[]
  data: Doc
  onChange: (data: Doc) => void
}) {
  const t = useT()
  const set = (key: string, value: unknown) => onChange({ ...data, [key]: value })

  const booleans = fields.filter((field) => field.type === 'bool')
  const others = fields.filter((field) => field.type !== 'bool')

  return (
    <>
      {booleans.length ? (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
            gap: '12px 26px',
          }}
        >
          {booleans.map((field) => (
            <div key={field.key}>
              <Switch
                checked={Boolean(data[field.key])}
                onChange={(value) => set(field.key, value)}
                label={t(field.label)}
                title={t(field.help)}
              />
              {/* Help belongs on the page, not only in a tooltip nobody hovers. */}
              {field.help ? (
                <div className="hint" style={{ margin: '4px 0 0 45px' }}>
                  {t(field.help)}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {/* A grid, not a flex row: flex-end alignment left labels and help text
          sitting at different heights across a group, which reads as sloppy. */}
      <div className="fields-grid" style={{ marginTop: booleans.length ? 16 : 0 }}>
        {others.map((field) => (
          <Field key={field.key} field={field} value={data[field.key]} onChange={set} />
        ))}
      </div>
    </>
  )
}

function Field({
  field,
  value,
  onChange,
}: {
  field: ConfigField
  value: unknown
  onChange: (key: string, value: unknown) => void
}) {
  const t = useT()
  const label = (
    <label htmlFor={`f-${field.key}`}>
      {t(field.label)}
      {field.unit ? ` (${t(field.unit)})` : ''}
    </label>
  )
  const help = field.help ? (
    <div className="hint" style={{ margin: '4px 0 0' }}>
      {t(field.help)}
    </div>
  ) : null

  if (field.type === 'lines') {
    const lines = Array.isArray(value) ? (value as unknown[]).map(String).join('\n') : ''
    return (
      <div className="field wide">
        {label}
        <textarea
          id={`f-${field.key}`}
          value={lines}
          spellCheck={false}
          style={{ minHeight: 110 }}
          onChange={(event) =>
            onChange(
              field.key,
              event.target.value
                .split('\n')
                .map((line) => line.trim())
                .filter(Boolean),
            )
          }
        />
        {help}
      </div>
    )
  }

  if (field.type === 'select') {
    // Options are strings; keep the stored type (AdGuard uses numbers for some).
    const current = value === undefined || value === null ? '' : String(value)
    return (
      <div className="field">
        {label}
        <select
          id={`f-${field.key}`}
          value={current}
          onChange={(event) => {
            const raw = event.target.value
            const asNumber = Number(raw)
            onChange(field.key, raw !== '' && !Number.isNaN(asNumber) ? asNumber : raw)
          }}
        >
          {field.options.map(([optionValue, optionLabel]) => (
            <option key={optionValue} value={optionValue}>
              {t(optionLabel)}
            </option>
          ))}
        </select>
        {help}
      </div>
    )
  }

  if (field.type === 'int') {
    return (
      <div className="field">
        {label}
        <input
          id={`f-${field.key}`}
          type="number"
          value={typeof value === 'number' ? value : ''}
          onChange={(event) => onChange(field.key, Number(event.target.value))}
        />
        {help}
      </div>
    )
  }

  if (field.type === 'pairs') {
    return <PairsField field={field} value={value} onChange={onChange} help={help} />
  }

  if (field.type === 'clients') {
    return <ClientsField field={field} value={value} onChange={onChange} />
  }

  return (
    <div className="field">
      {label}
      <input
        id={`f-${field.key}`}
        value={typeof value === 'string' ? value : ''}
        onChange={(event) => onChange(field.key, event.target.value)}
      />
      {help}
    </div>
  )
}

interface Rewrite {
  domain: string
  answer: string
}

function PairsField({
  field,
  value,
  onChange,
  help,
}: {
  field: ConfigField
  value: unknown
  onChange: (key: string, value: unknown) => void
  help: React.ReactNode
}) {
  const t = useT()
  const items: Rewrite[] = Array.isArray(value)
    ? (value as Rewrite[]).map((item) => ({
        domain: String(item?.domain ?? ''),
        answer: String(item?.answer ?? ''),
      }))
    : []

  const write = (next: Rewrite[]) => onChange(field.key, next)

  return (
    <div className="field full">
      <label>{t(field.label)}</label>
      {items.map((item, index) => (
        <div className="row" key={index} style={{ marginBottom: 6 }}>
          <input
            value={item.domain}
            placeholder={t('nas.lan')}
            onChange={(event) =>
              write(items.map((row, i) => (i === index ? { ...row, domain: event.target.value } : row)))
            }
          />
          <input
            value={item.answer}
            placeholder="192.168.1.9"
            onChange={(event) =>
              write(items.map((row, i) => (i === index ? { ...row, answer: event.target.value } : row)))
            }
          />
          <button
            type="button"
            className="small danger fixed"
            onClick={() => write(items.filter((_, i) => i !== index))}
          >
            {t('Remove')}
          </button>
        </div>
      ))}
      <button
        type="button"
        className="small"
        onClick={() => write([...items, { domain: '', answer: '' }])}
      >
        {t('Add rewrite')}
      </button>
      {help}
    </div>
  )
}

interface ClientEntry {
  name: string
  ids: string[]
  use_global_settings?: boolean
  filtering_enabled?: boolean
  [key: string]: unknown
}

function ClientsField({
  field,
  value,
  onChange,
}: {
  field: ConfigField
  value: unknown
  onChange: (key: string, value: unknown) => void
}) {
  const t = useT()
  const items: ClientEntry[] = Array.isArray(value) ? (value as ClientEntry[]) : []
  const write = (next: ClientEntry[]) => onChange(field.key, next)

  return (
    <div className="field full">
      <label>{t(field.label)}</label>
      <p className="hint" style={{ marginBottom: 8 }}>
        {t(
          'Name and identifiers are edited here; any other per-client setting AdGuard stores is kept as imported and visible in the raw document.',
        )}
      </p>
      {items.map((client, index) => (
        <div className="row" key={index} style={{ marginBottom: 6 }}>
          <input
            value={client.name ?? ''}
            placeholder={t('Living room TV')}
            onChange={(event) =>
              write(
                items.map((row, i) => (i === index ? { ...row, name: event.target.value } : row)),
              )
            }
          />
          <input
            value={(client.ids ?? []).join(', ')}
            placeholder="192.168.1.5, aa:bb:cc:dd:ee:ff"
            onChange={(event) =>
              write(
                items.map((row, i) =>
                  i === index
                    ? {
                        ...row,
                        ids: event.target.value
                          .split(',')
                          .map((id) => id.trim())
                          .filter(Boolean),
                      }
                    : row,
                ),
              )
            }
          />
          <button
            type="button"
            className="small danger fixed"
            onClick={() => write(items.filter((_, i) => i !== index))}
          >
            {t('Remove')}
          </button>
        </div>
      ))}
      <button
        type="button"
        className="small"
        onClick={() =>
          write([...items, { name: '', ids: [], use_global_settings: true } as ClientEntry])
        }
      >
        {t('Add client')}
      </button>
    </div>
  )
}
