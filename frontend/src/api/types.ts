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

export interface DnsSettings {
  managed: boolean
  upstream_dns: string
  bootstrap_dns: string
  fallback_dns: string
  upstream_mode: string
  dnssec_enabled: boolean
  protection_enabled: boolean
  updated_at: string
}

export interface DashboardStats {
  instances_total: number
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
  dns_imported: boolean
  replaced: boolean
}

export interface SyncResult {
  instances: number
  failed: Record<string, string>
}
