/**
 * What a node says about its own AdGuard Home version.
 *
 * Three states, not two. A node can offer a newer build, be current, or be
 * unable to say — its update check can be switched off in its own
 * configuration, and older builds have no endpoint for it. The third must never
 * render as the second: telling an operator their DNS is current when nobody
 * actually asked is worse than saying nothing.
 */

import type { Instance } from '../api/types'
import { useT } from '../i18n'
import { nodeUpdateState } from '../nodes'

export function NodeUpdate({ instance }: { instance: Instance }) {
  const t = useT()

  const state = nodeUpdateState(instance)

  if (state === 'behind') {
    const label = t('update to {version}', { version: instance.update_version })
    return (
      <span className="node-update">
        {instance.update_url ? (
          <a href={instance.update_url} target="_blank" rel="noreferrer noopener">
            {label}
          </a>
        ) : (
          label
        )}
      </span>
    )
  }

  if (state === 'unknown') {
    // Deliberately quiet: it is a thing the hub could not find out, not a fault
    // in the node, and it must not read as an update being available.
    return (
      <span className="hint" title={instance.update_error}>
        {t('update unknown')}
      </span>
    )
  }

  return null
}
