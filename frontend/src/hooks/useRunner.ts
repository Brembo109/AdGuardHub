/**
 * Run one action, and say what came of it.
 *
 * Settings used to be a single page whose sections shared one busy flag and one
 * pair of banners, so testing a notifier cleared the message from the password
 * you had just changed. Split into pages, each owns its own — which is also what
 * makes the split honest: the sections were never actually related.
 */

import { useState } from 'react'
import { errorMessage } from './useApi'

export type Runner = (
  action: () => Promise<string>,
  reload?: () => Promise<void>,
) => Promise<void>

export interface RunnerState {
  busy: boolean
  error: string
  message: string
  run: Runner
}

export function useRunner(): RunnerState {
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const run: Runner = async (action, reload) => {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      setMessage(await action())
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
      if (reload) await reload()
    }
  }

  return { busy, error, message, run }
}
