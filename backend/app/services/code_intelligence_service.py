"""Deterministic Code Intelligence extraction and persistence service (Stage 4)."""

from __future__ import annotations

from datetime import datetime, timezone
import posixpath
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.parser_registry import (
    ExtractedSymbol,
    FileParseResult,
    default_parser_registry,
    detect_language_and_kind,
)
from app.integrations.storage import TenantObjectStorage
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
from app.models.ingestion import Artifact, ArtifactVersion, Repository, RepositorySnapshot
from app.models.projects import AnalysisScope


class CodeIntelligenceService:
    """
    Executes deterministic multi-language static analysis over an immutable
    `RepositorySnapshot` and populates all 7 Domain D code intelligence tables.
    """

    def __init__(self, storage: TenantObjectStorage | None = None) -> None:
        self.storage = storage or TenantObjectStorage()

    def ensure_default_analysis_scope(
        self, db: Session, *, tenant_id: uuid.UUID, application_id: uuid.UUID
    ) -> AnalysisScope:
        scope = db.execute(
            select(AnalysisScope).where(
                AnalysisScope.tenant_id == tenant_id,
                AnalysisScope.application_id == application_id,
            )
        ).scalars().first()
        if scope is None:
            scope = AnalysisScope(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                application_id=application_id,
                name="default-scope",
                is_default=True,
            )
            db.add(scope)
            db.flush()
        return scope

    def run_static_analysis(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        triggered_by_user_id: uuid.UUID | None = None,
        snapshot_artifacts: list[tuple[Artifact, ArtifactVersion]] | None = None,
    ) -> AnalysisRun:
        snapshot = db.execute(
            select(RepositorySnapshot).where(
                RepositorySnapshot.tenant_id == tenant_id,
                RepositorySnapshot.id == snapshot_id,
            )
        ).scalar_one_or_none()
        if snapshot is None:
            raise ValueError(f"RepositorySnapshot {snapshot_id} not found for tenant {tenant_id}.")

        repo = db.execute(
            select(Repository).where(
                Repository.tenant_id == tenant_id,
                Repository.id == snapshot.repository_id,
            )
        ).scalar_one()

        scope = self.ensure_default_analysis_scope(
            db, tenant_id=tenant_id, application_id=repo.application_id
        )

        # Determine next run_number for this application
        existing_runs = db.execute(
            select(AnalysisRun.run_number).where(
                AnalysisRun.tenant_id == tenant_id,
                AnalysisRun.application_id == repo.application_id,
            )
        ).scalars().all()
        next_run_number = (max(existing_runs) + 1) if existing_runs else 1

        now = datetime.now(timezone.utc)
        analysis_run = AnalysisRun(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            application_id=repo.application_id,
            snapshot_id=snapshot.id,
            analysis_scope_id=scope.id,
            triggered_by_user_id=triggered_by_user_id,
            run_number=next_run_number,
            run_mode="FULL_DISCOVERY",
            status="RUNNING",
            pipeline_versions_manifest={
                "parser_engine": "wave1-static-1.0",
                "languages": ["python", "java", "javascript", "typescript", "php"],
            },
            started_at=now,
        )
        db.add(analysis_run)
        db.flush()

        if snapshot_artifacts is None:
            rows = db.execute(
                select(Artifact, ArtifactVersion)
                .join(
                    ArtifactVersion,
                    (ArtifactVersion.tenant_id == Artifact.tenant_id)
                    & (ArtifactVersion.artifact_id == Artifact.id),
                )
                .where(
                    Artifact.tenant_id == tenant_id,
                    Artifact.repository_id == repo.id,
                )
                .order_by(Artifact.canonical_path.asc())
            ).all()
            snapshot_artifacts = [(r[0], r[1]) for r in rows]

        parsed_files: list[tuple[Artifact, ArtifactVersion, FileParseResult]] = []
        modules_by_key: dict[tuple[str, str], CodeModule] = {}

        for artifact, version in snapshot_artifacts:
            lang, _ = detect_language_and_kind(artifact.canonical_path)
            if not default_parser_registry.supports_language(lang):
                continue
            assert lang is not None
            source_text = self.storage.get_blob_text(tenant_id, version.content_sha256)
            parse_res = default_parser_registry.parse_file(
                artifact.canonical_path, lang, source_text
            )
            parsed_files.append((artifact, version, parse_res))

            mod_key = (lang, parse_res.module_name)
            if mod_key not in modules_by_key:
                mod = CodeModule(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    snapshot_id=snapshot.id,
                    language=lang,
                    module_kind="PACKAGE" if lang in ("python", "java", "php") else "DIRECTORY",
                    qualified_name=parse_res.module_name,
                    parent_module_id=None,
                )
                db.add(mod)
                modules_by_key[mod_key] = mod

        db.flush()

        # Persist CodeFiles and CodeSymbols
        files_by_rel_path: dict[str, CodeFile] = {}
        symbols_by_short_name: dict[str, list[CodeSymbol]] = {}
        pending_file_records: list[
            tuple[CodeFile, FileParseResult, list[tuple[ExtractedSymbol, CodeSymbol]]]
        ] = []

        for artifact, version, parse_res in parsed_files:
            mod = modules_by_key[(parse_res.language, parse_res.module_name)]
            loc_comment = max(0, parse_res.loc_total - parse_res.loc_code)
            code_file = CodeFile(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                snapshot_id=snapshot.id,
                artifact_version_id=version.id,
                module_id=mod.id,
                analysis_run_id=analysis_run.id,
                relative_path=artifact.canonical_path,
                language=parse_res.language,
                parser_name=parse_res.parser_version,
                parse_status=parse_res.parse_status,
                loc_code=parse_res.loc_code,
                loc_comment=loc_comment,
                ast_metrics={
                    "loc_total": parse_res.loc_total,
                    "symbol_count": len(parse_res.symbols),
                    "import_count": len(parse_res.imports),
                },
            )
            db.add(code_file)
            files_by_rel_path[artifact.canonical_path] = code_file

            file_sym_pairs: list[tuple[ExtractedSymbol, CodeSymbol]] = []
            local_qname_map: dict[str, CodeSymbol] = {}

            for ext_sym in parse_res.symbols:
                parent_id = None
                if (
                    ext_sym.parent_qualified_name
                    and ext_sym.parent_qualified_name in local_qname_map
                ):
                    parent_id = local_qname_map[ext_sym.parent_qualified_name].id

                code_sym = CodeSymbol(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    snapshot_id=snapshot.id,
                    code_file_id=code_file.id,
                    parent_symbol_id=parent_id,
                    symbol_kind=ext_sym.symbol_kind,
                    name=ext_sym.symbol_name,
                    qualified_name=ext_sym.qualified_name,
                    signature_text=ext_sym.signature_text,
                    visibility=ext_sym.visibility,
                    start_line=ext_sym.start_line,
                    end_line=max(ext_sym.end_line, ext_sym.start_line),
                    start_column=ext_sym.start_col,
                    end_column=ext_sym.end_col,
                    cyclomatic_complexity=ext_sym.cyclomatic_complexity,
                    cognitive_complexity=ext_sym.cyclomatic_complexity,
                    body_ast_hash=ext_sym.body_ast_hash,
                    modifiers_and_annotations=(
                        {"docstring": ext_sym.docstring_text}
                        if ext_sym.docstring_text
                        else {}
                    ),
                )
                db.add(code_sym)
                local_qname_map[ext_sym.qualified_name] = code_sym
                symbols_by_short_name.setdefault(ext_sym.symbol_name, []).append(code_sym)
                file_sym_pairs.append((ext_sym, code_sym))

            pending_file_records.append((code_file, parse_res, file_sym_pairs))

        db.flush()

        # Second pass: resolve CodeImports, CodeCallEdges, CodeTypeHierarchies, CodeSymbolReferences
        seen_call_edges: set[tuple[uuid.UUID, uuid.UUID, int]] = set()
        seen_hierarchies: set[tuple[uuid.UUID, uuid.UUID, str]] = set()

        for code_file, parse_res, file_sym_pairs in pending_file_records:
            # 1. Imports
            for imp in parse_res.imports:
                resolved_file_id = self._resolve_import_target(
                    code_file.relative_path,
                    imp.imported_module_name,
                    files_by_rel_path,
                )
                is_ext = resolved_file_id is None and imp.is_external
                db.add(
                    CodeImport(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        snapshot_id=snapshot.id,
                        source_file_id=code_file.id,
                        resolved_target_file_id=resolved_file_id,
                        imported_module_expr=imp.imported_module_name,
                        imported_symbol_name=imp.imported_symbol_name,
                        alias_name=None,
                        is_external_package=is_ext,
                        line_number=imp.line_number,
                    )
                )

            # 2. Type hierarchies and Call edges
            for ext_sym, code_sym in file_sym_pairs:
                for base_name, rel_kind in ext_sym.base_types:
                    short_base = base_name.split(".")[-1]
                    candidates = [
                        c
                        for c in symbols_by_short_name.get(short_base, [])
                        if c.symbol_kind in ("CLASS", "INTERFACE") and c.id != code_sym.id
                    ]
                    if candidates:
                        parent_sym = candidates[0]
                        h_key = (code_sym.id, parent_sym.id, rel_kind)
                        if h_key not in seen_hierarchies:
                            seen_hierarchies.add(h_key)
                            db.add(
                                CodeTypeHierarchy(
                                    id=uuid.uuid4(),
                                    tenant_id=tenant_id,
                                    snapshot_id=snapshot.id,
                                    sub_symbol_id=code_sym.id,
                                    super_symbol_id=parent_sym.id,
                                    unresolved_super_name=None,
                                    relation_kind=rel_kind,
                                )
                            )
                    else:
                        db.add(
                            CodeTypeHierarchy(
                                id=uuid.uuid4(),
                                tenant_id=tenant_id,
                                snapshot_id=snapshot.id,
                                sub_symbol_id=code_sym.id,
                                super_symbol_id=None,
                                unresolved_super_name=base_name,
                                relation_kind=rel_kind,
                            )
                        )

                for callee_name, call_line, is_dyn in ext_sym.calls_made:
                    candidates = [
                        c
                        for c in symbols_by_short_name.get(callee_name, [])
                        if c.symbol_kind in ("FUNCTION", "METHOD", "CLASS")
                        and c.id != code_sym.id
                    ]
                    if candidates:
                        same_file = [
                            c for c in candidates if c.code_file_id == code_file.id
                        ]
                        target_sym = same_file[0] if same_file else candidates[0]
                        edge_key = (code_sym.id, target_sym.id, call_line)
                        if edge_key not in seen_call_edges:
                            seen_call_edges.add(edge_key)
                            certainty = (
                                "EXACT_AST"
                                if same_file
                                else ("DYNAMIC_HEURISTIC" if is_dyn else "IMPORT_RESOLVED")
                            )
                            db.add(
                                CodeCallEdge(
                                    id=uuid.uuid4(),
                                    tenant_id=tenant_id,
                                    snapshot_id=snapshot.id,
                                    caller_symbol_id=code_sym.id,
                                    callee_symbol_id=target_sym.id,
                                    unresolved_callee_expr=None,
                                    resolution_certainty=certainty,
                                    call_site_line=call_line,
                                    call_site_column=0,
                                )
                            )

            # 3. Symbol references
            for ref in parse_res.references:
                candidates = symbols_by_short_name.get(ref.target_symbol_name, [])
                if candidates:
                    same_file = [c for c in candidates if c.code_file_id == code_file.id]
                    target_sym = same_file[0] if same_file else candidates[0]
                    db.add(
                        CodeSymbolReference(
                            id=uuid.uuid4(),
                            tenant_id=tenant_id,
                            snapshot_id=snapshot.id,
                            referencing_file_id=code_file.id,
                            enclosing_symbol_id=None,
                            referenced_symbol_id=target_sym.id,
                            reference_kind=ref.reference_kind,
                            line_number=ref.line_number,
                            column_number=ref.col_number,
                        )
                    )

        analysis_run.status = "COMPLETED"
        analysis_run.completed_at = datetime.now(timezone.utc)
        db.flush()
        return analysis_run

    @staticmethod
    def _resolve_import_target(
        source_rel_path: str,
        imported_module_name: str,
        files_by_rel_path: dict[str, CodeFile],
    ) -> uuid.UUID | None:
        clean_mod = imported_module_name.lstrip("./").replace(".", "/")
        source_dir = posixpath.dirname(source_rel_path)

        candidates = [
            f"{clean_mod}.py",
            f"{clean_mod}/__init__.py",
            f"{clean_mod}.ts",
            f"{clean_mod}.tsx",
            f"{clean_mod}.js",
            f"{clean_mod}.jsx",
            f"{clean_mod}.java",
            f"{clean_mod}.php",
        ]
        if source_dir:
            rel_base = posixpath.normpath(
                f"{source_dir}/{imported_module_name.lstrip('./')}"
            )
            candidates.extend(
                [
                    f"{rel_base}.py",
                    f"{rel_base}.ts",
                    f"{rel_base}.tsx",
                    f"{rel_base}.js",
                    f"{rel_base}.jsx",
                    f"{rel_base}.php",
                ]
            )
        for cand in candidates:
            if cand in files_by_rel_path:
                return files_by_rel_path[cand].id
        for path_key, cf in files_by_rel_path.items():
            no_ext = posixpath.splitext(path_key)[0]
            if no_ext.endswith(clean_mod) and clean_mod:
                return cf.id
        return None
