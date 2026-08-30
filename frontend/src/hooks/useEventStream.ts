import { useEffect, useRef, useState } from 'react'

export interface HubEvent {
  event: string
  data: unknown
}

/**
 * Subscribes to the backend's SSE stream. The browser's EventSource reconnects on
 * its own, so `connected` mostly reflects whether the backend is currently up.
 */
export function useEventStream(onEvent: (event: HubEvent) => void): boolean {
  const [connected, setConnected] = useState(false)
  const handler = useRef(onEvent)
  handler.current = onEvent

  useEffect(() => {
    const source = new EventSource('/api/stream')
    source.onopen = () => setConnected(true)
    source.onerror = () => setConnected(false)
    source.onmessage = (message) => {
      try {
        handler.current(JSON.parse(message.data) as HubEvent)
      } catch {
        // Keep-alive comments and malformed frames are simply ignored.
      }
    }
    return () => source.close()
  }, [])

  return connected
}
