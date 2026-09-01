/**
 * Runs before every test file.
 *
 * Testing Library normally unmounts what a test rendered by registering its own
 * `afterEach`, but that only happens when Vitest is running with `globals: true`.
 * This project does not enable globals — imported `describe`/`it` are clearer
 * about where they come from — so the cleanup has to be wired up explicitly.
 *
 * Without it the DOM accumulates across tests in a file, and a query that should
 * match one element matches every copy rendered so far. That failure reads like
 * a bug in the component rather than a missing hook, which is exactly the kind
 * of confusion worth spending six lines to avoid.
 */

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(cleanup)
