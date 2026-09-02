/**
 * One stroke-based icon set, drawn inline.
 *
 * Kept in the repo rather than pulled from an icon package: the hub ships as a
 * single image for a local network, and a handful of glyphs is not worth a
 * dependency.
 */

interface IconProps {
  size?: number
  className?: string
}

const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
})

export function IconSun({ size = 18 }: IconProps) {
  return (
    <svg {...base(size)}>
      <circle cx="12" cy="12" r="3.6" />
      <path d="M12 3v2M12 19v2M5 12H3M21 12h-2M6.3 6.3 4.9 4.9M19.1 19.1l-1.4-1.4M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4" />
    </svg>
  )
}

export function IconMoon({ size = 18 }: IconProps) {
  return (
    <svg {...base(size)}>
      <path d="M20.5 14.4A8.5 8.5 0 0 1 9.6 3.5a8.5 8.5 0 1 0 10.9 10.9" />
    </svg>
  )
}

export function IconMonitor({ size = 18 }: IconProps) {
  return (
    <svg {...base(size)}>
      <rect x="3" y="4" width="18" height="12.5" rx="1.6" />
      <path d="M9 20.5h6M12 16.5v4" />
    </svg>
  )
}

export function IconChevron({ size = 12, up = false }: IconProps & { up?: boolean }) {
  return (
    <svg {...base(size)} strokeWidth={2.2}>
      <path d={up ? 'm6 15 6-6 6 6' : 'm6 9 6 6 6-6'} />
    </svg>
  )
}

export function IconSearch({ size = 15 }: IconProps) {
  return (
    <svg {...base(size)} strokeWidth={1.9}>
      <circle cx="11" cy="11" r="6.6" />
      <path d="m16.2 16.2 4 4" />
    </svg>
  )
}

export function IconDots({ size = 16 }: IconProps) {
  return (
    <svg width={size} height="4" viewBox="0 0 16 4" fill="currentColor" aria-hidden="true">
      <circle cx="2" cy="2" r="1.6" />
      <circle cx="8" cy="2" r="1.6" />
      <circle cx="14" cy="2" r="1.6" />
    </svg>
  )
}

export function IconWarning({ size = 16 }: IconProps) {
  return (
    <svg {...base(size)} strokeWidth={1.9}>
      <path d="M12 4.5 21 20H3z" />
      <path d="M12 10v4.2M12 17.2v.1" strokeWidth={2.1} />
    </svg>
  )
}

export function IconCheck({ size = 15 }: IconProps) {
  return (
    <svg {...base(size)}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8 12.3 2.7 2.7L16 9.7" strokeWidth={2} />
    </svg>
  )
}

export function IconMenu({ size = 20 }: IconProps) {
  return (
    <svg {...base(size)} strokeWidth={2}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  )
}

/** The one filled mark in the set: the logo is a shape, not strokes. */
export function IconGitHub({ size = 15 }: IconProps) {
  return (
    <svg {...base(size)} fill="currentColor" stroke="none">
      <path d="M12 2a10 10 0 0 0-3.16 19.49c.5.09.69-.22.69-.48l-.01-1.7c-2.78.6-3.37-1.34-3.37-1.34-.45-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.89 1.53 2.34 1.09 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.56-1.11-4.56-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.65 0 0 .84-.27 2.75 1.02a9.5 9.5 0 0 1 5 0c1.91-1.29 2.75-1.02 2.75-1.02.55 1.38.2 2.4.1 2.65.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.68-4.57 4.93.36.31.68.92.68 1.85l-.01 2.75c0 .27.18.58.69.48A10 10 0 0 0 12 2Z" />
    </svg>
  )
}
