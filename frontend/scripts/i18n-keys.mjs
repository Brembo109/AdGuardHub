/**
 * Every string the UI asks to translate, and whether German has it.
 *
 * Keying translations on the English text keeps the source readable, but it is
 * silent when an English string is edited: the German simply stops matching and
 * the page quietly reverts to English. This walks the call sites so that cannot
 * happen unnoticed — `--check` exits non-zero when anything is missing.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const SRC = join(here, '..', 'src')

function walk(dir) {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    return statSync(full).isDirectory() ? walk(full) : [full]
  })
}

/** t('…') and t("…"), including calls broken across lines by the formatter. */
const CALL = /\bt\(\s*(['"])((?:\\.|(?!\1)[^\\])*?)\1/gs

export function staticKeys() {
  const keys = new Set()
  for (const file of walk(SRC)) {
    // Tests live beside the code they cover, so they are walked too — and a test
    // that quotes a `t('…')` call while describing it would otherwise register a
    // key nothing renders, failing this check for a string that does not exist.
    if (!/\.tsx?$/.test(file) || /\.test\.tsx?$/.test(file)) continue
    if (file.includes(`${join('src', 'i18n')}`)) continue
    const source = readFileSync(file, 'utf8')
    for (const match of source.matchAll(CALL)) {
      // Unescape the two sequences the source can contain.
      keys.add(match[2].replaceAll("\\'", "'").replaceAll('\\"', '"'))
    }
  }
  return [...keys].sort((a, b) => a.localeCompare(b))
}

/**
 * Strings that reach t() through a variable, so no scan can see them: table
 * definitions in the frontend, and the section metadata the backend serves.
 */
export const dynamicKeys = JSON.parse(
  readFileSync(join(SRC, 'i18n', 'dynamic-keys.json'), 'utf8'),
)

export function allKeys() {
  return [...new Set([...staticKeys(), ...dynamicKeys])].sort((a, b) => a.localeCompare(b))
}

if (process.argv[2] === '--check') {
  const dict = readFileSync(join(SRC, 'i18n', 'de.ts'), 'utf8')
  const german = new Set()
  for (const match of dict.matchAll(/^\s*(['"])((?:\\.|(?!\1)[^\\])*?)\1:/gm)) {
    german.add(match[2].replaceAll("\\'", "'").replaceAll('\\"', '"'))
  }
  const missing = allKeys().filter((key) => !german.has(key))
  const stale = [...german].filter((key) => !allKeys().includes(key))

  if (missing.length) {
    console.error(`Missing German for ${missing.length} string(s):`)
    for (const key of missing) console.error(`  ${JSON.stringify(key)}`)
  }
  if (stale.length) {
    console.error(`\n${stale.length} German entr(y/ies) no longer used by any call site:`)
    for (const key of stale) console.error(`  ${JSON.stringify(key)}`)
  }
  if (missing.length || stale.length) process.exit(1)
  console.log(`i18n: ${allKeys().length} strings, all translated.`)
} else if (process.argv[2] === '--list') {
  for (const key of allKeys()) console.log(JSON.stringify(key))
}
