import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Ctx, DICTS, LANGUAGE_KEY, fill, initialLanguage, type I18n, type Language } from '.'

/** Holds the chosen language and hands `t` to the tree below. */
export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setStored] = useState<Language>(initialLanguage)

  // The document is served with lang="en"; correct it for the language actually
  // rendered, so screen readers and the browser's own translation offer agree
  // with the page. Covers the first render as well as every later switch.
  useEffect(() => {
    document.documentElement.lang = language
  }, [language])

  const setLanguage = useCallback((next: Language) => {
    setStored(next)
    try {
      localStorage.setItem(LANGUAGE_KEY, next)
    } catch {
      // Not remembering the choice is no reason to fail the render.
    }
  }, [])

  const value = useMemo<I18n>(() => {
    const dict = DICTS[language]
    return {
      language,
      setLanguage,
      t: (text, vars) => fill(dict[text] ?? text, vars),
    }
  }, [language, setLanguage])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
