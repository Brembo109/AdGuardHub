/**
 * Dates and numbers, and the locale they follow.
 *
 * This file exists because of a real bug: the formatters called
 * `toLocaleString()` with no argument, which follows the *browser* rather than
 * the interface. A German operator on an en-US browser read `9/1/2026` under a
 * German heading — not a different format, a different date.
 *
 * The property to pin is therefore not "German uses dots". It is that the
 * language the user picked wins over the one their browser happens to be in,
 * *and* that English still defers to the browser, because `en` is written in
 * both date orders and an American should keep seeing American dates.
 */

import { afterEach, describe, expect, it } from 'vitest'
import { formatClock, formatCount, formatTime, setFormatLocale } from './format'

// A fixed instant, expressed so the assertions below cannot drift with the
// runner's timezone: local midday on a day whose parts differ in every locale.
const INSTANT = new Date(2026, 8, 1, 14, 38, 49).toISOString()

afterEach(() => {
  // Module-level state: one test must not decide the next one's locale.
  setFormatLocale('en')
})

describe('setFormatLocale', () => {
  it('formats dates for German once German is chosen', () => {
    setFormatLocale('de')
    const shown = formatTime(INSTANT)
    expect(shown).toContain('1.9.2026')
    expect(shown).not.toMatch(/\d{1,2}\/\d{1,2}\/\d{4}/)
  })

  it('groups thousands the German way too', () => {
    setFormatLocale('de')
    expect(formatCount(4085)).toBe('4.085')
  })

  it('leaves English on the browser locale rather than pinning a region', () => {
    // The test runner's locale is en-US, so this is the case that regressed
    // when an early draft pinned English to en-GB.
    setFormatLocale('en')
    expect(formatTime(INSTANT)).toMatch(/\d{1,2}\/\d{1,2}\/\d{4}/)
    expect(formatCount(4085)).toBe('4,085')
  })

  it('switches back when the language does', () => {
    setFormatLocale('de')
    setFormatLocale('en')
    expect(formatCount(4085)).toBe('4,085')
  })

  it('treats an unknown language as English rather than throwing', () => {
    setFormatLocale('fr')
    expect(() => formatCount(1000)).not.toThrow()
  })
})

describe('the empty and broken cases', () => {
  it.each([null, undefined, ''])('renders %p as a dash', (value) => {
    expect(formatTime(value)).toBe('—')
    expect(formatClock(value)).toBe('—')
  })

  it('hands back text it cannot parse instead of showing "Invalid Date"', () => {
    expect(formatTime('not a timestamp')).toBe('not a timestamp')
    expect(formatClock('not a timestamp')).toBe('not a timestamp')
  })
})

describe('formatClock', () => {
  it('drops the date, because every row in the log is from the last few minutes', () => {
    const shown = formatClock(INSTANT)
    expect(shown).not.toContain('2026')
    expect(shown).toMatch(/\d{1,2}:\d{2}/)
  })
})
