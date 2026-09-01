/**
 * The translation layer's two pieces of real logic.
 *
 * `fill` interpolates `{name}` placeholders. Everything user-facing that
 * mentions a count, a node or an error goes through it, so the case that
 * matters is the one where a variable is *missing*: leaving the placeholder
 * visible is ugly, but printing "undefined" into a sentence is worse, and
 * dropping it silently changes what the sentence claims.
 *
 * `initialLanguage` decides what a first-time visitor sees. It reads
 * localStorage, which throws outright in a private window or with site data
 * blocked — so the interesting property is that it never takes the page down.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { DICTS, LANGUAGES, LANGUAGE_KEY, fill, initialLanguage } from '.'

afterEach(() => {
  localStorage.clear()
})

describe('fill', () => {
  it('substitutes a placeholder', () => {
    expect(fill('Pushed to {count} instances', { count: 2 })).toBe('Pushed to 2 instances')
  })

  it('substitutes several, including the same one twice', () => {
    expect(fill('{a} then {b} then {a}', { a: 'x', b: 'y' })).toBe('x then y then x')
  })

  it('leaves a placeholder alone when nothing was passed for it', () => {
    // Visible and wrong beats invisible and wrong: "{names}" in the UI is a bug
    // report, "undefined" reads like a real value.
    expect(fill('could not reach {names}', {})).toBe('could not reach {names}')
    expect(fill('could not reach {names}')).toBe('could not reach {names}')
  })

  it('renders a zero rather than dropping it', () => {
    expect(fill('{count} queued', { count: 0 })).toBe('0 queued')
  })

  it('does not touch text that has no placeholders', () => {
    expect(fill('Reconcile', { count: 3 })).toBe('Reconcile')
  })

  it('leaves braces that are not placeholders', () => {
    expect(fill('a { b } c', { b: 'x' })).toBe('a { b } c')
  })
})

describe('initialLanguage', () => {
  it('uses a remembered choice', () => {
    localStorage.setItem(LANGUAGE_KEY, 'de')
    expect(initialLanguage()).toBe('de')
  })

  it('ignores a stored value that is not a language we ship', () => {
    localStorage.setItem(LANGUAGE_KEY, 'klingon')
    expect(initialLanguage()).toBe('en')
  })

  it('follows the browser when nothing is stored', () => {
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('de-AT')
    expect(initialLanguage()).toBe('de')
  })

  it('matches the language case-insensitively', () => {
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('DE')
    expect(initialLanguage()).toBe('de')
  })

  it('falls back to English for a language we do not ship', () => {
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('fr-FR')
    expect(initialLanguage()).toBe('en')
  })

  it('survives localStorage throwing, as it does in a private window', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('The operation is insecure.', 'SecurityError')
    })
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('de')
    expect(initialLanguage()).toBe('de')
  })
})

describe('the dictionaries', () => {
  it('ships every language the switcher offers', () => {
    for (const { code } of LANGUAGES) {
      expect(DICTS[code], `no dictionary for ${code}`).toBeDefined()
    }
  })

  it('leaves English empty, because it is the source text', () => {
    expect(DICTS.en).toEqual({})
  })

  it('never maps a German entry to an empty string', () => {
    // An empty translation is worse than a missing one: the fallback would have
    // shown correct English, this shows nothing at all.
    const blank = Object.entries(DICTS.de)
      .filter(([, value]) => !value.trim())
      .map(([key]) => key)
    expect(blank).toEqual([])
  })
})
