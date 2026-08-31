/** Local timestamps; the backend speaks UTC throughout. */
export function formatTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

/** Thousands separators from the browser's locale, for counts in tiles and lists. */
export function formatCount(value: number): string {
  return value.toLocaleString()
}

/**
 * Time of day only, for logs where every row is from the last few minutes and the
 * date would just wrap the column. The full stamp belongs in a title attribute.
 */
export function formatClock(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleTimeString()
}
