"""Pydantic v2 request and response schemas for LegacyIQ Wave 1 APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class OrganizationCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=120, pattern=r"^[a-z0-9-]+$")
    owner_email: str = Field(default="architect@legacyiq.local", max_length=320)
    owner_name: str = Field(default="Lead Architect", max_length=255)
    plan_tier: str = Field(default="ENTERPRISE", max_length=64)


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    status: str
    plan_tier: str
    created_at: datetime


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    is_active: bool


class MembershipCreateRequest(BaseModel):
    email: str = Field(..., max_length=320)
    display_name: str = Field(..., min_length=1, max_length=255)
    role_code: str = Field(default="ARCHITECT", pattern=r"^(ORG_OWNER|ARCHITECT|REVIEWER|VIEWER)$")


class OrganizationMembershipResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    user_display_name: str
    role_id: uuid.UUID
    role_code: str
    status: str


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=120, pattern=r"^[a-z0-9-]+$")
    description: str | None = None


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    slug: str
    name: str
    description: str | None
    is_archived: bool
    created_at: datetime


class ProjectCreateRequest(BaseModel):
    workspace_id: uuid.UUID
    name: str = Field(..., min_length=2, max_length=255)
    key: str = Field(..., min_length=2, max_length=32, pattern=r"^[A-Z0-9_-]+$")
    description: str | None = None
    default_retention_days: int = Field(default=365, ge=1, le=3650)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    key: str
    name: str
    description: str | None
    status: str
    default_retention_days: int
    created_at: datetime


class ProjectMembershipCreateRequest(BaseModel):
    user_id: uuid.UUID
    role_code: str = Field(default="ARCHITECT", pattern=r"^(ORG_OWNER|ARCHITECT|REVIEWER|VIEWER)$")


class ApplicationCreateRequest(BaseModel):
    project_id: uuid.UUID
    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=120, pattern=r"^[a-z0-9-]+$")
    primary_language: str | None = None
    criticality_tier: str = Field(default="TIER_1", pattern=r"^TIER_[1234]$")


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    project_id: uuid.UUID
    slug: str
    name: str
    primary_language: str | None
    criticality_tier: str
    created_at: datetime


class RepositoryCreateRequest(BaseModel):
    project_id: uuid.UUID
    application_id: uuid.UUID | None = None
    name: str = Field(..., min_length=2, max_length=255)
    default_branch: str = Field(default="main", max_length=255)
    clone_url: str | None = None


class RepositoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    project_id: uuid.UUID
    application_id: uuid.UUID | None
    name: str
    default_branch: str
    clone_url: str | None
    is_active: bool
    created_at: datetime


class SnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    project_id: uuid.UUID
    repository_id: uuid.UUID
    snapshot_label: str | None
    source_type: str
    tree_hash: str
    file_count: int
    total_bytes: int
    status: str
    retention_class: str
    legal_hold: bool
    created_at: datetime


class IngestionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    project_id: uuid.UUID
    repository_id: uuid.UUID
    snapshot_id: uuid.UUID | None
    status: str
    stage: str
    progress_pct: int
    files_processed: int
    bytes_processed: int
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class ZipUploadResponse(BaseModel):
    repository_id: uuid.UUID
    snapshot_id: uuid.UUID
    ingestion_job_id: uuid.UUID
    analysis_run_id: uuid.UUID | None
    tree_hash: str
    is_duplicate_snapshot: bool
    files_processed: int
    total_bytes: int
    chunks_indexed: int


class CodeFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_run_id: uuid.UUID
    module_id: uuid.UUID | None
    artifact_version_id: uuid.UUID
    relative_path: str
    language: str
    loc_total: int
    loc_code: int
    parse_status: str
    parser_version: str


class CodeSymbolResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_run_id: uuid.UUID
    code_file_id: uuid.UUID
    parent_symbol_id: uuid.UUID | None
    qualified_name: str
    symbol_name: str
    symbol_kind: str
    visibility: str
    signature_text: str | None
    docstring_text: str | None
    body_ast_hash: str
    start_line: int
    end_line: int
    cyclomatic_complexity: int | None


class CodeImportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_run_id: uuid.UUID
    source_file_id: uuid.UUID
    resolved_file_id: uuid.UUID | None
    imported_module_name: str
    imported_symbol_name: str | None
    is_relative: bool
    is_external: bool
    line_number: int


class CodeCallEdgeResponse(BaseModel):
    id: uuid.UUID
    analysis_run_id: uuid.UUID
    caller_symbol_id: uuid.UUID
    caller_qualified_name: str
    callee_symbol_id: uuid.UUID
    callee_qualified_name: str
    call_site_line: int
    resolution_confidence: float
    is_dynamic_dispatch: bool


class CodeTypeHierarchyResponse(BaseModel):
    id: uuid.UUID
    analysis_run_id: uuid.UUID
    child_symbol_id: uuid.UUID
    child_qualified_name: str
    parent_symbol_id: uuid.UUID
    parent_qualified_name: str
    relationship_kind: str


class CodeReferenceResponse(BaseModel):
    id: uuid.UUID
    analysis_run_id: uuid.UUID
    source_file_id: uuid.UUID
    source_relative_path: str
    target_symbol_id: uuid.UUID
    target_qualified_name: str
    reference_kind: str
    line_number: int
    col_number: int


class CodeSummaryResponse(BaseModel):
    project_id: uuid.UUID
    snapshot_id: uuid.UUID | None
    analysis_run_id: uuid.UUID | None
    total_modules: int
    total_files: int
    total_loc: int
    total_symbols: int
    total_imports: int
    total_call_edges: int
    total_type_hierarchies: int
    total_references: int
    language_breakdown: dict[str, int]
    symbol_kind_breakdown: dict[str, int]


class HybridSearchRequest(BaseModel):
    project_id: uuid.UUID
    snapshot_id: uuid.UUID
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)
    language: str | None = None


class HybridSearchHitResponse(BaseModel):
    chunk_id: uuid.UUID
    artifact_id: uuid.UUID
    artifact_version_id: uuid.UUID
    relative_path: str
    detected_language: str | None
    code_symbol_id: uuid.UUID | None
    symbol_qualified_name: str | None
    symbol_kind: str | None
    chunk_strategy: str
    start_line: int
    end_line: int
    chunk_text: str
    chunk_sha256: str
    rrf_score: float
    vector_score: float | None
    lexical_score: float | None


class HybridSearchResponse(BaseModel):
    project_id: uuid.UUID
    snapshot_id: uuid.UUID
    query: str
    total_hits: int
    hits: list[HybridSearchHitResponse]


class BootstrapContextResponse(BaseModel):
    tenant_id: uuid.UUID
    organization_name: str
    organization_slug: str
    user_id: uuid.UUID
    user_email: str
    user_display_name: str
    role_code: str
    workspace_id: uuid.UUID
    workspace_name: str
    project_id: uuid.UUID
    project_key: str
    project_name: str
    default_repository_id: uuid.UUID
    default_repository_name: str
    latest_snapshot_id: uuid.UUID | None

