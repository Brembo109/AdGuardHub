export type RuleKind = 'allow' | 'block'
export type RuleOrigin = 'custom' | 'allowlist' | 'querylog'
export type ListKind = 'blocklist' | 'allowlist'
export type NotifierType = 'homeassistant' | 'discord' | 'gotify'

export interface AuthState {
  authenticated: boolean
  username: string | null
  setup_required: boolean
  ephemeral_secret: boolean
}

export interface Instance {
  id: number
  name: string
  base_url: string
  adapter: string
  username: string
  has_password: boolean
  verify_tls: boolean
  enabled: boolean
  status: 'unknown' | 'online' | 'unreachable' | 'disabled'
  last_error: string
  last_seen_at: string | null
  last_synced_at: string | null
  created_at: string
}

export interface Rule {
  id: number
  text: string
  kind: RuleKind
  origin: RuleOrigin
  enabled: boolean
  comment: string
  created_at: string
  updated_at: string
}

export interface FilterList {
  id: number
  name: string
  url: string
  kind: ListKind
  enabled: boolean
  created_at: string
}

export interface QueryLogEntry {
  instance: string
  time: string
  question: string
  question_type: string
  client: string
  answer_status: string
  blocked: boolean
  rule: string
  elapsed_ms: number
  upstream: string
}

export interface PushJob {
  id: number
  instance_id: number
  instance_name: string
  payload_kind: string
  status: 'pending' | 'applied' | 'failed'
  attempts: number
  last_error: string
  reason: string
  updated_at: string
}

export interface DriftEvent {
  id: number
  instance_id: number | null
  instance_name: string
  payload_kind: string
  summary: string
  details: string
  corrected: boolean
  created_at: string
}

export interface Notifier {
  id: number
  name: string
  type: NotifierType
  url: string
  has_token: boolean
  enabled: boolean
  events: string[]
  last_error: string
}

export interface DashboardStats {
  instances_total: number
  last_sync_at: string | null
  instances_synced: number
  managed_sections: number
  versions_total: number
  instances_online: number
  instances_unreachable: number
  instances_disabled: number
  rules_total: number
  rules_allow: number
  rules_block: number
  filter_lists_total: number
  filter_lists_enabled: number
  pending_jobs: number
  failed_jobs: number
  recent_drift: number
  querylog_buffered: number
}

export interface ReconcileReport {
  instance_id: number
  instance_name: string
  checked: boolean
  error: string
  corrected: boolean
  differences: { payload_kind: string; summary: string; details: Record<string, unknown> }[]
}

export interface ImportResult {
  instance: string
  rules_imported: number
  rules_skipped: number
  filter_lists_imported: number
  sections_imported: string[]
  sections_unsupported: string[]
  replaced: boolean
}

export interface SyncResult {
  instances: number
  failed: Record<string, string>
}

export interface ConnectionResult {
  ok: boolean
  version: string
  error: string
}

export interface ConfigSection {
  name: string
  title: string
  description: string
  notes: string
  managed: boolean
  has_data: boolean
  keys: string[]
  data: Record<string, unknown>
  /** Non-empty when the section is managed but cannot safely be pushed. */
  skipped_reason: string
  updated_at: string
}

export interface Version {
  id: number
  label: string
  author: string
  kind: string
  summary: string
  created_at: string
}

export interface VersionDiff {
  from_id: number
  to_id: number | null
  to_label: string
  summary: string
  changes: {
    rules: { added: string[]; removed: string[]; changed: { key: string }[] }
    filter_lists: { added: string[]; removed: string[]; changed: { key: string }[] }
    sections: Record<
      string,
      {
        keys: Record<string, { before: unknown; after: unknown }>
        managed?: { before: boolean; after: boolean }
      }
    >
    empty: boolean
  }
}

export interface VersionRestoreResult {
  version_id: number
  rules: number
  filter_lists: number
  sections: number
  pushed: boolean
}

export interface HubSettings {
  reconcile_enabled: boolean
  reconcile_interval: number
  retry_interval: number
  querylog_enabled: boolean
  querylog_poll_interval: number
  querylog_buffer_size: number
  http_timeout: number
  /** Accepted [min, max] per field, so the form can bound its inputs. */
  limits: Record<string, [number, number]>
}
