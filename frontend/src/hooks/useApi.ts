import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return String(error)
}

/**
 * Loads data on mount and exposes a `reload` for after mutations.
 * `deps` re-runs the fetch, e.g. when a filter changes.
 */
export function useResource<T>(
  loader: () => Promise<T>,
  deps: unknown[] = [],
): {
  data: T | null
  error: string
  loading: boolean
  reload: () => Promise<void>
  setData: (value: T) => void
} {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const loaderRef = useRef(loader)
  loaderRef.current = loader
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const result = await loaderRef.current()
      if (alive.current) {
        setData(result)
        setError('')
      }
    } catch (caught) {
      if (alive.current) setError(errorMessage(caught))
    } finally {
      if (alive.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { data, error, loading, reload, setData }
}
