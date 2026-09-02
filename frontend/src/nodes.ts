/**
 * What a node says about its own AdGuard Home version.
 *
 * Three states, not two, and keeping them apart is the whole feature. A node
 * can offer a newer build, be current, or be unable to say — its update check
 * can be switched off in its own configuration, and older builds have no
 * endpoint for it at all. "Could not find out" rendering as "up to date" would
 * tell an operator their DNS is current when nobody actually asked.
 *
 * Plain data and a pure function so the distinction can be tested without
 * rendering anything.
 */

import type { Instance } from './api/types'

export type NodeUpdateState = 'behind' | 'current' | 'unknown'

export function nodeUpdateState(instance: Instance): NodeUpdateState {
  if (instance.update_version) return 'behind'
  // Checked after the offer on purpose: a node that answered with an update and
  // also left an error behind has still told us something worth acting on.
  if (instance.update_error) return 'unknown'
  return 'current'
}

/** The nodes worth leading with, in the order they were given. */
export function nodesBehind(instances: Instance[] | null | undefined): Instance[] {
  return (instances ?? []).filter((instance) => nodeUpdateState(instance) === 'behind')
}

/** "agh-a → v0.107.64, agh-b → v0.107.64" — the nodes and what each would move to. */
export function behindLabel(instances: Instance[]): string {
  return instances.map((item) => `${item.name} \u2192 ${item.update_version}`).join(', ')
}
