/**
 * Which log lines the operator wants to see.
 *
 * Its own module rather than part of the page, so the decision to hide a line
 * can be tested on its own — and because the one rule that matters here is easy
 * to break by accident later: a level this build does not recognise is shown,
 * never hidden.
 */

import type { LogLine } from '../../api/types'

/** Python's numeric levels, plus the aliases some libraries use. */
const SEVERITY: Record<string, number> = {
  DEBUG: 10,
  INFO: 20,
  WARN: 30,
  WARNING: 30,
  ERROR: 40,
  CRITICAL: 50,
  FATAL: 50,
}

export interface LogFilter {
  /** Minimum severity to show; 0 shows everything. */
  floor: number
  /** Exact logger name, or empty for all of them. */
  logger: string
  /** Substring of the line, case-insensitively. */
  text: string
}

export const NO_FILTER: LogFilter = { floor: 0, logger: '', text: '' }

export function isFiltering(filter: LogFilter): boolean {
  return filter.floor !== 0 || filter.logger !== '' || filter.text !== ''
}

export function matches(line: LogLine, filter: LogFilter): boolean {
  if (filter.logger && line.logger !== filter.logger) return false
  if (filter.floor) {
    const rank = SEVERITY[(line.level || '').toUpperCase()]
    // A level this build has never heard of is shown, not hidden. Swallowing
    // the unfamiliar is the one failure a log filter must not have — the line
    // nobody recognises is usually the line worth reading.
    if (rank !== undefined && rank < filter.floor) return false
  }
  if (filter.text && !line.message.toLowerCase().includes(filter.text.toLowerCase())) return false
  return true
}

/** `app.services.sync` is the module path; the `app.` in front of it says nothing. */
export function sourceLabel(logger: string): string {
  return logger.startsWith('app.') ? logger.slice(4) : logger
}
