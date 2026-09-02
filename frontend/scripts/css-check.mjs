/**
 * Is the stylesheet structurally intact?
 *
 * This exists because of a shipped release in which one rule lost its closing
 * brace during a merge. Nothing complained: eslint does not read CSS, tsc does
 * not read CSS, and the bundler happily built and minified it. The browser did
 * what browsers do with an unterminated rule — swallowed the nine hundred lines
 * that followed as if they were part of it — so every layout rule after that
 * point silently stopped existing, and the first screen an operator saw was a
 * column of full-width inputs flush against the left edge.
 *
 * A stylesheet that does not parse is not a style question, it is a broken
 * build, and it should fail the way a broken build fails.
 *
 * Deliberately not a linter. It answers one question — do the braces balance,
 * ignoring comments and strings — and names the rule that opened and never
 * closed, because that is the line a human needs.
 */

import { readFileSync } from 'node:fs'
import { readdirSync } from 'node:fs'
import { join } from 'node:path'
import process from 'node:process'

const SOURCE_DIR = new URL('../src/', import.meta.url).pathname

function stylesheets(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) return stylesheets(path)
    return entry.name.endsWith('.css') ? [path] : []
  })
}

/** The selector a `{` belongs to, for an error message worth reading. */
function selectorBefore(text, index) {
  const start = text.lastIndexOf('}', index) + 1
  const commentEnd = text.lastIndexOf('*/', index) + 2
  return text
    .slice(Math.max(start, commentEnd), index)
    .trim()
    .split('\n')
    .pop()
    .trim()
}

function check(path) {
  const text = readFileSync(path, 'utf8')
  const open = []
  const problems = []
  let line = 1
  let inComment = false
  let quote = ''

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i]
    if (ch === '\n') line += 1

    if (inComment) {
      if (ch === '*' && text[i + 1] === '/') {
        inComment = false
        i += 1
      }
      continue
    }
    if (quote) {
      // A backslash escapes the next character, quote included.
      if (ch === '\\') i += 1
      else if (ch === quote) quote = ''
      continue
    }
    if (ch === '/' && text[i + 1] === '*') {
      inComment = true
      i += 1
      continue
    }
    if (ch === '"' || ch === "'") {
      quote = ch
      continue
    }

    if (ch === '{') open.push({ line, selector: selectorBefore(text, i) })
    else if (ch === '}') {
      if (open.length === 0) problems.push(`${path}:${line}  a '}' closes a rule that was never opened`)
      else open.pop()
    }
  }

  for (const { line: at, selector } of open) {
    problems.push(
      `${path}:${at}  '${selector}' is never closed — everything after it is swallowed by this rule`,
    )
  }
  return problems
}

const problems = stylesheets(SOURCE_DIR).flatMap(check)

if (problems.length) {
  console.error('css: the stylesheet does not parse.\n')
  for (const problem of problems) console.error(`  ${problem}`)
  console.error('')
  process.exit(1)
}

console.log(`css: ${stylesheets(SOURCE_DIR).length} stylesheet(s), braces balanced.`)
