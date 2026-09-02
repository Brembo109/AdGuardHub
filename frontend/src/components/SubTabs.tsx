/**
 * The second level of navigation, inside a page.
 *
 * The top bar had grown to nine entries and Settings to six stacked cards, and
 * the obvious fix — a menu that opens on hover — is the one that does not
 * survive contact with a tablet: there is no hover, so the destinations simply
 * become unreachable. AdGuard Home, sitting next to this in most people's tabs,
 * solves the same problem the same way this does: the bar stays flat and short,
 * and a page that covers several things carries tabs of its own.
 *
 * They are links, not state. Every tab is a real route, so it can be
 * bookmarked, opened in a new tab, and reached by the back button — which is
 * the whole difference between a second level of navigation and a widget.
 */

import { NavLink } from 'react-router-dom'
import { useT } from '../i18n'
import type { SubTab } from '../nav'

export function SubTabs({ tabs }: { tabs: SubTab[] }) {
  const t = useT()
  return (
    <nav className="subtabs">
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end
          className={({ isActive }) => `subtab${isActive ? ' active' : ''}`}
        >
          {t(tab.label)}
          {tab.badge ? <span className="subtab-badge">{tab.badge}</span> : null}
        </NavLink>
      ))}
    </nav>
  )
}
