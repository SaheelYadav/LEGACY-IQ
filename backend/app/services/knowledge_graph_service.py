"""Wave 2.5 — Unified Knowledge Graph, Provenance (`EvidenceAnchor`), NetworkX Projection, Cycle-Safe Traversal & Human Review Service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import re
from typing import Any
import uuid

import networkx as nx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.analysis.database_intelligence import ExtractedDbAccessEdge
from app.models.code_intelligence import (
    AnalysisRun,
    CodeCallEdge,
    CodeFile,
    CodeImport,
    CodeModule,
    CodeSymbol,
    CodeTypeHierarchy,
)
from app.models.ingestion import Artifact, ArtifactVersion, RepositorySnapshot
from app.models.knowledge_graph import (
    EvidenceAnchor,
    Finding,
    FindingEvidenceLink,
    KnowledgeConflict,
    KnowledgeEntity,
    KnowledgeRelationship,
    ReviewHistory,
)
from app.models.technical_intelligence import (
    ApiEndpoint,
    ApiService,
    DbColumn,
    DbForeignKey,
    DbSchema,
    DbTable,
    DocSection,
    InfraResource,
)

SECRET_REDACT_RE = re.compile(
    r"(?i)(password|passwd|secret|api_key|token|private_key)\s*[:=]\s*['\"]?[^\s'\";,]{4,}['\"]?"
)


def redact_excerpt(raw_excerpt: str | None, max_chars: int = 2048) -> str:
    """Bound excerpt to <= 2048 characters and scrub inline secret literals."""
    if not raw_excerpt:
        return ""
    scrubbed = SECRET_REDACT_RE.sub(r"\1=[REDACTED]", raw_excerpt)
    return scrubbed[:max_chars]


@dataclass
class GraphBuildStats:
    entities_count: int
    relationships_count: int
    evidence_anchors_count: int
    deterministic_findings_count: int
    conflicts_count: int
    scc_cycles_count: int


class KnowledgeGraphService:
    """
    Constructs and queries the Unified Knowledge Graph (`knowledge_entities`, `knowledge_relationships`),
    immutable cryptographic `evidence_anchors`, `finding_evidence_links`, `findings`, `knowledge_conflicts`,
    and `review_history`.
    """

    def get_or_create_evidence_anchor(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        artifact_version_id: uuid.UUID,
        start_line: int,
        end_line: int,
        excerpt_text: str,
        locator_type: str = "LINE_RANGE",
        start_column: int = 0,
        end_column: int = 0,
        ast_or_json_path: str | None = None,
    ) -> EvidenceAnchor:
        """Create or return an immutable cryptographic `EvidenceAnchor` for an exact source span."""
        safe_start = max(1, int(start_line))
        safe_end = max(safe_start, int(end_line))
        bounded_excerpt = redact_excerpt(excerpt_text)
        snippet_sha256 = hashlib.sha256(
            bounded_excerpt.encode("utf-8", errors="replace")
        ).hexdigest()

        existing = db.execute(
            select(EvidenceAnchor).where(
                EvidenceAnchor.tenant_id == tenant_id,
                EvidenceAnchor.artifact_version_id == artifact_version_id,
                EvidenceAnchor.locator_type == locator_type,
                EvidenceAnchor.start_line == safe_start,
                EvidenceAnchor.end_line == safe_end,
                EvidenceAnchor.start_column == start_column,
                EvidenceAnchor.end_column == end_column,
                EvidenceAnchor.snippet_sha256 == snippet_sha256,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        anchor = EvidenceAnchor(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            artifact_version_id=artifact_version_id,
            snapshot_id=snapshot_id,
            locator_type=locator_type,
            start_line=safe_start,
            end_line=safe_end,
            start_column=start_column,
            end_column=end_column,
            ast_or_json_path=ast_or_json_path,
            snippet_sha256=snippet_sha256,
            excerpt_text=bounded_excerpt,
        )
        db.add(anchor)
        db.flush()
        return anchor

    def link_evidence(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        evidence_anchor_id: uuid.UUID,
        evidence_role: str,
        finding_id: uuid.UUID | None = None,
        knowledge_entity_id: uuid.UUID | None = None,
        knowledge_relationship_id: uuid.UUID | None = None,
        relevance_weight: Decimal = Decimal("1.0000"),
        rationale_note: str | None = None,
    ) -> FindingEvidenceLink:
        """Create a `FindingEvidenceLink` connecting an `EvidenceAnchor` to a graph node, edge, or finding."""
        link = FindingEvidenceLink(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            evidence_anchor_id=evidence_anchor_id,
            finding_id=finding_id,
            knowledge_entity_id=knowledge_entity_id,
            knowledge_relationship_id=knowledge_relationship_id,
            evidence_role=evidence_role,
            relevance_weight=relevance_weight,
            rationale_note=rationale_note,
        )
        db.add(link)
        db.flush()
        return link

    def _upsert_entity(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        application_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        analysis_run_id: uuid.UUID,
        entity_type: str,
        canonical_key: str,
        title: str,
        summary_description: str | None,
        origin_type: str = "DETERMINISTIC_PARSER",
        confidence_score: Decimal = Decimal("1.0000"),
        review_status: str = "DETERMINISTIC_FACT",
        source_symbol_id: uuid.UUID | None = None,
        source_db_table_id: uuid.UUID | None = None,
        source_api_endpoint_id: uuid.UUID | None = None,
        attributes_json: dict[str, Any] | None = None,
    ) -> KnowledgeEntity:
        existing = db.execute(
            select(KnowledgeEntity).where(
                KnowledgeEntity.tenant_id == tenant_id,
                KnowledgeEntity.application_id == application_id,
                KnowledgeEntity.snapshot_id == snapshot_id,
                KnowledgeEntity.analysis_run_id == analysis_run_id,
                KnowledgeEntity.entity_type == entity_type,
                KnowledgeEntity.canonical_key == canonical_key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            if attributes_json:
                merged = dict(existing.attributes_json or {})
                merged.update(attributes_json)
                existing.attributes_json = merged
            return existing

        entity = KnowledgeEntity(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            application_id=application_id,
            snapshot_id=snapshot_id,
            analysis_run_id=analysis_run_id,
            source_symbol_id=source_symbol_id,
            source_db_table_id=source_db_table_id,
            source_api_endpoint_id=source_api_endpoint_id,
            entity_type=entity_type,
            canonical_key=canonical_key,
            title=title[:255],
            summary_description=summary_description,
            origin_type=origin_type,
            confidence_score=confidence_score,
            review_status=review_status,
            attributes_json=attributes_json or {},
        )
        db.add(entity)
        db.flush()
        return entity

    def _upsert_relationship(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        application_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        analysis_run_id: uuid.UUID,
        source_entity_id: uuid.UUID,
        target_entity_id: uuid.UUID,
        relationship_type: str,
        origin_type: str = "DETERMINISTIC_PARSER",
        confidence_score: Decimal = Decimal("1.0000"),
        edge_weight: Decimal = Decimal("1.0000"),
        review_status: str = "DETERMINISTIC_FACT",
        edge_metadata: dict[str, Any] | None = None,
    ) -> KnowledgeRelationship:
        existing = db.execute(
            select(KnowledgeRelationship).where(
                KnowledgeRelationship.tenant_id == tenant_id,
                KnowledgeRelationship.analysis_run_id == analysis_run_id,
                KnowledgeRelationship.source_entity_id == source_entity_id,
                KnowledgeRelationship.target_entity_id == target_entity_id,
                KnowledgeRelationship.relationship_type == relationship_type,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        rel = KnowledgeRelationship(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            application_id=application_id,
            snapshot_id=snapshot_id,
            analysis_run_id=analysis_run_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relationship_type=relationship_type,
            origin_type=origin_type,
            confidence_score=confidence_score,
            edge_weight=edge_weight,
            review_status=review_status,
            edge_metadata=edge_metadata or {},
        )
        db.add(rel)
        db.flush()
        return rel

    def build_unified_knowledge_graph(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        application_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        analysis_run_id: uuid.UUID,
        db_access_edges: list[tuple[uuid.UUID, ExtractedDbAccessEdge]] | None = None,
        doc_mentions_by_section: dict[uuid.UUID, tuple[uuid.UUID, list[str]]] | None = None,
    ) -> GraphBuildStats:
        """
        Synthesize the Unified Knowledge Graph (`knowledge_entities`, `knowledge_relationships`),
        attach immutable `evidence_anchors` and `finding_evidence_links`, run NetworkX projections
        (PageRank, centrality, Strongly Connected Components), and emit deterministic `findings` and `knowledge_conflicts`.
        """
        anchors_created = 0

        # Load CodeFiles -> ArtifactVersions lookup
        code_files = (
            db.execute(
                select(CodeFile).where(
                    CodeFile.tenant_id == tenant_id,
                    CodeFile.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        code_file_by_id: dict[uuid.UUID, CodeFile] = {cf.id: cf for cf in code_files}
        default_av_id: uuid.UUID | None = (
            code_files[0].artifact_version_id if code_files else None
        )
        if default_av_id is None:
            first_av = db.execute(
                select(ArtifactVersion.id).where(ArtifactVersion.tenant_id == tenant_id).limit(1)
            ).scalar_one_or_none()
            default_av_id = first_av

        # 1. Create KnowledgeEntity nodes for CodeModules (`MODULE`)
        modules = (
            db.execute(
                select(CodeModule).where(
                    CodeModule.tenant_id == tenant_id,
                    CodeModule.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        module_entity_by_id: dict[uuid.UUID, KnowledgeEntity] = {}
        module_entity_by_qname: dict[str, KnowledgeEntity] = {}
        for mod in modules:
            cf_for_mod = next((cf for cf in code_files if cf.module_id == mod.id), None)
            ent = self._upsert_entity(
                db,
                tenant_id=tenant_id,
                application_id=application_id,
                snapshot_id=snapshot_id,
                analysis_run_id=analysis_run_id,
                entity_type="MODULE",
                canonical_key=f"module:{mod.language}:{mod.qualified_name}",
                title=mod.qualified_name,
                summary_description=f"{mod.language.capitalize()} {mod.module_kind.lower()} `{mod.qualified_name}`",
                attributes_json={"language": mod.language, "module_kind": mod.module_kind},
            )
            module_entity_by_id[mod.id] = ent
            module_entity_by_qname[mod.qualified_name] = ent

            if cf_for_mod is not None:
                anchor = self.get_or_create_evidence_anchor(
                    db,
                    tenant_id=tenant_id,
                    snapshot_id=snapshot_id,
                    artifact_version_id=cf_for_mod.artifact_version_id,
                    start_line=1,
                    end_line=max(1, min(20, cf_for_mod.loc_code + cf_for_mod.loc_comment)),
                    excerpt_text=f"Module {mod.qualified_name} ({mod.language}) in {cf_for_mod.relative_path}",
                    ast_or_json_path=f"Module[{mod.qualified_name}]",
                )
                anchors_created += 1
                self.link_evidence(
                    db,
                    tenant_id=tenant_id,
                    evidence_anchor_id=anchor.id,
                    knowledge_entity_id=ent.id,
                    evidence_role="PRIMARY_DEFINITION",
                    rationale_note=f"Primary source file defining module {mod.qualified_name}",
                )

        # 2. Create KnowledgeEntity nodes for CodeSymbols (`SYMBOL`) + `CONTAINS` edges from `MODULE`
        symbols = (
            db.execute(
                select(CodeSymbol).where(
                    CodeSymbol.tenant_id == tenant_id,
                    CodeSymbol.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        symbol_entity_by_id: dict[uuid.UUID, KnowledgeEntity] = {}
        symbol_entity_by_qname: dict[str, KnowledgeEntity] = {}
        symbol_entity_by_short_name: dict[str, KnowledgeEntity] = {}

        for sym in symbols:
            cf = code_file_by_id.get(sym.code_file_id)
            docstring = (sym.modifiers_and_annotations or {}).get("docstring")
            ent = self._upsert_entity(
                db,
                tenant_id=tenant_id,
                application_id=application_id,
                snapshot_id=snapshot_id,
                analysis_run_id=analysis_run_id,
                entity_type="SYMBOL",
                canonical_key=f"symbol:{sym.qualified_name}",
                title=sym.name,
                summary_description=docstring or sym.signature_text,
                source_symbol_id=sym.id,
                attributes_json={
                    "symbol_kind": sym.symbol_kind,
                    "visibility": sym.visibility,
                    "signature": sym.signature_text,
                    "cyclomatic_complexity": sym.cyclomatic_complexity,
                    "start_line": sym.start_line,
                    "end_line": sym.end_line,
                },
            )
            symbol_entity_by_id[sym.id] = ent
            symbol_entity_by_qname[sym.qualified_name] = ent
            symbol_entity_by_short_name[sym.name.lower()] = ent

            if cf is not None:
                anchor = self.get_or_create_evidence_anchor(
                    db,
                    tenant_id=tenant_id,
                    snapshot_id=snapshot_id,
                    artifact_version_id=cf.artifact_version_id,
                    start_line=sym.start_line,
                    end_line=sym.end_line,
                    excerpt_text=sym.signature_text or sym.qualified_name,
                    ast_or_json_path=f"{sym.symbol_kind}[{sym.qualified_name}]",
                )
                anchors_created += 1
                self.link_evidence(
                    db,
                    tenant_id=tenant_id,
                    evidence_anchor_id=anchor.id,
                    knowledge_entity_id=ent.id,
                    evidence_role="PRIMARY_DEFINITION",
                    rationale_note=f"AST definition of {sym.symbol_kind} {sym.qualified_name}",
                )

                mod_ent = module_entity_by_id.get(cf.module_id) if cf.module_id else None
                if mod_ent is not None:
                    self._upsert_relationship(
                        db,
                        tenant_id=tenant_id,
                        application_id=application_id,
                        snapshot_id=snapshot_id,
                        analysis_run_id=analysis_run_id,
                        source_entity_id=mod_ent.id,
                        target_entity_id=ent.id,
                        relationship_type="CONTAINS",
                        edge_metadata={"start_line": sym.start_line, "end_line": sym.end_line},
                    )

        # 3. Code Call Edges (`CALLS`), Type Hierarchies (`INHERITS_FROM` / `IMPLEMENTS_INTERFACE`), and Module `IMPORTS`
        call_edges = (
            db.execute(
                select(CodeCallEdge).where(
                    CodeCallEdge.tenant_id == tenant_id,
                    CodeCallEdge.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        for ce in call_edges:
            src_ent = symbol_entity_by_id.get(ce.caller_symbol_id)
            tgt_ent = symbol_entity_by_id.get(ce.callee_symbol_id) if ce.callee_symbol_id else None
            if src_ent and tgt_ent and src_ent.id != tgt_ent.id:
                self._upsert_relationship(
                    db,
                    tenant_id=tenant_id,
                    application_id=application_id,
                    snapshot_id=snapshot_id,
                    analysis_run_id=analysis_run_id,
                    source_entity_id=src_ent.id,
                    target_entity_id=tgt_ent.id,
                    relationship_type="CALLS",
                    edge_metadata={
                        "call_site_line": ce.call_site_line,
                        "resolution_certainty": ce.resolution_certainty,
                    },
                )

        type_hierarchies = (
            db.execute(
                select(CodeTypeHierarchy).where(
                    CodeTypeHierarchy.tenant_id == tenant_id,
                    CodeTypeHierarchy.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        for th in type_hierarchies:
            child_ent = symbol_entity_by_id.get(th.sub_symbol_id)
            parent_ent = (
                symbol_entity_by_id.get(th.super_symbol_id)
                if th.super_symbol_id
                else (
                    symbol_entity_by_short_name.get(th.unresolved_super_name.lower())
                    if th.unresolved_super_name
                    else None
                )
            )
            if child_ent and parent_ent and child_ent.id != parent_ent.id:
                rel_type = (
                    "IMPLEMENTS_INTERFACE"
                    if th.relation_kind == "IMPLEMENTS"
                    else "INHERITS_FROM"
                )
                self._upsert_relationship(
                    db,
                    tenant_id=tenant_id,
                    application_id=application_id,
                    snapshot_id=snapshot_id,
                    analysis_run_id=analysis_run_id,
                    source_entity_id=child_ent.id,
                    target_entity_id=parent_ent.id,
                    relationship_type=rel_type,
                )

        code_imports = (
            db.execute(
                select(CodeImport).where(
                    CodeImport.tenant_id == tenant_id,
                    CodeImport.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        for imp in code_imports:
            cf = code_file_by_id.get(imp.source_file_id)
            if not cf or not cf.module_id:
                continue
            src_mod_ent = module_entity_by_id.get(cf.module_id)
            tgt_cf = code_file_by_id.get(imp.resolved_target_file_id) if imp.resolved_target_file_id else None
            tgt_mod_ent = (
                module_entity_by_id.get(tgt_cf.module_id)
                if (tgt_cf and tgt_cf.module_id)
                else module_entity_by_qname.get(imp.imported_module_expr)
            )
            if src_mod_ent and tgt_mod_ent and src_mod_ent.id != tgt_mod_ent.id:
                self._upsert_relationship(
                    db,
                    tenant_id=tenant_id,
                    application_id=application_id,
                    snapshot_id=snapshot_id,
                    analysis_run_id=analysis_run_id,
                    source_entity_id=src_mod_ent.id,
                    target_entity_id=tgt_mod_ent.id,
                    relationship_type="IMPORTS",
                    edge_metadata={"line_number": imp.line_number},
                )

        # 4. Database Tables (`DB_TABLE`), Foreign Keys (`REFERENCES_TABLE_FK`), ORM `MAPS_TO_TABLE`, and `READS_TABLE` / `WRITES_TABLE`
        db_schemas = (
            db.execute(
                select(DbSchema).where(
                    DbSchema.tenant_id == tenant_id,
                    DbSchema.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        schema_by_id: dict[uuid.UUID, DbSchema] = {s.id: s for s in db_schemas}
        db_tables = (
            db.execute(
                select(DbTable).where(
                    DbTable.tenant_id == tenant_id,
                    DbTable.db_schema_id.in_([s.id for s in db_schemas]) if db_schemas else False,
                )
            )
            .scalars()
            .all()
            if db_schemas
            else []
        )
        db_table_entity_by_id: dict[uuid.UUID, KnowledgeEntity] = {}
        db_table_entity_by_name: dict[str, KnowledgeEntity] = {}

        for tbl in db_tables:
            sch = schema_by_id[tbl.db_schema_id]
            cols = (
                db.execute(
                    select(DbColumn)
                    .where(
                        DbColumn.tenant_id == tenant_id,
                        DbColumn.db_table_id == tbl.id,
                    )
                    .order_by(DbColumn.ordinal_position)
                )
                .scalars()
                .all()
            )
            pii_cols = [c.column_name for c in cols if c.is_pii_candidate]
            pk_cols = [c.column_name for c in cols if c.is_primary_key]
            ent = self._upsert_entity(
                db,
                tenant_id=tenant_id,
                application_id=application_id,
                snapshot_id=snapshot_id,
                analysis_run_id=analysis_run_id,
                entity_type="DB_TABLE",
                canonical_key=f"db_table:{sch.schema_name}.{tbl.table_name}",
                title=f"{sch.schema_name}.{tbl.table_name}",
                summary_description=tbl.comment_text
                or f"{tbl.table_kind} `{sch.schema_name}.{tbl.table_name}` ({len(cols)} columns)",
                source_db_table_id=tbl.id,
                attributes_json={
                    "db_engine": sch.db_engine,
                    "schema_name": sch.schema_name,
                    "table_name": tbl.table_name,
                    "table_kind": tbl.table_kind,
                    "column_count": len(cols),
                    "primary_keys": pk_cols,
                    "pii_columns": pii_cols,
                },
            )
            db_table_entity_by_id[tbl.id] = ent
            db_table_entity_by_name[tbl.table_name.lower()] = ent

            av_id = sch.source_artifact_version_id or default_av_id
            if av_id is not None:
                anchor = self.get_or_create_evidence_anchor(
                    db,
                    tenant_id=tenant_id,
                    snapshot_id=snapshot_id,
                    artifact_version_id=av_id,
                    start_line=1,
                    end_line=max(1, len(cols) + 2),
                    excerpt_text=f"TABLE {sch.schema_name}.{tbl.table_name} ({', '.join(c.column_name for c in cols[:15])})",
                    ast_or_json_path=f"DbTable[{sch.schema_name}.{tbl.table_name}]",
                )
                anchors_created += 1
                self.link_evidence(
                    db,
                    tenant_id=tenant_id,
                    evidence_anchor_id=anchor.id,
                    knowledge_entity_id=ent.id,
                    evidence_role="PRIMARY_DEFINITION",
                    rationale_note=f"Discovered via {sch.discovery_source}",
                )

            if tbl.mapped_orm_symbol_id and tbl.mapped_orm_symbol_id in symbol_entity_by_id:
                orm_ent = symbol_entity_by_id[tbl.mapped_orm_symbol_id]
                self._upsert_relationship(
                    db,
                    tenant_id=tenant_id,
                    application_id=application_id,
                    snapshot_id=snapshot_id,
                    analysis_run_id=analysis_run_id,
                    source_entity_id=orm_ent.id,
                    target_entity_id=ent.id,
                    relationship_type="MAPS_TO_TABLE",
                )

        # Foreign keys -> REFERENCES_TABLE_FK
        if db_tables:
            fks = (
                db.execute(
                    select(DbForeignKey).where(
                        DbForeignKey.tenant_id == tenant_id,
                        DbForeignKey.source_table_id.in_([t.id for t in db_tables]),
                    )
                )
                .scalars()
                .all()
            )
            for fk in fks:
                src_tbl_ent = db_table_entity_by_id.get(fk.source_table_id)
                tgt_tbl_ent = db_table_entity_by_id.get(fk.target_table_id)
                if src_tbl_ent and tgt_tbl_ent:
                    self._upsert_relationship(
                        db,
                        tenant_id=tenant_id,
                        application_id=application_id,
                        snapshot_id=snapshot_id,
                        analysis_run_id=analysis_run_id,
                        source_entity_id=src_tbl_ent.id,
                        target_entity_id=tgt_tbl_ent.id,
                        relationship_type="REFERENCES_TABLE_FK",
                        edge_metadata={
                            "constraint_name": fk.constraint_name,
                            "source_columns": fk.source_column_names,
                            "target_columns": fk.target_column_names,
                            "relation_origin": fk.relation_origin,
                        },
                    )

        # Code-to-DB access edges (`READS_TABLE`, `WRITES_TABLE`, `MAPS_TO_TABLE`)
        for av_id, edge in db_access_edges or []:
            tbl_ent = db_table_entity_by_name.get(edge.table_name.lower())
            if not tbl_ent:
                continue
            src_ent: KnowledgeEntity | None = None
            if edge.symbol_qualified_name:
                src_ent = symbol_entity_by_qname.get(edge.symbol_qualified_name)
            if src_ent is None:
                # Find any symbol in the same file spanning that line range
                cf_match = next(
                    (cf for cf in code_files if cf.artifact_version_id == av_id), None
                )
                if cf_match:
                    sym_match = next(
                        (
                            s
                            for s in symbols
                            if s.code_file_id == cf_match.id
                            and s.start_line <= edge.start_line <= s.end_line
                        ),
                        None,
                    )
                    if sym_match:
                        src_ent = symbol_entity_by_id.get(sym_match.id)
                    elif cf_match.module_id:
                        src_ent = module_entity_by_id.get(cf_match.module_id)
            if src_ent and src_ent.id != tbl_ent.id:
                rel = self._upsert_relationship(
                    db,
                    tenant_id=tenant_id,
                    application_id=application_id,
                    snapshot_id=snapshot_id,
                    analysis_run_id=analysis_run_id,
                    source_entity_id=src_ent.id,
                    target_entity_id=tbl_ent.id,
                    relationship_type=edge.relationship_type,
                    origin_type="DETERMINISTIC_PARSER",
                    edge_metadata={"start_line": edge.start_line, "end_line": edge.end_line},
                )
                anchor = self.get_or_create_evidence_anchor(
                    db,
                    tenant_id=tenant_id,
                    snapshot_id=snapshot_id,
                    artifact_version_id=av_id,
                    start_line=edge.start_line,
                    end_line=edge.end_line,
                    excerpt_text=edge.snippet,
                )
                anchors_created += 1
                self.link_evidence(
                    db,
                    tenant_id=tenant_id,
                    evidence_anchor_id=anchor.id,
                    knowledge_relationship_id=rel.id,
                    evidence_role="CALL_SITE",
                    rationale_note=f"{edge.relationship_type} reference to table `{edge.table_name}`",
                )

        # 5. API Services (`SERVICE`) and API Endpoints (`API_ENDPOINT`)
        api_services = (
            db.execute(
                select(ApiService).where(
                    ApiService.tenant_id == tenant_id,
                    ApiService.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        service_entity_by_id: dict[uuid.UUID, KnowledgeEntity] = {}
        endpoint_entity_by_route: dict[str, KnowledgeEntity] = {}
        api_endpoints: list[ApiEndpoint] = []

        for svc in api_services:
            svc_ent = self._upsert_entity(
                db,
                tenant_id=tenant_id,
                application_id=application_id,
                snapshot_id=snapshot_id,
                analysis_run_id=analysis_run_id,
                entity_type="SERVICE",
                canonical_key=f"api_service:{svc.protocol}:{svc.service_name}",
                title=svc.service_name,
                summary_description=f"{svc.protocol} API Service `{svc.service_name}` (base: `{svc.base_path or '/'}`)",
                attributes_json={"protocol": svc.protocol, "base_path": svc.base_path},
            )
            service_entity_by_id[svc.id] = svc_ent

            eps = (
                db.execute(
                    select(ApiEndpoint).where(
                        ApiEndpoint.tenant_id == tenant_id,
                        ApiEndpoint.api_service_id == svc.id,
                    )
                )
                .scalars()
                .all()
            )
            for ep in eps:
                api_endpoints.append(ep)
                ep_ent = self._upsert_entity(
                    db,
                    tenant_id=tenant_id,
                    application_id=application_id,
                    snapshot_id=snapshot_id,
                    analysis_run_id=analysis_run_id,
                    entity_type="API_ENDPOINT",
                    canonical_key=f"api_endpoint:{svc.service_name}:{ep.http_method}:{ep.route_pattern}",
                    title=f"{ep.http_method} {ep.route_pattern}",
                    summary_description=f"{svc.protocol} endpoint `{ep.http_method} {ep.route_pattern}` on `{svc.service_name}`",
                    source_api_endpoint_id=ep.id,
                    attributes_json={
                        "http_method": ep.http_method,
                        "route_pattern": ep.route_pattern,
                        "auth_required_inferred": ep.auth_required_inferred,
                        "protocol": svc.protocol,
                    },
                )
                endpoint_entity_by_route[ep.route_pattern.lower()] = ep_ent

                self._upsert_relationship(
                    db,
                    tenant_id=tenant_id,
                    application_id=application_id,
                    snapshot_id=snapshot_id,
                    analysis_run_id=analysis_run_id,
                    source_entity_id=svc_ent.id,
                    target_entity_id=ep_ent.id,
                    relationship_type="EXPOSES_API",
                )

                if ep.handler_symbol_id and ep.handler_symbol_id in symbol_entity_by_id:
                    handler_ent = symbol_entity_by_id[ep.handler_symbol_id]
                    self._upsert_relationship(
                        db,
                        tenant_id=tenant_id,
                        application_id=application_id,
                        snapshot_id=snapshot_id,
                        analysis_run_id=analysis_run_id,
                        source_entity_id=handler_ent.id,
                        target_entity_id=ep_ent.id,
                        relationship_type="HANDLES_ENDPOINT",
                    )

        # 6. Infrastructure Resources (`INFRA_RESOURCE`) and `DEPLOYED_ON` / `DEPENDS_ON`
        infra_resources = (
            db.execute(
                select(InfraResource).where(
                    InfraResource.tenant_id == tenant_id,
                    InfraResource.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        infra_entity_by_name: dict[str, KnowledgeEntity] = {}
        for ir in infra_resources:
            ir_ent = self._upsert_entity(
                db,
                tenant_id=tenant_id,
                application_id=application_id,
                snapshot_id=snapshot_id,
                analysis_run_id=analysis_run_id,
                entity_type="INFRA_RESOURCE",
                canonical_key=f"infra:{ir.iac_tool}:{ir.resource_type}:{ir.resource_name}",
                title=f"{ir.resource_name} ({ir.resource_type})",
                summary_description=f"{ir.iac_tool} `{ir.resource_type}` resource `{ir.resource_name}`",
                attributes_json={
                    "iac_tool": ir.iac_tool,
                    "resource_type": ir.resource_type,
                    **(ir.configuration_attributes or {}),
                },
            )
            infra_entity_by_name[ir.resource_name.lower()] = ir_ent

            anchor = self.get_or_create_evidence_anchor(
                db,
                tenant_id=tenant_id,
                snapshot_id=snapshot_id,
                artifact_version_id=ir.source_artifact_version_id,
                start_line=1,
                end_line=10,
                excerpt_text=f"{ir.iac_tool} {ir.resource_type} {ir.resource_name}",
                ast_or_json_path=f"InfraResource[{ir.resource_name}]",
            )
            anchors_created += 1
            self.link_evidence(
                db,
                tenant_id=tenant_id,
                evidence_anchor_id=anchor.id,
                knowledge_entity_id=ir_ent.id,
                evidence_role="CONFIG_BINDING",
                rationale_note=f"Infrastructure definition in {ir.iac_tool}",
            )

        for ir in infra_resources:
            src_ir_ent = infra_entity_by_name.get(ir.resource_name.lower())
            if not src_ir_ent:
                continue
            deps = (ir.configuration_attributes or {}).get("depends_on") or (
                ir.configuration_attributes or {}
            ).get("referenced_resources") or []
            if isinstance(deps, list):
                for dep_name in deps:
                    dep_key = str(dep_name).split(".")[-1].lower()
                    tgt_ir_ent = infra_entity_by_name.get(dep_key) or infra_entity_by_name.get(
                        str(dep_name).lower()
                    )
                    if tgt_ir_ent and tgt_ir_ent.id != src_ir_ent.id:
                        self._upsert_relationship(
                            db,
                            tenant_id=tenant_id,
                            application_id=application_id,
                            snapshot_id=snapshot_id,
                            analysis_run_id=analysis_run_id,
                            source_entity_id=src_ir_ent.id,
                            target_entity_id=tgt_ir_ent.id,
                            relationship_type="DEPENDS_ON",
                        )

        # 7. Connect Documentation Sections (`COMPONENT` / `DOC_CLAIM`) to mentioned code/DB/API entities
        conflicts_created = 0
        for sec_id, (av_id, mentions) in (doc_mentions_by_section or {}).items():
            sec = db.execute(
                select(DocSection).where(
                    DocSection.tenant_id == tenant_id,
                    DocSection.id == sec_id,
                )
            ).scalar_one_or_none()
            if sec is None:
                continue
            doc_anchor = self.get_or_create_evidence_anchor(
                db,
                tenant_id=tenant_id,
                snapshot_id=snapshot_id,
                artifact_version_id=av_id,
                locator_type="DOC_HEADING",
                start_line=sec.start_line,
                end_line=sec.end_line,
                excerpt_text=sec.content_markdown[:1500],
                ast_or_json_path=sec.heading_path,
            )
            anchors_created += 1

            for ident in mentions:
                lower_id = ident.lower()
                matched_ent = (
                    symbol_entity_by_qname.get(ident)
                    or symbol_entity_by_short_name.get(lower_id)
                    or db_table_entity_by_name.get(lower_id)
                    or endpoint_entity_by_route.get(lower_id)
                    or infra_entity_by_name.get(lower_id)
                )
                if matched_ent is not None:
                    self.link_evidence(
                        db,
                        tenant_id=tenant_id,
                        evidence_anchor_id=doc_anchor.id,
                        knowledge_entity_id=matched_ent.id,
                        evidence_role="DOC_CLAIM",
                        rationale_note=f"Documented in section '{sec.heading_path}'",
                    )

        # 8. NetworkX Projection (PageRank, Degree, Betweenness, Strongly Connected Components)
        all_entities = (
            db.execute(
                select(KnowledgeEntity).where(
                    KnowledgeEntity.tenant_id == tenant_id,
                    KnowledgeEntity.snapshot_id == snapshot_id,
                    KnowledgeEntity.analysis_run_id == analysis_run_id,
                )
            )
            .scalars()
            .all()
        )
        all_rels = (
            db.execute(
                select(KnowledgeRelationship).where(
                    KnowledgeRelationship.tenant_id == tenant_id,
                    KnowledgeRelationship.snapshot_id == snapshot_id,
                    KnowledgeRelationship.analysis_run_id == analysis_run_id,
                )
            )
            .scalars()
            .all()
        )

        nx_graph = nx.MultiDiGraph()
        entity_map: dict[uuid.UUID, KnowledgeEntity] = {}
        for ent in all_entities:
            entity_map[ent.id] = ent
            nx_graph.add_node(str(ent.id), entity_type=ent.entity_type, title=ent.title)
        for rel in all_rels:
            nx_graph.add_edge(
                str(rel.source_entity_id),
                str(rel.target_entity_id),
                relationship_type=rel.relationship_type,
                weight=float(rel.edge_weight),
            )

        simple_di = nx.DiGraph(nx_graph)
        try:
            pagerank_scores = nx.pagerank(simple_di) if len(simple_di) > 0 else {}
        except Exception:
            pagerank_scores = {n: 1.0 / max(1, len(simple_di)) for n in simple_di.nodes}

        betweenness_scores = (
            nx.betweenness_centrality(simple_di) if len(simple_di) <= 500 else {}
        )
        sccs = [
            list(comp)
            for comp in nx.strongly_connected_components(simple_di)
            if len(comp) > 1
        ]

        for ent in all_entities:
            nid = str(ent.id)
            attrs = dict(ent.attributes_json or {})
            attrs["in_degree"] = int(simple_di.in_degree(nid)) if nid in simple_di else 0
            attrs["out_degree"] = int(simple_di.out_degree(nid)) if nid in simple_di else 0
            attrs["pagerank"] = round(float(pagerank_scores.get(nid, 0.0)), 6)
            attrs["betweenness_centrality"] = round(
                float(betweenness_scores.get(nid, 0.0)), 6
            )
            ent.attributes_json = attrs

        # 9. Emit Deterministic Evidence-Backed Findings
        findings_created = 0

        # 9a. Circular dependency SCC findings
        for scc in sccs[:10]:
            member_ents = [entity_map[uuid.UUID(nid)] for nid in scc if uuid.UUID(nid) in entity_map]
            if not member_ents:
                continue
            primary_ent = member_ents[0]
            cycle_names = " -> ".join(e.title for e in member_ents[:6])
            finding = Finding(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                application_id=application_id,
                snapshot_id=snapshot_id,
                analysis_run_id=analysis_run_id,
                subject_entity_id=primary_ent.id,
                finding_category="ARCHITECTURE",
                severity="MEDIUM",
                title=f"Circular Dependency Detected ({len(member_ents)} entities)",
                statement_markdown=(
                    f"Tarjan Strongly Connected Component analysis identified a circular dependency cycle "
                    f"involving **{len(member_ents)}** entities: `{cycle_names}`."
                ),
                origin_type="DETERMINISTIC_RULE",
                confidence_score=Decimal("1.0000"),
                review_status="PENDING_REVIEW",
            )
            db.add(finding)
            db.flush()
            findings_created += 1

            if default_av_id:
                anc = self.get_or_create_evidence_anchor(
                    db,
                    tenant_id=tenant_id,
                    snapshot_id=snapshot_id,
                    artifact_version_id=default_av_id,
                    start_line=1,
                    end_line=1,
                    excerpt_text=f"SCC Cycle: {cycle_names}",
                )
                self.link_evidence(
                    db,
                    tenant_id=tenant_id,
                    evidence_anchor_id=anc.id,
                    finding_id=finding.id,
                    evidence_role="CALL_SITE",
                    rationale_note="Strongly connected cycle detected in static dependency graph",
                )

        # 9b. Database PII exposure candidate findings
        for tbl in db_tables:
            tbl_ent = db_table_entity_by_id.get(tbl.id)
            if not tbl_ent:
                continue
            pii_cols = (tbl_ent.attributes_json or {}).get("pii_columns") or []
            if pii_cols:
                sch = schema_by_id[tbl.db_schema_id]
                finding = Finding(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    application_id=application_id,
                    snapshot_id=snapshot_id,
                    analysis_run_id=analysis_run_id,
                    subject_entity_id=tbl_ent.id,
                    finding_category="SECURITY_RISK",
                    severity="HIGH",
                    title=f"PII / Sensitive Columns in Table `{sch.schema_name}.{tbl.table_name}`",
                    statement_markdown=(
                        f"Database table `{sch.schema_name}.{tbl.table_name}` contains **{len(pii_cols)}** "
                        f"sensitive/PII candidate column(s): `{', '.join(pii_cols)}`. "
                        f"Verify encryption-at-rest, masking policies, and retention governance."
                    ),
                    origin_type="DETERMINISTIC_RULE",
                    confidence_score=Decimal("0.9500"),
                    review_status="PENDING_REVIEW",
                )
                db.add(finding)
                db.flush()
                findings_created += 1
                av_id = sch.source_artifact_version_id or default_av_id
                if av_id:
                    anc = self.get_or_create_evidence_anchor(
                        db,
                        tenant_id=tenant_id,
                        snapshot_id=snapshot_id,
                        artifact_version_id=av_id,
                        start_line=1,
                        end_line=5,
                        excerpt_text=f"Table {tbl.table_name} PII columns: {', '.join(pii_cols)}",
                    )
                    self.link_evidence(
                        db,
                        tenant_id=tenant_id,
                        evidence_anchor_id=anc.id,
                        finding_id=finding.id,
                        evidence_role="PRIMARY_DEFINITION",
                        rationale_note="PII column identifier heuristic match",
                    )

        # 9c. Unauthenticated state-mutating API endpoint findings
        for ep in api_endpoints:
            if ep.http_method in ("POST", "PUT", "DELETE", "PATCH") and ep.auth_required_inferred is False:
                ep_ent = endpoint_entity_by_route.get(ep.route_pattern.lower())
                finding = Finding(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    application_id=application_id,
                    snapshot_id=snapshot_id,
                    analysis_run_id=analysis_run_id,
                    subject_entity_id=ep_ent.id if ep_ent else None,
                    finding_category="SECURITY_RISK",
                    severity="MEDIUM",
                    title=f"State-Mutating Endpoint Without Explicit Auth Guard: `{ep.http_method} {ep.route_pattern}`",
                    statement_markdown=(
                        f"Endpoint `{ep.http_method} {ep.route_pattern}` performs state mutation (`{ep.http_method}`) "
                        f"without a detected authentication decorator, security scheme, or middleware guard."
                    ),
                    origin_type="DETERMINISTIC_RULE",
                    confidence_score=Decimal("0.8800"),
                    review_status="PENDING_REVIEW",
                )
                db.add(finding)
                db.flush()
                findings_created += 1
                if default_av_id:
                    anc = self.get_or_create_evidence_anchor(
                        db,
                        tenant_id=tenant_id,
                        snapshot_id=snapshot_id,
                        artifact_version_id=default_av_id,
                        start_line=1,
                        end_line=5,
                        excerpt_text=f"{ep.http_method} {ep.route_pattern} (auth_required_inferred=False)",
                    )
                    self.link_evidence(
                        db,
                        tenant_id=tenant_id,
                        evidence_anchor_id=anc.id,
                        finding_id=finding.id,
                        evidence_role="PRIMARY_DEFINITION",
                        rationale_note="Endpoint route lacks explicit auth middleware/security scheme",
                    )

        db.flush()
        return GraphBuildStats(
            entities_count=len(all_entities),
            relationships_count=len(all_rels),
            evidence_anchors_count=anchors_created,
            deterministic_findings_count=findings_created,
            conflicts_count=conflicts_created,
            scc_cycles_count=len(sccs),
        )

    def traverse_subgraph(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        root_entity_id: uuid.UUID,
        max_hops: int = 3,
        direction: str = "OUTGOING",
        relationship_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a cycle-safe recursive CTE graph traversal (`WHERE NOT target = ANY(visited_path)`)
        with strict `tenant_id` and `snapshot_id` predicates at both seed and recursive steps.
        """
        safe_hops = max(1, min(6, int(max_hops)))
        dir_upper = direction.upper()

        root_ent = db.execute(
            select(KnowledgeEntity).where(
                KnowledgeEntity.tenant_id == tenant_id,
                KnowledgeEntity.snapshot_id == snapshot_id,
                KnowledgeEntity.id == root_entity_id,
            )
        ).scalar_one_or_none()
        if root_ent is None:
            return {"root_entity_id": str(root_entity_id), "nodes": [], "edges": []}

        if dir_upper == "INCOMING":
            join_cond = "kr.target_entity_id = g.current_id"
            seed_next_col = "kr.source_entity_id"
            rec_next_col = "kr.source_entity_id"
        elif dir_upper == "BOTH":
            join_cond = "(kr.source_entity_id = g.current_id OR kr.target_entity_id = g.current_id)"
            seed_next_col = "CASE WHEN kr.source_entity_id = :root_id THEN kr.target_entity_id ELSE kr.source_entity_id END"
            rec_next_col = "CASE WHEN kr.source_entity_id = g.current_id THEN kr.target_entity_id ELSE kr.source_entity_id END"
        else:
            join_cond = "kr.source_entity_id = g.current_id"
            seed_next_col = "kr.target_entity_id"
            rec_next_col = "kr.target_entity_id"

        cte_sql = text(
            f"""
            WITH RECURSIVE graph_walk AS (
                SELECT
                    kr.id AS edge_id,
                    kr.source_entity_id,
                    kr.target_entity_id,
                    {seed_next_col} AS current_id,
                    kr.relationship_type,
                    kr.confidence_score,
                    1 AS hop_depth,
                    ARRAY[CAST(:root_id AS uuid), {seed_next_col}] AS visited_path
                FROM knowledge_relationships kr
                WHERE kr.tenant_id = :tenant_id
                  AND kr.snapshot_id = :snapshot_id
                  AND ({'kr.target_entity_id = :root_id' if dir_upper == 'INCOMING' else ('(kr.source_entity_id = :root_id OR kr.target_entity_id = :root_id)' if dir_upper == 'BOTH' else 'kr.source_entity_id = :root_id')})

                UNION ALL

                SELECT
                    kr.id AS edge_id,
                    kr.source_entity_id,
                    kr.target_entity_id,
                    {rec_next_col} AS current_id,
                    kr.relationship_type,
                    kr.confidence_score,
                    g.hop_depth + 1,
                    g.visited_path || {rec_next_col}
                FROM knowledge_relationships kr
                INNER JOIN graph_walk g
                    ON kr.tenant_id = :tenant_id
                   AND kr.snapshot_id = :snapshot_id
                   AND {join_cond}
                WHERE g.hop_depth < :max_hops
                  AND NOT ({rec_next_col} = ANY(g.visited_path))
            )
            SELECT DISTINCT
                edge_id,
                source_entity_id,
                target_entity_id,
                relationship_type,
                confidence_score,
                MIN(hop_depth) AS min_hop_depth
            FROM graph_walk
            GROUP BY edge_id, source_entity_id, target_entity_id, relationship_type, confidence_score
            ORDER BY min_hop_depth ASC
            LIMIT 500;
            """
        )

        rows = db.execute(
            cte_sql,
            {
                "tenant_id": tenant_id,
                "snapshot_id": snapshot_id,
                "root_id": root_entity_id,
                "max_hops": safe_hops,
            },
        ).fetchall()

        allowed_types = {rt.upper() for rt in relationship_types} if relationship_types else None
        edges: list[dict[str, Any]] = []
        node_ids: set[uuid.UUID] = {root_entity_id}

        for r in rows:
            if allowed_types and str(r.relationship_type).upper() not in allowed_types:
                continue
            node_ids.add(r.source_entity_id)
            node_ids.add(r.target_entity_id)
            edges.append(
                {
                    "id": str(r.edge_id),
                    "source_entity_id": str(r.source_entity_id),
                    "target_entity_id": str(r.target_entity_id),
                    "relationship_type": r.relationship_type,
                    "confidence_score": float(r.confidence_score),
                    "hop_depth": int(r.min_hop_depth),
                }
            )

        entities = (
            db.execute(
                select(KnowledgeEntity).where(
                    KnowledgeEntity.tenant_id == tenant_id,
                    KnowledgeEntity.snapshot_id == snapshot_id,
                    KnowledgeEntity.id.in_(list(node_ids)),
                )
            )
            .scalars()
            .all()
        )
        nodes = [
            {
                "id": str(e.id),
                "entity_type": e.entity_type,
                "canonical_key": e.canonical_key,
                "title": e.title,
                "summary_description": e.summary_description,
                "origin_type": e.origin_type,
                "confidence_score": float(e.confidence_score),
                "review_status": e.review_status,
                "attributes_json": e.attributes_json,
            }
            for e in entities
        ]
        return {
            "root_entity_id": str(root_entity_id),
            "direction": dir_upper,
            "max_hops": safe_hops,
            "nodes": nodes,
            "edges": edges,
        }

    def review_finding(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        finding_id: uuid.UUID,
        reviewer_user_id: uuid.UUID,
        new_status: str,
        review_comment: str | None = None,
        updated_title: str | None = None,
        updated_statement_markdown: str | None = None,
    ) -> Finding:
        """Transition a `Finding` review status and append an immutable `ReviewHistory` audit entry."""
        finding = db.execute(
            select(Finding).where(
                Finding.tenant_id == tenant_id,
                Finding.id == finding_id,
            )
        ).scalar_one_or_none()
        if finding is None:
            raise ValueError(f"Finding {finding_id} not found for tenant {tenant_id}.")

        prev_status = finding.review_status
        prev_snap = {
            "title": finding.title,
            "statement_markdown": finding.statement_markdown,
            "severity": finding.severity,
            "review_status": finding.review_status,
            "version_no": finding.version_no,
        }

        finding.review_status = new_status
        if updated_title:
            finding.title = updated_title[:255]
        if updated_statement_markdown:
            finding.statement_markdown = updated_statement_markdown
        finding.version_no = int(finding.version_no) + 1

        new_snap = {
            "title": finding.title,
            "statement_markdown": finding.statement_markdown,
            "severity": finding.severity,
            "review_status": finding.review_status,
            "version_no": finding.version_no,
        }

        history = ReviewHistory(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            target_object_type="FINDING",
            target_object_id=finding.id,
            reviewer_user_id=reviewer_user_id,
            previous_status=prev_status,
            new_status=new_status,
            previous_snapshot_json=prev_snap,
            updated_snapshot_json=new_snap,
            review_comment=review_comment,
            reviewed_at=datetime.now(timezone.utc),
        )
        db.add(history)
        db.flush()
        return finding
