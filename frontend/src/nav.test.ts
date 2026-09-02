/**
 * The second level of navigation, as data.
 *
 * Two things here are easy to break without noticing, because neither shows up
 * as an error: a top-level entry that goes dark while you are still inside it,
 * and a tab list that points at a route nobody serves.
 */

import { describe, expect, it } from 'vitest'
import { FILTER_TABS, INSTANCE_TABS, SETTINGS_TABS, covers } from './nav'

const FILTER = { covers: ['/rules', '/subscriptions'] }

describe('covers', () => {
  it('keeps the group lit on its own landing page', () => {
    expect(covers(FILTER, '/rules')).toBe(true)
  })

  it('keeps the group lit on its second tab', () => {
    // The whole reason this helper exists: a NavLink to /rules knows nothing
    // about /subscriptions, so "Filter" would go dark inside its own section.
    expect(covers(FILTER, '/subscriptions')).toBe(true)
  })

  it('follows a covered path into its children', () => {
    expect(covers({ covers: ['/settings'] }, '/settings/backup')).toBe(true)
  })

  it('does not claim a path that merely starts with the same letters', () => {
    // '/rules-archive' is not inside '/rules'; a prefix match without the
    // separator would light the wrong entry.
    expect(covers(FILTER, '/rules-archive')).toBe(false)
  })

  it('claims nothing for an entry that groups nothing', () => {
    expect(covers({}, '/rules')).toBe(false)
  })
})

describe('tab lists', () => {
  it('give every tab a distinct route', () => {
    for (const tabs of [FILTER_TABS, INSTANCE_TABS, SETTINGS_TABS]) {
      const routes = tabs.map((tab) => tab.to)
      expect(new Set(routes).size).toBe(routes.length)
    }
  })

  it('start each group at the route its top-level entry points to', () => {
    // The first tab is where the bar sends you; if it were not a real tab, the
    // strip would show nothing active on arrival.
    expect(FILTER_TABS[0].to).toBe('/rules')
    expect(INSTANCE_TABS[0].to).toBe('/instances')
    expect(SETTINGS_TABS[0].to).toBe('/settings')
  })
})
