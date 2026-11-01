"""Hybrid Reciprocal Rank Fusion (RRF) search endpoints (Domain J)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_context
from app.core.security import (
    SecurityViolationError,
    TenantContext,
    verify_project_access,
)
from app.schemas.platform import (
    HybridSearchHitResponse,
    HybridSearchRequest,
    HybridSearchResponse,
)
from app.services.retrieval_service import RetrievalService

router = APIRouter()
retrieval_service = RetrievalService()


@router.post(
    "/search/hybrid",
    response_model=HybridSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute tenant- and snapshot-scoped Hybrid RRF search (pgvector cosine + PostgreSQL FTS)",
)
def post_hybrid_search(
    payload: HybridSearchRequest,
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> HybridSearchResponse:
    db, ctx = deps
    try:
        verify_project_access(
            db,
            tenant_context=ctx,
            project_id=payload.project_id,
            required_permission="code:search",
        )
    except SecurityViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    hits = retrieval_service.hybrid_search(
        db,
        tenant_id=ctx.tenant_id,
        project_id=payload.project_id,
        snapshot_id=payload.snapshot_id,
        query_text=payload.query,
        limit=payload.limit,
        language_filter=payload.language,
    )
    return HybridSearchResponse(
        project_id=payload.project_id,
        snapshot_id=payload.snapshot_id,
        query=payload.query,
        total_hits=len(hits),
        hits=[
            HybridSearchHitResponse(
                chunk_id=h.chunk_id,
                artifact_id=h.artifact_id,
                artifact_version_id=h.artifact_version_id,
                relative_path=h.relative_path,
                detected_language=h.detected_language,
                code_symbol_id=h.code_symbol_id,
                symbol_qualified_name=h.symbol_qualified_name,
                symbol_kind=h.symbol_kind,
                chunk_strategy=h.chunk_strategy,
                start_line=h.start_line,
                end_line=h.end_line,
                chunk_text=h.chunk_text,
                chunk_sha256=h.chunk_sha256,
                rrf_score=h.rrf_score,
                vector_score=h.vector_score,
                lexical_score=h.lexical_score,
            )
            for h in hits
        ],
    )


@router.get(
    "/search/hybrid",
    response_model=HybridSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute tenant- and snapshot-scoped Hybrid RRF search via GET query parameters",
)
def get_hybrid_search(
    project_id: uuid.UUID = Query(...),
    snapshot_id: uuid.UUID = Query(...),
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(default=10, ge=1, le=50),
    language: str | None = Query(default=None),
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> HybridSearchResponse:
    return post_hybrid_search(
        HybridSearchRequest(
            project_id=project_id,
            snapshot_id=snapshot_id,
            query=q,
            limit=limit,
            language=language,
        ),
        deps=deps,
    )

