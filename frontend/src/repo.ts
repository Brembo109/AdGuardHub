/**
 * Where this hub's source lives, and how to link at the build that is running.
 *
 * Its own module rather than a constant in the footer: a component file that
 * also exports helpers loses fast refresh, and the release URL is the kind of
 * thing worth testing without rendering anything.
 */

export const REPO_URL = 'https://github.com/fgrfn/adguardhub'

/**
 * The page for a given build. Released images carry the git tag they were cut
 * from, and those tags are `vX.Y.Z`; anything else — an unreleased build says
 * "dev" — has no release page, so it goes to the repository.
 */
export function releaseUrl(version: string): string {
  if (!/^v?\d+\.\d+\.\d+/.test(version)) return REPO_URL
  return `${REPO_URL}/releases/tag/${version.startsWith('v') ? version : `v${version}`}`
}
