import { useCallback, useEffect, useState } from 'react'

export type Theme = 'system' | 'light' | 'dark'

const KEY = 'adguardhub-theme'
const ORDER: Theme[] = ['system', 'light', 'dark']

function stored(): Theme {
  try {
    const value = localStorage.getItem(KEY)
    if (value === 'light' || value === 'dark' || value === 'system') return value
  } catch {
    // Private windows and blocked site data both throw here; the default is fine.
  }
  return 'system'
}

/**
 * Light, dark, or whatever the operating system says.
 *
 * "system" deliberately stamps no attribute, so the stylesheet's
 * prefers-color-scheme block governs and the page follows the OS as it changes.
 */
export function useTheme(): { theme: Theme; cycle: () => void } {
  const [theme, setTheme] = useState<Theme>(stored)

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme)
    try {
      localStorage.setItem(KEY, theme)
    } catch {
      // Not being able to remember the choice is not a reason to fail the render.
    }
  }, [theme])

  const cycle = useCallback(
    () => setTheme((current) => ORDER[(ORDER.indexOf(current) + 1) % ORDER.length]),
    [],
  )

  return { theme, cycle }
}
