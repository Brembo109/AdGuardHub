/**
 * The two charts, which are hand-drawn SVG rather than a library.
 *
 * That is a deliberate choice — a hub that ships as one image for a network
 * with no internet should not carry a plotting engine — but it means the axis
 * scaling and the text fitting are ours to get right, and both were arrived at
 * by measuring rendered strings by hand. These tests hold those measurements
 * still.
 */

import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { ReactNode } from 'react'
import { LANGUAGE_KEY } from '../i18n'
import { I18nProvider } from '../i18n/provider'
import { BlockRateRing, RankList, SeriesChart } from './charts'

afterEach(() => {
  // The provider reads the remembered language at mount, so a test that
  // switches to German must not decide the next test's language.
  localStorage.clear()
})

function show(ui: ReactNode) {
  return render(<I18nProvider>{ui}</I18nProvider>)
}

/** Every `<text>` in the rendered SVG, trimmed. */
function labels(container: HTMLElement): string[] {
  return [...container.querySelectorAll('text')].map((node) => node.textContent?.trim() ?? '')
}

describe('BlockRateRing', () => {
  it('shows one decimal', () => {
    const { container } = show(<BlockRateRing rate={26.42} />)
    expect(labels(container)).toContain('26.4%')
  })

  it('drops the decimal at the top of the range, where it would not fit', () => {
    // The ring leaves 89px clear inside its stroke. "100.0%" measured 100px,
    // which ran into the arc; "100%" fits. The decimal is dropped only here, so
    // ordinary values keep their precision instead of every value shrinking to
    // accommodate a state that means the network is blocking everything.
    const { container } = show(<BlockRateRing rate={100} />)
    expect(labels(container)).toContain('100%')
    expect(labels(container)).not.toContain('100.0%')
  })

  it('rounds up into that case rather than printing "100.0%"', () => {
    // 99.96 rounds to "100.0" on toFixed(1), so the threshold has to be tested
    // against the rendered string, not against the number.
    const { container } = show(<BlockRateRing rate={99.96} />)
    expect(labels(container)).toContain('100%')
  })

  it('keeps the decimal just below the threshold', () => {
    const { container } = show(<BlockRateRing rate={99.9} />)
    expect(labels(container)).toContain('99.9%')
  })

  it('clamps a nonsensical rate instead of drawing an arc past the circle', () => {
    const over = show(<BlockRateRing rate={140} />).container
    const under = show(<BlockRateRing rate={-20} />).container
    const arc = (c: HTMLElement) => c.querySelectorAll('circle')[1].getAttribute('stroke-dasharray')
    const [filled, gap] = arc(over)!.split(' ').map(Number)
    expect(gap).toBeCloseTo(0, 5)
    expect(filled).toBeGreaterThan(0)
    const [noFill] = arc(under)!.split(' ').map(Number)
    expect(noFill).toBeCloseTo(0, 5)
  })

  it('labels itself for a screen reader', () => {
    show(<BlockRateRing rate={26.4} />)
    expect(screen.getByRole('img')).toHaveProperty('tagName', 'svg')
  })
})

describe('SeriesChart', () => {
  const flat = (values: number[]) => values.map(() => 0)

  it('says so rather than drawing a line through one point', () => {
    show(<SeriesChart queries={[5]} blocked={[1]} unit="hours" />)
    expect(screen.getByText(/Not enough history/)).toBeTruthy()
  })

  it('rounds the axis up to a readable maximum', () => {
    // 413 becomes 500, not 413: the gridline labels are meant to be read, and
    // "413" as a top tick is noise.
    const queries = [10, 200, 413, 120]
    const { container } = show(
      <SeriesChart queries={queries} blocked={flat(queries)} unit="hours" />,
    )
    expect(labels(container)).toContain('500')
  })

  it('abbreviates a large axis instead of spelling out every digit', () => {
    const queries = [100, 1200, 900, 400]
    const { container } = show(
      <SeriesChart queries={queries} blocked={flat(queries)} unit="hours" />,
    )
    expect(labels(container)).toContain('1.5k')
  })

  it('does not collapse to a zero axis when nothing was queried', () => {
    const { container } = show(<SeriesChart queries={[0, 0, 0]} blocked={[0, 0, 0]} unit="hours" />)
    expect(labels(container)).toContain('1')
  })

  it('names the busiest point', () => {
    const queries = [10, 200, 413, 120]
    const { container } = show(
      <SeriesChart queries={queries} blocked={flat(queries)} unit="hours" />,
    )
    expect(labels(container)).toContain('413 queries')
  })

  it('translates that label rather than concatenating an English word', () => {
    // Asserted in German on purpose. In English the broken version — a bare
    // "queries" next to the number — renders identical text content, so an
    // English assertion here would pass either way and pin nothing.
    localStorage.setItem(LANGUAGE_KEY, 'de')
    const queries = [10, 200, 413, 120]
    const { container } = show(
      <SeriesChart queries={queries} blocked={flat(queries)} unit="hours" />,
    )
    expect(labels(container)).toContain('413 Anfragen')
  })

  it('ends the x axis at "now"', () => {
    const queries = [1, 2, 3, 4]
    const { container } = show(
      <SeriesChart queries={queries} blocked={flat(queries)} unit="hours" />,
    )
    expect(labels(container)).toContain('now')
  })
})

describe('RankList', () => {
  it('says nothing was reported rather than drawing an empty list', () => {
    show(<RankList entries={[]} tone="a" />)
    expect(screen.getByText(/Nothing reported yet/)).toBeTruthy()
  })

  it('scales every bar against the leader, not against the total', () => {
    const { container } = show(
      <RankList
        entries={[
          { name: 'a.example', count: 100 },
          { name: 'b.example', count: 50 },
        ]}
        tone="a"
      />,
    )
    const widths = [...container.querySelectorAll<HTMLElement>('.bar-fill')].map(
      (node) => node.style.width,
    )
    expect(widths).toEqual(['100%', '50%'])
  })

  it('keeps a sliver visible for a count that would otherwise round to nothing', () => {
    const { container } = show(
      <RankList
        entries={[
          { name: 'a.example', count: 10_000 },
          { name: 'b.example', count: 1 },
        ]}
        tone="b"
      />,
    )
    const last = container.querySelectorAll<HTMLElement>('.bar-fill')[1]
    expect(parseFloat(last.style.width)).toBeGreaterThan(0)
  })

  it('groups thousands in the counts', () => {
    show(<RankList entries={[{ name: 'a.example', count: 2612 }]} tone="a" />)
    expect(screen.getByText('2,612')).toBeTruthy()
  })
})
