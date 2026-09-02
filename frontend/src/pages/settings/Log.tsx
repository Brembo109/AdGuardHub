/**
 * The hub's own log, followed live.
 *
 * Not the query log — that is DNS traffic and has its own page. This is the hub
 * talking about itself: what it did on start, a push that failed, a refused
 * sign-in. Reading it used to mean `docker logs` or a shell, which is what you
 * do not have when you are looking at a hub from a phone, or helping somebody
 * else look at theirs.
 *
 * Polled with a cursor rather than streamed. The hub already runs one event
 * stream for the shell, and putting log lines through it would mean the act of
 * delivering a line producing a line — so this asks, on a timer, for whatever is
 * newer than the last sequence number it holds. Following along costs one small
 * response; nothing is re-sent.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { LogLine } from '../../api/types'
import { Card, Empty } from '../../components/ui'
import { useT } from '../../i18n'

const POLL_MS = 2000

/** Enough to scroll back through a restart, matching the buffer the hub keeps. */
const KEEP = 500

export default function SettingsLog() {
  const t = useT()
  const [lines, setLines] = useState<LogLine[]>([])
  const [following, setFollowing] = useState(true)
  const [error, setError] = useState('')
  const cursor = useRef(0)
  const box = useRef<HTMLDivElement>(null)

  const poll = useCallback(async () => {
    try {
      const body = await api.log(cursor.current)
      cursor.current = body.cursor
      setError('')
      if (body.lines.length) {
        setLines((current) => [...current, ...body.lines].slice(-KEEP))
      }
    } catch {
      // A hub mid-restart stops answering for a moment. That is not worth a
      // banner — the next poll picks up where this one left off, and the cursor
      // means nothing is missed in between.
      setError(t('Waiting for the hub…'))
    }
  }, [t])

  useEffect(() => {
    void poll()
    if (!following) return
    const timer = setInterval(() => void poll(), POLL_MS)
    return () => clearInterval(timer)
  }, [poll, following])

  // Follow the tail, unless the operator has scrolled up to read something.
  useEffect(() => {
    const node = box.current
    if (node && following) node.scrollTop = node.scrollHeight
  }, [lines, following])

  return (
    <Card
      title={t('Application log')}
      hint={t(
        'What the hub itself is doing. Kept in memory only — the last {count} lines, cleared on restart. Your container or systemd log remains the record.',
        { count: String(KEEP) },
      )}
    >
      <div className="actions" style={{ marginBottom: 12 }}>
        <label className="checkbox" style={{ marginBottom: 0 }}>
          <input
            type="checkbox"
            checked={following}
            onChange={(event) => setFollowing(event.target.checked)}
          />
          {t('Follow')}
        </label>
        <button type="button" className="small" onClick={() => setLines([])}>
          {t('Clear view')}
        </button>
        {error ? <span className="hint">{error}</span> : null}
      </div>

      {lines.length ? (
        <div className="run-log" ref={box}>
          {lines.map((line) => (
            <div key={line.seq} className={`log-line ${line.level.toLowerCase()}`}>
              {line.message}
            </div>
          ))}
        </div>
      ) : (
        <Empty>{t('Nothing logged yet.')}</Empty>
      )}
    </Card>
  )
}
