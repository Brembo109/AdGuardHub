/**
 * Being told about a release, and being able to stop being told.
 *
 * The bar is the interruption and the dot beside *Settings* is the standing
 * fact, so what matters here is that dismissing silences this one only — and
 * silences it for the release it was dismissed on, not for every release after.
 */

import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import type { UpdateStatus } from '../api/types'
import { I18nProvider } from '../i18n/provider'
import { UpdateNotice } from './UpdateNotice'

function status(overrides: Partial<UpdateStatus> = {}): UpdateStatus {
  return {
    current: 'v0.5.0',
    latest: 'v0.5.1',
    update_available: true,
    release_url: 'https://example.test/releases/v0.5.1',
    published_at: '2026-09-02T22:17:09Z',
    install_method: 'native',
    self_update: true,
    checked_at: 0,
    error: '',
    enabled: true,
    ...overrides,
  }
}

function show(value: UpdateStatus | null) {
  return render(
    <I18nProvider>
      <MemoryRouter>
        <UpdateNotice status={value} />
      </MemoryRouter>
    </I18nProvider>,
  )
}

describe('UpdateNotice', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('says which release is waiting', () => {
    show(status())
    expect(screen.getByText(/v0\.5\.1/)).toBeTruthy()
  })

  it('says nothing while the status is still loading', () => {
    // The shell renders it on every page, so a hub that cannot reach GitHub —
    // or has not answered yet — must not flash a bar about nothing.
    const { container } = show(null)
    expect(container.textContent).toBe('')
  })

  it('says nothing when the hub is current', () => {
    const { container } = show(status({ update_available: false }))
    expect(container.textContent).toBe('')
  })

  it('dismissing hides it and is remembered', () => {
    const { container } = show(status())
    fireEvent.click(screen.getByRole('button'))
    expect(container.textContent).toBe('')
    expect(localStorage.getItem('adguardhub.update.dismissed')).toBe('v0.5.1')
  })

  it('the next release is announced even though the last one was dismissed', () => {
    localStorage.setItem('adguardhub.update.dismissed', 'v0.5.1')
    show(status({ latest: 'v0.6.0' }))
    expect(screen.getByText(/v0\.6\.0/)).toBeTruthy()
  })

  it('stays dismissed for the release it was dismissed on', () => {
    localStorage.setItem('adguardhub.update.dismissed', 'v0.5.1')
    const { container } = show(status())
    expect(container.textContent).toBe('')
  })
})
