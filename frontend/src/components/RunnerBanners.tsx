/** The outcome of the last action, above the section that caused it. */

import type { RunnerState } from '../hooks/useRunner'
import { Banner } from './ui'

export function RunnerBanners({ state }: { state: RunnerState }) {
  return (
    <>
      {state.error ? <Banner kind="error">{state.error}</Banner> : null}
      {state.message ? <Banner kind="ok">{state.message}</Banner> : null}
    </>
  )
}
