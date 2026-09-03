/**
 * Where the interface's second level lives.
 *
 * In one module rather than next to each page: both halves of a pair render the
 * same strip, so defining it twice would let the two drift apart — a tab list
 * that disagrees with itself depending on which tab you are standing on is
 * worse than no tabs. It is also plain data, which keeps fast refresh working
 * in the component files that use it.
 */

export interface SubTab {
  to: string
  /** English source text; the strip translates it. */
  label: string
  /** A count or state beside the label, already formatted. */
  badge?: string
}

/** The central rule set and the lists that are fetched rather than written. */
export const FILTER_TABS: SubTab[] = [
  { to: '/rules', label: 'Rules' },
  { to: '/subscriptions', label: 'Filter lists' },
]

/** A node, and what the hub replicates to it — one subject, two pages. */
export const INSTANCE_TABS: SubTab[] = [
  { to: '/instances', label: 'Instances' },
  { to: '/config', label: 'Instance settings' },
]

/** How the hub behaves, as five unrelated things that used to be one page. */
export const SETTINGS_TABS: SubTab[] = [
  { to: '/settings', label: 'General' },
  { to: '/settings/notifications', label: 'Notifications' },
  { to: '/settings/updates', label: 'Updates' },
  { to: '/settings/security', label: 'Security' },
  { to: '/settings/log', label: 'Log' },
  { to: '/settings/backup', label: 'Backup' },
  { to: '/settings/diagnostics', label: 'Diagnostics' },
]

/**
 * Whether a grouped entry owns the page currently open.
 *
 * A NavLink only knows about its own path, so "Filter" would go dark the moment
 * you opened the filter lists — telling you that you had left the section you
 * are looking at. This is what keeps the top level lit while you move between
 * its tabs.
 */
export function covers(item: { covers?: string[] }, pathname: string): boolean {
  return (item.covers ?? []).some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  )
}
