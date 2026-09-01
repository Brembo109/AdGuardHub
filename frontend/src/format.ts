/**
 * Dates and numbers, formatted for the language the interface is actually in.
 *
 * These used to call `toLocaleString()` with no locale, which follows the
 * *browser*, not the UI. So switching the hub to German on a browser set to
 * en-US left every timestamp in American order — `9/1/2026, 2:38:49 PM` under a
 * German heading, which reads as the wrong date rather than a different format.
 *
 * The language lives in React state, but these are plain functions called from
 * dozens of call sites and from inside SVG. Rather than turn each of them into a
 * hook, the provider pushes the active language here whenever it changes, and
 * the formatters read it. Anything rendered before the provider mounts falls
 * back to the browser's own locale, which is what it always did.
 */

let locale: string | undefined

/**
 * Called by the i18n provider. Not part of the public formatting surface.
 *
 * English stays on the browser's own locale rather than being pinned to one
 * English region: `en` is spoken in places that write the date in opposite
 * orders, and an American reading the English UI should keep seeing American
 * dates. German has one convention, so it can be pinned, and pinning it is the
 * whole point — the operator picked German.
 */
export function setFormatLocale(language: string): void {
  locale = language === 'de' ? 'de-DE' : undefined
}

/** Local timestamps; the backend speaks UTC throughout. */
export function formatTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(locale)
}

/** Thousands separators for counts in tiles and lists. */
export function formatCount(value: number): string {
  return value.toLocaleString(locale)
}

/**
 * Time of day only, for logs where every row is from the last few minutes and the
 * date would just wrap the column. The full stamp belongs in a title attribute.
 */
export function formatClock(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleTimeString(locale)
}
