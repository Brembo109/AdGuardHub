"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import ListKind, RuleKind, RuleOrigin


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# -- auth ------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1)


class SetupRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


class AuthState(BaseModel):
    authenticated: bool
    username: str | None = None
    setup_required: bool = False
    ephemeral_secret: bool = False


# -- instances -------------------------------------------------------------


class InstanceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=500)
    adapter: str = "adguard"
    username: str = ""
    password: str = ""
    verify_tls: bool = True
    enabled: bool = True

    @field_validator("base_url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return value


class ConnectionTest(BaseModel):
    """Probe credentials before an instance is saved (or with edited values)."""

    base_url: str = Field(min_length=1, max_length=500)
    adapter: str = "adguard"
    username: str = ""
    password: str = ""
    verify_tls: bool = True
    # Set when re-testing a saved instance whose password was left untouched.
    instance_id: int | None = None

    @field_validator("base_url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return value


class ConnectionResult(BaseModel):
    ok: bool
    version: str = ""
    error: str = ""


class InstanceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: str | None = None
    username: str | None = None
    # Omit to keep the stored password; send a new value to replace it.
    password: str | None = None
    verify_tls: bool | None = None
    enabled: bool | None = None

    @field_validator("base_url")
    @classmethod
    def _check_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return value


class InstanceOut(ORMModel):
    """Credentials are deliberately never serialised — only whether one is stored."""

    id: int
    name: str
    base_url: str
    adapter: str
    username: str
    has_password: bool
    verify_tls: bool
    enabled: bool
    status: str
    last_error: str
    last_seen_at: datetime | None
    last_synced_at: datetime | None
    created_at: datetime


class ImportRequest(BaseModel):
    replace: bool = True
    # Empty means every section the master exposes.
    sections: list[str] = Field(default_factory=list)
    push_after_import: bool = True


# -- rules -----------------------------------------------------------------


class RuleCreate(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    origin: RuleOrigin = RuleOrigin.custom
    enabled: bool = True
    comment: str = ""

    @field_validator("text")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Rule text must not be empty")
        return value


class RuleUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=1000)
    enabled: bool | None = None
    comment: str | None = None


class RuleOut(ORMModel):
    id: int
    text: str
    kind: RuleKind
    origin: RuleOrigin
    enabled: bool
    comment: str
    created_at: datetime
    updated_at: datetime


class DomainRuleRequest(BaseModel):
    """Query-log "Unblock"/"Block" action — the hub builds the AdGuard rule itself."""

    domain: str = Field(min_length=1, max_length=253)
    comment: str = ""

    @field_validator("domain")
    @classmethod
    def _clean(cls, value: str) -> str:
        value = value.strip().lower().rstrip(".")
        if not value or " " in value:
            raise ValueError("Not a valid domain")
        return value


class BulkRulesRequest(BaseModel):
    text: str = ""
    origin: RuleOrigin = RuleOrigin.custom


# -- filter lists ----------------------------------------------------------


class FilterListCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=1000)
    kind: ListKind = ListKind.blocklist
    enabled: bool = True

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith(("http://", "https://")):
            raise ValueError("Subscription URL must start with http:// or https://")
        return value


class FilterListUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    enabled: bool | None = None


class FilterListOut(ORMModel):
    id: int
    name: str
    url: str
    kind: ListKind
    enabled: bool
    created_at: datetime


# -- DNS settings ----------------------------------------------------------


class ConfigSectionOut(BaseModel):
    name: str
    title: str
    description: str
    notes: str
    managed: bool
    has_data: bool
    keys: list[str]
    data: dict[str, Any]
    # Non-empty when the section is managed but cannot safely be pushed.
    skipped_reason: str
    updated_at: datetime


class ConfigSectionUpdate(BaseModel):
    managed: bool | None = None
    data: dict[str, Any] | None = None


class VersionOut(BaseModel):
    id: int
    label: str
    author: str
    kind: str
    summary: str
    created_at: datetime


class VersionDetail(BaseModel):
    id: int
    label: str
    author: str
    kind: str
    created_at: datetime
    snapshot: dict[str, Any]


class VersionDiff(BaseModel):
    from_id: int
    to_id: int | None
    to_label: str
    summary: str
    changes: dict[str, Any]


class VersionRestoreResult(BaseModel):
    version_id: int
    rules: int
    filter_lists: int
    sections: int
    pushed: bool


# -- notifiers -------------------------------------------------------------


NotifierType = Literal["homeassistant", "discord", "gotify"]


class NotifierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: NotifierType
    url: str = Field(min_length=1, max_length=1000)
    token: str = ""
    enabled: bool = True
    events: list[str] = Field(default_factory=list)


class NotifierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    url: str | None = None
    token: str | None = None
    enabled: bool | None = None
    events: list[str] | None = None


class NotifierOut(BaseModel):
    id: int
    name: str
    type: str
    url: str
    has_token: bool
    enabled: bool
    events: list[str]
    last_error: str


# -- operations ------------------------------------------------------------


class PushJobOut(BaseModel):
    id: int
    instance_id: int
    instance_name: str
    payload_kind: str
    status: str
    attempts: int
    last_error: str
    reason: str
    updated_at: datetime


class DriftEventOut(ORMModel):
    id: int
    instance_id: int | None
    instance_name: str
    payload_kind: str
    summary: str
    details: str
    corrected: bool
    created_at: datetime


class SyncResult(BaseModel):
    instances: int
    failed: dict[str, str]


class DashboardStats(BaseModel):
    instances_total: int
    # Most recent successful push across all instances, and how many are current.
    last_sync_at: datetime | None = None
    instances_synced: int = 0
    managed_sections: int = 0
    versions_total: int = 0
    instances_online: int
    instances_unreachable: int
    instances_disabled: int
    rules_total: int
    rules_allow: int
    rules_block: int
    filter_lists_total: int
    filter_lists_enabled: int
    pending_jobs: int
    failed_jobs: int
    recent_drift: int
    querylog_buffered: int


class QueryLogEntryOut(BaseModel):
    instance: str
    time: str
    question: str
    question_type: str
    client: str
    answer_status: str
    blocked: bool
    rule: str
    elapsed_ms: float
    upstream: str


class ReconcileReportOut(BaseModel):
    instance_id: int
    instance_name: str
    checked: bool
    error: str
    corrected: bool
    differences: list[dict[str, Any]]
