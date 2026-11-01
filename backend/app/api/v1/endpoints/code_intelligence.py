"""Deterministic Code Intelligence discovery endpoints (Domain D)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.api.deps import get_tenant_context
from app.core.security import (
    SecurityViolationError,
    TenantContext,
    verify_project_access,
)
from app.models.code_intelligence import (
    AnalysisRun,
    CodeCallEdge,
    CodeFile,
    CodeImport,
    CodeModule,
    CodeSymbol,
    CodeSymbolReference,
    CodeTypeHierarchy,
)
from app.models.projects import Application
from app.schemas.platform import (
    CodeCallEdgeResponse,
    CodeFileResponse,
    CodeImportResponse,
    CodeReferenceResponse,
    CodeSummaryResponse,
    CodeSymbolResponse,
    CodeTypeHierarchyResponse,
)

router = APIRouter()


def _resolve_active_run(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    snapshot_id: uuid.UUID | None = None,
) -> AnalysisRun | None:
    stmt = (
        select(AnalysisRun)
        .join(
            Application,
            (Application.tenant_id == AnalysisRun.tenant_id)
            & (Application.id == AnalysisRun.application_id),
        )
        .where(
            AnalysisRun.tenant_id == tenant_id,
            Application.project_id == project_id,
        )
    )
    if snapshot_id is not None:
        stmt = stmt.where(AnalysisRun.snapshot_id == snapshot_id)
    stmt = stmt.order_by(AnalysisRun.started_at.desc()).limit(1)
    return db.execute(stmt).scalar_one_or_none()


@router.get(
    "/code/summary",
    response_model=CodeSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get deterministic code intelligence metrics and breakdowns for a project/snapshot",
)
def get_code_summary(
    project_id: uuid.UUID = Query(...),
    snapshot_id: uuid.UUID | None = Query(default=None),
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> CodeSummaryResponse:
    db, ctx = deps
    try:
        verify_project_access(
            db,
            tenant_context=ctx,
            project_id=project_id,
            required_permission="project:read",
        )
    except SecurityViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    run = _resolve_active_run(
        db, tenant_id=ctx.tenant_id, project_id=project_id, snapshot_id=snapshot_id
    )
    if run is None:
        return CodeSummaryResponse(
            project_id=project_id,
            snapshot_id=snapshot_id,
            analysis_run_id=None,
            total_modules=0,
            total_files=0,
            total_loc=0,
            total_symbols=0,
            total_imports=0,
            total_call_edges=0,
            total_type_hierarchies=0,
            total_references=0,
            language_breakdown={},
            symbol_kind_breakdown={},
        )

    snap_id = run.snapshot_id

    total_modules = (
        db.execute(
            select(func.count(CodeModule.id)).where(
                CodeModule.tenant_id == ctx.tenant_id,
                CodeModule.snapshot_id == snap_id,
            )
        ).scalar_one()
        or 0
    )

    file_rows = db.execute(
        select(
            CodeFile.language,
            func.count(CodeFile.id),
            func.coalesce(func.sum(CodeFile.loc_code), 0),
        )
        .where(
            CodeFile.tenant_id == ctx.tenant_id,
            CodeFile.snapshot_id == snap_id,
        )
        .group_by(CodeFile.language)
    ).all()

    lang_breakdown = {row[0]: int(row[1]) for row in file_rows}
    total_files = sum(lang_breakdown.values())
    total_loc = sum(int(row[2]) for row in file_rows)

    sym_rows = db.execute(
        select(CodeSymbol.symbol_kind, func.count(CodeSymbol.id))
        .where(
            CodeSymbol.tenant_id == ctx.tenant_id,
            CodeSymbol.snapshot_id == snap_id,
        )
        .group_by(CodeSymbol.symbol_kind)
    ).all()
    sym_breakdown = {row[0]: int(row[1]) for row in sym_rows}
    total_symbols = sum(sym_breakdown.values())

    total_imports = (
        db.execute(
            select(func.count(CodeImport.id)).where(
                CodeImport.tenant_id == ctx.tenant_id,
                CodeImport.snapshot_id == snap_id,
            )
        ).scalar_one()
        or 0
    )

    total_call_edges = (
        db.execute(
            select(func.count(CodeCallEdge.id)).where(
                CodeCallEdge.tenant_id == ctx.tenant_id,
                CodeCallEdge.snapshot_id == snap_id,
            )
        ).scalar_one()
        or 0
    )

    total_hierarchies = (
        db.execute(
            select(func.count(CodeTypeHierarchy.id)).where(
                CodeTypeHierarchy.tenant_id == ctx.tenant_id,
                CodeTypeHierarchy.snapshot_id == snap_id,
            )
        ).scalar_one()
        or 0
    )

    total_refs = (
        db.execute(
            select(func.count(CodeSymbolReference.id)).where(
                CodeSymbolReference.tenant_id == ctx.tenant_id,
                CodeSymbolReference.snapshot_id == snap_id,
            )
        ).scalar_one()
        or 0
    )

    return CodeSummaryResponse(
        project_id=project_id,
        snapshot_id=snap_id,
        analysis_run_id=run.id,
        total_modules=int(total_modules),
        total_files=total_files,
        total_loc=total_loc,
        total_symbols=total_symbols,
        total_imports=int(total_imports),
        total_call_edges=int(total_call_edges),
        total_type_hierarchies=int(total_hierarchies),
        total_references=int(total_refs),
        language_breakdown=lang_breakdown,
        symbol_kind_breakdown=sym_breakdown,
    )


@router.get(
    "/code/files",
    response_model=list[CodeFileResponse],
    status_code=status.HTTP_200_OK,
    summary="List parsed code files for a project/snapshot",
)
def list_code_files(
    project_id: uuid.UUID = Query(...),
    snapshot_id: uuid.UUID | None = Query(default=None),
    language: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> list[CodeFileResponse]:
    db, ctx = deps
    try:
        verify_project_access(
            db,
            tenant_context=ctx,
            project_id=project_id,
            required_permission="project:read",
        )
    except SecurityViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    run = _resolve_active_run(
        db, tenant_id=ctx.tenant_id, project_id=project_id, snapshot_id=snapshot_id
    )
    if run is None:
        return []

    stmt = select(CodeFile).where(
        CodeFile.tenant_id == ctx.tenant_id,
        CodeFile.snapshot_id == run.snapshot_id,
    )
    if language:
        stmt = stmt.where(CodeFile.language == language)
    rows = (
        db.execute(stmt.order_by(CodeFile.relative_path.asc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return [
        CodeFileResponse(
            id=f.id,
            analysis_run_id=f.analysis_run_id,
            module_id=f.module_id,
            artifact_version_id=f.artifact_version_id,
            relative_path=f.relative_path,
            language=f.language,
            loc_total=f.loc_code + f.loc_comment,
            loc_code=f.loc_code,
            parse_status=f.parse_status,
            parser_version=f.parser_name,
        )
        for f in rows
    ]


@router.get(
    "/code/symbols",
    response_model=list[CodeSymbolResponse],
    status_code=status.HTTP_200_OK,
    summary="List extracted AST symbols for a project/snapshot",
)
def list_code_symbols(
    project_id: uuid.UUID = Query(...),
    snapshot_id: uuid.UUID | None = Query(default=None),
    code_file_id: uuid.UUID | None = Query(default=None),
    symbol_kind: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> list[CodeSymbolResponse]:
    db, ctx = deps
    try:
        verify_project_access(
            db,
            tenant_context=ctx,
            project_id=project_id,
            required_permission="project:read",
        )
    except SecurityViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    run = _resolve_active_run(
        db, tenant_id=ctx.tenant_id, project_id=project_id, snapshot_id=snapshot_id
    )
    if run is None:
        return []

    stmt = select(CodeSymbol).where(
        CodeSymbol.tenant_id == ctx.tenant_id,
        CodeSymbol.snapshot_id == run.snapshot_id,
    )
    if code_file_id is not None:
        stmt = stmt.where(CodeSymbol.code_file_id == code_file_id)
    if symbol_kind:
        stmt = stmt.where(CodeSymbol.symbol_kind == symbol_kind.upper())
    if q:
        stmt = stmt.where(CodeSymbol.qualified_name.ilike(f"%{q}%"))
    rows = (
        db.execute(stmt.order_by(CodeSymbol.qualified_name.asc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return [
        CodeSymbolResponse(
            id=s.id,
            analysis_run_id=run.id,
            code_file_id=s.code_file_id,
            parent_symbol_id=s.parent_symbol_id,
            qualified_name=s.qualified_name,
            symbol_name=s.name,
            symbol_kind=s.symbol_kind,
            visibility=s.visibility or "PUBLIC",
            signature_text=s.signature_text,
            docstring_text=(s.modifiers_and_annotations or {}).get("docstring"),
            body_ast_hash=s.body_ast_hash or "",
            start_line=s.start_line,
            end_line=s.end_line,
            cyclomatic_complexity=s.cyclomatic_complexity,
        )
        for s in rows
    ]


@router.get(
    "/code/imports",
    response_model=list[CodeImportResponse],
    status_code=status.HTTP_200_OK,
    summary="List extracted module imports for a project/snapshot",
)
def list_code_imports(
    project_id: uuid.UUID = Query(...),
    snapshot_id: uuid.UUID | None = Query(default=None),
    source_file_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> list[CodeImportResponse]:
    db, ctx = deps
    try:
        verify_project_access(
            db,
            tenant_context=ctx,
            project_id=project_id,
            required_permission="project:read",
        )
    except SecurityViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    run = _resolve_active_run(
        db, tenant_id=ctx.tenant_id, project_id=project_id, snapshot_id=snapshot_id
    )
    if run is None:
        return []

    stmt = select(CodeImport).where(
        CodeImport.tenant_id == ctx.tenant_id,
        CodeImport.snapshot_id == run.snapshot_id,
    )
    if source_file_id is not None:
        stmt = stmt.where(CodeImport.source_file_id == source_file_id)
    rows = db.execute(stmt.order_by(CodeImport.line_number.asc()).limit(limit)).scalars().all()
    return [
        CodeImportResponse(
            id=i.id,
            analysis_run_id=run.id,
            source_file_id=i.source_file_id,
            resolved_file_id=i.resolved_target_file_id,
            imported_module_name=i.imported_module_expr,
            imported_symbol_name=i.imported_symbol_name,
            is_relative=i.imported_module_expr.startswith("."),
            is_external=i.is_external_package,
            line_number=i.line_number,
        )
        for i in rows
    ]


@router.get(
    "/code/call-edges",
    response_model=list[CodeCallEdgeResponse],
    status_code=status.HTTP_200_OK,
    summary="List static symbol-to-symbol call graph edges for a project/snapshot",
)
def list_code_call_edges(
    project_id: uuid.UUID = Query(...),
    snapshot_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> list[CodeCallEdgeResponse]:
    db, ctx = deps
    try:
        verify_project_access(
            db,
            tenant_context=ctx,
            project_id=project_id,
            required_permission="project:read",
        )
    except SecurityViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    run = _resolve_active_run(
        db, tenant_id=ctx.tenant_id, project_id=project_id, snapshot_id=snapshot_id
    )
    if run is None:
        return []

    CallerSym = aliased(CodeSymbol)
    CalleeSym = aliased(CodeSymbol)
    rows = db.execute(
        select(CodeCallEdge, CallerSym.qualified_name, CalleeSym.qualified_name)
        .join(
            CallerSym,
            (CallerSym.tenant_id == CodeCallEdge.tenant_id)
            & (CallerSym.id == CodeCallEdge.caller_symbol_id),
        )
        .join(
            CalleeSym,
            (CalleeSym.tenant_id == CodeCallEdge.tenant_id)
            & (CalleeSym.id == CodeCallEdge.callee_symbol_id),
        )
        .where(
            CodeCallEdge.tenant_id == ctx.tenant_id,
            CodeCallEdge.snapshot_id == run.snapshot_id,
        )
        .order_by(CodeCallEdge.call_site_line.asc())
        .limit(limit)
    ).all()

    return [
        CodeCallEdgeResponse(
            id=edge.id,
            analysis_run_id=run.id,
            caller_symbol_id=edge.caller_symbol_id,
            caller_qualified_name=caller_qname,
            callee_symbol_id=edge.callee_symbol_id,  # type: ignore[arg-type]
            callee_qualified_name=callee_qname,
            call_site_line=edge.call_site_line,
            resolution_confidence=(
                0.95 if edge.resolution_certainty == "EXACT_AST" else 0.85
            ),
            is_dynamic_dispatch=(edge.resolution_certainty == "DYNAMIC_HEURISTIC"),
        )
        for edge, caller_qname, callee_qname in rows
    ]


@router.get(
    "/code/type-hierarchies",
    response_model=list[CodeTypeHierarchyResponse],
    status_code=status.HTTP_200_OK,
    summary="List class/interface inheritance and implementation hierarchies",
)
def list_code_type_hierarchies(
    project_id: uuid.UUID = Query(...),
    snapshot_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> list[CodeTypeHierarchyResponse]:
    db, ctx = deps
    try:
        verify_project_access(
            db,
            tenant_context=ctx,
            project_id=project_id,
            required_permission="project:read",
        )
    except SecurityViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    run = _resolve_active_run(
        db, tenant_id=ctx.tenant_id, project_id=project_id, snapshot_id=snapshot_id
    )
    if run is None:
        return []

    ChildSym = aliased(CodeSymbol)
    ParentSym = aliased(CodeSymbol)
    rows = db.execute(
        select(CodeTypeHierarchy, ChildSym.qualified_name, ParentSym.qualified_name)
        .join(
            ChildSym,
            (ChildSym.tenant_id == CodeTypeHierarchy.tenant_id)
            & (ChildSym.id == CodeTypeHierarchy.sub_symbol_id),
        )
        .join(
            ParentSym,
            (ParentSym.tenant_id == CodeTypeHierarchy.tenant_id)
            & (ParentSym.id == CodeTypeHierarchy.super_symbol_id),
        )
        .where(
            CodeTypeHierarchy.tenant_id == ctx.tenant_id,
            CodeTypeHierarchy.snapshot_id == run.snapshot_id,
        )
        .limit(limit)
    ).all()

    return [
        CodeTypeHierarchyResponse(
            id=th.id,
            analysis_run_id=run.id,
            child_symbol_id=th.sub_symbol_id,
            child_qualified_name=child_q,
            parent_symbol_id=th.super_symbol_id,  # type: ignore[arg-type]
            parent_qualified_name=parent_q,
            relationship_kind=th.relation_kind,
        )
        for th, child_q, parent_q in rows
    ]


@router.get(
    "/code/references",
    response_model=list[CodeReferenceResponse],
    status_code=status.HTTP_200_OK,
    summary="List cross-file symbol references",
)
def list_code_references(
    project_id: uuid.UUID = Query(...),
    snapshot_id: uuid.UUID | None = Query(default=None),
    target_symbol_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> list[CodeReferenceResponse]:
    db, ctx = deps
    try:
        verify_project_access(
            db,
            tenant_context=ctx,
            project_id=project_id,
            required_permission="project:read",
        )
    except SecurityViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    run = _resolve_active_run(
        db, tenant_id=ctx.tenant_id, project_id=project_id, snapshot_id=snapshot_id
    )
    if run is None:
        return []

    stmt = (
        select(CodeSymbolReference, CodeFile.relative_path, CodeSymbol.qualified_name)
        .join(
            CodeFile,
            (CodeFile.tenant_id == CodeSymbolReference.tenant_id)
            & (CodeFile.id == CodeSymbolReference.referencing_file_id),
        )
        .join(
            CodeSymbol,
            (CodeSymbol.tenant_id == CodeSymbolReference.tenant_id)
            & (CodeSymbol.id == CodeSymbolReference.referenced_symbol_id),
        )
        .where(
            CodeSymbolReference.tenant_id == ctx.tenant_id,
            CodeSymbolReference.snapshot_id == run.snapshot_id,
        )
    )
    if target_symbol_id is not None:
        stmt = stmt.where(CodeSymbolReference.referenced_symbol_id == target_symbol_id)
    rows = db.execute(stmt.order_by(CodeSymbolReference.line_number.asc()).limit(limit)).all()

    return [
        CodeReferenceResponse(
            id=ref.id,
            analysis_run_id=run.id,
            source_file_id=ref.referencing_file_id,
            source_relative_path=rel_path,
            target_symbol_id=ref.referenced_symbol_id,
            target_qualified_name=sym_qname,
            reference_kind=ref.reference_kind,
            line_number=ref.line_number,
            col_number=ref.column_number,
        )
        for ref, rel_path, sym_qname in rows
    ]
