/**
 * Narrowing the hub's own log.
 *
 * The buffer holds 500 lines and most of them are uvicorn reporting requests,
 * so "what did the sync engine do at 08:25" meant reading past a few hundred
 * access lines. These check the three ways of cutting that down, and — the
 * assertion that matters most — that nothing gets hidden by accident.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LogLine } from '../../api/types'
import { I18nProvider } from '../../i18n/provider'
import SettingsLog from './Log'
import { NO_FILTER, matches } from './logFilter'

const { logMock } = vi.hoisted(() => ({ logMock: vi.fn() }))

vi.mock('../../api/client', () => ({ api: { log: logMock } }))

function line(overrides: Partial<LogLine> & { seq: number }): LogLine {
  return {
    level: 'INFO',
    logger: 'app.services.sync',
    message: 'Pushed rules to Primary (12 rules)',
    at: '2026-09-03T08:25:00Z',
    ...overrides,
  }
}

const LINES: LogLine[] = [
  line({ seq: 1, logger: 'uvicorn.access', message: '10.0.0.5 - "GET /api/dashboard" 200' }),
  line({ seq: 2 }),
  line({
    seq: 3,
    level: 'WARNING',
    logger: 'app.services.sync',
    message: 'Push to Secondary failed (rules): timed out — queued for retry',
  }),
  line({
    seq: 4,
    level: 'ERROR',
    logger: 'app.services.reconcile',
    message: 'Reconciliation pass failed',
  }),
]

function show() {
  logMock.mockResolvedValue({ lines: LINES, cursor: 4, latest: 4, capacity: 500 })
  return render(
    <I18nProvider>
      <SettingsLog />
    </I18nProvider>,
  )
}

/** Every rendered log line, in order. */
function rendered(container: HTMLElement): string[] {
  return [...container.querySelectorAll('.log-line')].map((node) => node.textContent ?? '')
}

describe('matches', () => {
  it('shows a level it has never heard of rather than hiding it', () => {
    // A library logging at NOTICE, TRACE or its own custom level must not
    // disappear because this build does not rank it. The unrecognised line is
    // usually the one worth reading.
    const odd = line({ seq: 9, level: 'NOTICE' })
    expect(matches(odd, { ...NO_FILTER, floor: 40 })).toBe(true)
  })

  it('an empty filter matches everything', () => {
    expect(LINES.every((entry) => matches(entry, NO_FILTER))).toBe(true)
  })
})

describe('SettingsLog', () => {
  beforeEach(() => logMock.mockReset())

  it('shows every line until asked otherwise', async () => {
    const { container } = show()
    await waitFor(() => expect(rendered(container)).toHaveLength(4))
  })

  it('a level floor keeps what is at least that bad', async () => {
    const { container } = show()
    await waitFor(() => expect(rendered(container)).toHaveLength(4))

    fireEvent.change(screen.getByLabelText('Filter by level'), { target: { value: '30' } })

    const kept = rendered(container)
    expect(kept).toHaveLength(2)
    expect(kept[0]).toContain('queued for retry')
    expect(kept[1]).toContain('Reconciliation pass failed')
  })

  it('a source keeps that logger and drops the request noise', async () => {
    const { container } = show()
    await waitFor(() => expect(rendered(container)).toHaveLength(4))

    fireEvent.change(screen.getByLabelText('Filter by source'), {
      target: { value: 'app.services.sync' },
    })

    expect(rendered(container)).toHaveLength(2)
    expect(rendered(container).join()).not.toContain('GET /api/dashboard')
  })

  it('the source list drops the module prefix but keeps the logger as the value', async () => {
    show()
    const sources = await screen.findByLabelText('Filter by source')
    const labels = [...sources.querySelectorAll('option')].map((option) => option.textContent)
    expect(labels).toContain('services.sync')
    expect(labels).not.toContain('app.services.sync')
    const values = [...sources.querySelectorAll('option')].map((option) => option.value)
    expect(values).toContain('app.services.sync')
  })

  it('searching matches the line as it is displayed', async () => {
    const { container } = show()
    await waitFor(() => expect(rendered(container)).toHaveLength(4))

    fireEvent.change(screen.getByLabelText('Search the log'), { target: { value: 'SECONDARY' } })

    expect(rendered(container)).toHaveLength(1)
    expect(rendered(container)[0]).toContain('Push to Secondary failed')
  })

  it('says how much it is holding back, so a filter is never mistaken for a quiet hub', async () => {
    const { container } = show()
    await waitFor(() => expect(rendered(container)).toHaveLength(4))

    fireEvent.change(screen.getByLabelText('Filter by level'), { target: { value: '40' } })

    expect(container.textContent).toContain('1 of 4 lines')
  })

  it('an empty result says the filter did it, not that nothing was logged', async () => {
    const { container } = show()
    await waitFor(() => expect(rendered(container)).toHaveLength(4))

    fireEvent.change(screen.getByLabelText('Search the log'), { target: { value: 'nothing here' } })

    expect(rendered(container)).toHaveLength(0)
    expect(container.textContent).toContain('No line matches this filter.')
    expect(container.textContent).not.toContain('Nothing logged yet.')
  })

  it('Show all puts every line back', async () => {
    const { container } = show()
    await waitFor(() => expect(rendered(container)).toHaveLength(4))

    fireEvent.change(screen.getByLabelText('Filter by level'), { target: { value: '40' } })
    expect(rendered(container)).toHaveLength(1)

    fireEvent.click(screen.getByRole('button', { name: 'Show all' }))
    expect(rendered(container)).toHaveLength(4)
  })
})
