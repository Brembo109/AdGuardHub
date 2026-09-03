/**
 * The third state, and why it stopped being a dead end.
 *
 * "update unknown" with the reason in a `title` attribute is unreadable on a
 * phone — there is no hover — so a node saying, correctly, that its own updater
 * is switched off looked like a fault nobody could investigate.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Instance } from '../api/types'
import { I18nProvider } from '../i18n/provider'
import { NodeUpdate } from './NodeUpdate'

function node(overrides: Partial<Instance> = {}): Instance {
  return {
    id: 1,
    name: 'Secondary - Unraid',
    base_url: 'http://10.10.10.252',
    adapter: 'adguard',
    username: 'admin',
    has_password: true,
    verify_tls: true,
    enabled: true,
    maintenance: false,
    status: 'online',
    version: 'v0.107.79',
    update_version: '',
    update_url: '',
    update_error: '',
    last_error: '',
    last_seen_at: null,
    last_synced_at: null,
    created_at: '2026-09-03T08:00:00Z',
    ...overrides,
  } as Instance
}

const show = (instance: Instance) =>
  render(
    <I18nProvider>
      <NodeUpdate instance={instance} />
    </I18nProvider>,
  )

describe('NodeUpdate', () => {
  it('says why the answer is unknown, in the page rather than in a tooltip', () => {
    show(node({ update_error: 'this node has its own update check switched off' }))
    expect(screen.getByText(/update check switched off/)).toBeTruthy()
  })

  it('a node that is current renders nothing', () => {
    const { container } = show(node())
    expect(container.textContent).toBe('')
  })

  it('an offer still reads as an offer, not as a reason', () => {
    show(node({ update_version: 'v0.107.80' }))
    expect(screen.getByText(/v0\.107\.80/)).toBeTruthy()
  })

  it('an offer with an announcement links to it', () => {
    show(node({ update_version: 'v0.107.80', update_url: 'https://example.test/rel' }))
    expect(screen.getByRole('link').getAttribute('href')).toBe('https://example.test/rel')
  })
})
