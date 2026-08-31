/**
 * The two chart forms the dashboard needs, drawn as inline SVG.
 *
 * No charting library: a hub that ships as one image for a local network should not
 * carry a few hundred kilobytes of plotting engine for one area chart and one ring.
 */

import { formatCount } from '../format'

const W = 880
const H = 232
const LEFT = 44
const TOP = 10
const PLOT_W = 828
const PLOT_H = 196

function niceMax(value: number): number {
  if (value <= 0) return 1
  const magnitude = 10 ** Math.floor(Math.log10(value))
  for (const step of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) {
    if (magnitude * step >= value) return magnitude * step
  }
  return magnitude * 10
}

function short(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1)}M`
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 10_000 ? 0 : 1)}k`
  return String(Math.round(value))
}

interface SeriesChartProps {
  queries: number[]
  blocked: number[]
  /** What one step on the x axis represents, as the instances report it. */
  unit: string
}

/**
 * Two layered areas on one axis. Blocked is a subset of queries, so it is drawn
 * over the same baseline rather than stacked — stacking would double the totals.
 */
export function SeriesChart({ queries, blocked, unit }: SeriesChartProps) {
  const points = Math.max(queries.length, blocked.length)
  if (points < 2) {
    return <div className="empty">Not enough history yet to draw a chart.</div>
  }

  const max = niceMax(Math.max(...queries, ...blocked, 1))
  const x = (index: number) => LEFT + (index * PLOT_W) / (points - 1)
  const y = (value: number) => TOP + PLOT_H * (1 - value / max)

  const line = (values: number[]) =>
    values.map((value, index) => `${index ? 'L' : 'M'}${x(index)} ${y(value)}`).join(' ')
  const area = (values: number[]) =>
    `${line(values)} L${x(values.length - 1)} ${TOP + PLOT_H} L${x(0)} ${TOP + PLOT_H} Z`

  const ticks = [0, 0.25, 0.5, 0.75, 1].map((fraction) => ({
    value: max * fraction,
    y: TOP + PLOT_H * (1 - fraction),
  }))
  // Roughly six labels, whatever the series length, without crowding.
  const every = Math.max(1, Math.round((points - 1) / 6))
  const xLabels = queries
    .map((_, index) => index)
    .filter((index) => index % every === 0 || index === points - 1)

  const peak = queries.indexOf(Math.max(...queries))

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      style={{ width: '100%', height: 'auto', display: 'block' }}
      role="img"
      aria-label={`DNS queries and blocked queries per ${unit.replace(/s$/, '')}`}
    >
      <g stroke="var(--grid)" strokeWidth="1">
        {ticks.map((tick) => (
          <line key={tick.y} x1={LEFT} y1={tick.y} x2={W - 4} y2={tick.y} />
        ))}
      </g>
      <g fill="var(--faint)" fontSize="10.5" textAnchor="end">
        {ticks.map((tick) => (
          <text key={tick.y} x={LEFT - 8} y={tick.y + 3}>
            {short(tick.value)}
          </text>
        ))}
      </g>

      <path d={area(queries)} fill="var(--series-a)" fillOpacity="0.14" />
      <path d={area(blocked)} fill="var(--series-b)" fillOpacity="0.18" />
      <path
        d={line(queries)}
        fill="none"
        stroke="var(--series-a)"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <path
        d={line(blocked)}
        fill="none"
        stroke="var(--series-b)"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* Direct labels at the busiest point, so identity never rests on colour alone. */}
      <circle
        cx={x(peak)}
        cy={y(queries[peak])}
        r="3.6"
        fill="var(--series-a)"
        stroke="var(--card)"
        strokeWidth="2"
      />
      <text
        x={x(peak) + (peak > points * 0.7 ? -8 : 8)}
        y={y(queries[peak]) - 8}
        fill="var(--accent-ink)"
        fontSize="11.5"
        fontWeight="600"
        textAnchor={peak > points * 0.7 ? 'end' : 'start'}
      >
        {formatCount(queries[peak])} queries
      </text>

      <g fill="var(--faint)" fontSize="10.5" textAnchor="middle">
        {xLabels.map((index) => (
          <text key={index} x={x(index)} y={H - 6}>
            {index === points - 1 ? 'now' : `-${points - 1 - index}${unit.slice(0, 1)}`}
          </text>
        ))}
      </g>
    </svg>
  )
}

/** One proportion, with the number as the hero rather than the arc. */
export function BlockRateRing({ rate }: { rate: number }) {
  const radius = 52
  const circumference = 2 * Math.PI * radius
  const share = Math.max(0, Math.min(100, rate)) / 100

  return (
    <svg
      width="150"
      height="150"
      viewBox="0 0 150 150"
      role="img"
      aria-label={`Block rate ${rate.toFixed(1)} percent`}
    >
      <circle cx="75" cy="75" r={radius} fill="none" stroke="var(--line)" strokeWidth="15" />
      <circle
        cx="75"
        cy="75"
        r={radius}
        fill="none"
        stroke="var(--series-b)"
        strokeWidth="15"
        strokeLinecap="round"
        strokeDasharray={`${circumference * share} ${circumference * (1 - share)}`}
        transform="rotate(-90 75 75)"
      />
      <text
        x="75"
        y="72"
        textAnchor="middle"
        fontSize="30"
        fontWeight="680"
        fill="var(--text)"
        style={{ fontVariantNumeric: 'tabular-nums' }}
      >
        {rate.toFixed(1)}%
      </text>
      <text x="75" y="92" textAnchor="middle" fontSize="11.5" fill="var(--dim)">
        blocked
      </text>
    </svg>
  )
}

/** A ranked list with the bar inside the row — a chart would say no more. */
export function RankList({
  entries,
  tone,
}: {
  entries: { name: string; count: number }[]
  tone: 'a' | 'b'
}) {
  if (!entries.length) return <div className="empty">Nothing reported yet.</div>
  const top = entries[0].count || 1
  const colour = tone === 'a' ? 'var(--series-a)' : 'var(--series-b)'

  return (
    <div className="ranks">
      {entries.map((entry) => (
        <div key={entry.name}>
          <div className="rank">
            <span className="mono">{entry.name}</span>
            <span className="count">{formatCount(entry.count)}</span>
          </div>
          <div className="bar-track">
            <div
              className="bar-fill"
              style={{ background: colour, width: `${Math.max(4, (entry.count / top) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}
