import { createContext, useContext } from 'react'
import { de } from './de'

export type Language = 'en' | 'de'

/**
 * Translation, keyed by the English text itself.
 *
 * Invented keys ("rules.page.title") would leave the source unreadable and the
 * English copy in a file far from where it is rendered. Keying on the English
 * means the page still reads as prose, and a missing translation falls back to
 * a correct English sentence rather than to a key.
 *
 * The risk of that scheme is silence: edit an English string and its German
 * quietly stops matching. A test walks every t("…") call site and fails when one
 * has no German entry, so that cannot pass CI unnoticed.
 */
export const DICTS: Record<Language, Record<string, string>> = { en: {}, de }

export const LANGUAGES: { code: Language; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'de', label: 'Deutsch' },
]

export const LANGUAGE_KEY = 'adguardhub-language'

export function initialLanguage(): Language {
  try {
    const stored = localStorage.getItem(LANGUAGE_KEY)
    if (stored === 'en' || stored === 'de') return stored
  } catch {
    // Private windows and blocked site data both throw; fall through.
  }
  // Follow the browser rather than defaulting to English for a German operator.
  return navigator.language?.toLowerCase().startsWith('de') ? 'de' : 'en'
}

export type Vars = Record<string, string | number>

export function fill(text: string, vars?: Vars): string {
  if (!vars) return text
  return text.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in vars ? String(vars[name]) : whole,
  )
}

export interface I18n {
  language: Language
  setLanguage: (language: Language) => void
  t: (text: string, vars?: Vars) => string
}

export const Ctx = createContext<I18n | null>(null)

export function useI18n(): I18n {
  const value = useContext(Ctx)
  if (!value) throw new Error('useI18n used outside I18nProvider')
  return value
}

/** Shorthand for the common case of only needing the translate function. */
export function useT(): I18n['t'] {
  return useI18n().t
}
