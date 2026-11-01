"""Wave 2 — Technical Intelligence Pipeline Service (Database, API, Infrastructure, Documentation, Unified Knowledge Graph & Agent Orchestration)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.api_intelligence import (
    ExtractedApiEndpoint,
    extract_api_endpoints_from_code,
    parse_graphql_schema,
    parse_openapi_or_swagger,
)
from app.analysis.database_intelligence import (
    ExtractedDbAccessEdge,
    ExtractedDbForeignKey,
    ExtractedDbTable,
    extract_orm_and_sql_from_code,
    parse_sql_ddl,
)
from app.analysis.doc_intelligence import extract_documentation
from app.analysis.infra_intelligence import (
    parse_dockerfile,
    parse_terraform_hcl,
    parse_yaml_or_json_iac,
)
from app.analysis.parser_registry import (
    SUPPORTED_CODE_LANGUAGES,
    derive_module_info,
    detect_language_and_kind,
)
from app.integrations.storage import TenantObjectStorage
from app.models.code_intelligence import AnalysisRun, CodeSymbol
from app.models.ingestion import Artifact, ArtifactVersion, Repository, RepositorySnapshot
from app.models.projects import AnalysisScope
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
from app.services.agent_orchestrator import TechnicalIntelligenceOrchestrator
from app.services.knowledge_graph_service import KnowledgeGraphService


@dataclass
class Wave2PipelineSummary:
    snapshot_id: uuid.UUID
    analysis_run_id: uuid.UUID
    db_schemas_count: int
    db_tables_count: int
    db_columns_count: int
    db_foreign_keys_count: int
    api_services_count: int
    api_endpoints_count: int
    infra_resources_count: int
    doc_sections_count: int
    knowledge_entities_count: int
    knowledge_relationships_count: int
    evidence_anchors_count: int
    findings_count: int
    agent_runs_count: int


class TechnicalIntelligenceService:
    """
    Executes the complete Wave 2 pipeline for a repository snapshot:
    1. Database Intelligence (`db_schemas`, `db_tables`, `db_columns`, `db_foreign_keys`)
    2. API Intelligence (`api_services`, `api_endpoints`)
    3. Infrastructure Intelligence (`infra_resources`)
    4. Documentation Intelligence (`doc_sections`)
    5. Unified Knowledge Graph & Provenance (`knowledge_entities`, `knowledge_relationships`, `evidence_anchors`, `findings`)
    6. AI Agent Orchestration (`agent_runs`, `agent_task_dependencies`, `model_invocations`, `agent_execution_events`)
    """

    def __init__(
        self,
        storage: TenantObjectStorage | None = None,
        graph_service: KnowledgeGraphService | None = None,
        orchestrator: TechnicalIntelligenceOrchestrator | None = None,
    ) -> None:
        self.storage = storage or TenantObjectStorage()
        self.graph_service = graph_service or KnowledgeGraphService()
        self.orchestrator = orchestrator or TechnicalIntelligenceOrchestrator()

    def _resolve_snapshot_artifacts(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        repository_id: uuid.UUID,
        snapshot_artifacts: list[tuple[Artifact, ArtifactVersion]] | None = None,
    ) -> list[tuple[Artifact, ArtifactVersion]]:
        if snapshot_artifacts is not None:
            return snapshot_artifacts

        artifacts = (
            db.execute(
                select(Artifact).where(
                    Artifact.tenant_id == tenant_id,
                    Artifact.repository_id == repository_id,
                )
            )
            .scalars()
            .all()
        )
        pairs: list[tuple[Artifact, ArtifactVersion]] = []
        for art in artifacts:
            ver = (
                db.execute(
                    select(ArtifactVersion)
                    .where(
                        ArtifactVersion.tenant_id == tenant_id,
                        ArtifactVersion.artifact_id == art.id,
                    )
                    .order_by(ArtifactVersion.created_at.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            if ver is not None:
                pairs.append((art, ver))
        return pairs

    def _resolve_or_create_analysis_run(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        application_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        analysis_run_id: uuid.UUID | None = None,
    ) -> AnalysisRun:
        if analysis_run_id is not None:
            run = db.execute(
                select(AnalysisRun).where(
                    AnalysisRun.tenant_id == tenant_id,
                    AnalysisRun.id == analysis_run_id,
                )
            ).scalar_one_or_none()
            if run is not None:
                return run

        existing_run = (
            db.execute(
                select(AnalysisRun)
                .where(
                    AnalysisRun.tenant_id == tenant_id,
                    AnalysisRun.snapshot_id == snapshot_id,
                )
                .order_by(AnalysisRun.run_number.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if existing_run is not None:
            return existing_run

        scope = (
            db.execute(
                select(AnalysisScope)
                .where(
                    AnalysisScope.tenant_id == tenant_id,
                    AnalysisScope.application_id == application_id,
                )
                .limit(1)
            )
            .scalars()
            .first()
        )
        if scope is None:
            scope = AnalysisScope(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                application_id=application_id,
                name="default-full-scope",
                include_globs=["**/*"],
                exclude_globs=["**/node_modules/**", "**/.git/**"],
                max_file_size_kb=10240,
                enable_ai_enrichment=True,
            )
            db.add(scope)
            db.flush()

        existing_nums = (
            db.execute(
                select(AnalysisRun.run_number).where(
                    AnalysisRun.tenant_id == tenant_id,
                    AnalysisRun.application_id == application_id,
                )
            )
            .scalars()
            .all()
        )
        next_num = (max(existing_nums) + 1) if existing_nums else 1
        new_run = AnalysisRun(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            application_id=application_id,
            snapshot_id=snapshot_id,
            analysis_scope_id=scope.id,
            run_number=next_num,
            run_mode="FULL_DISCOVERY",
            status="COMPLETED",
            pipeline_versions_manifest={"wave": "2.0.0"},
        )
        db.add(new_run)
        db.flush()
        return new_run

    def run_wave2_pipeline(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        analysis_run_id: uuid.UUID | None = None,
        snapshot_artifacts: list[tuple[Artifact, ArtifactVersion]] | None = None,
    ) -> Wave2PipelineSummary:
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

        analysis_run = self._resolve_or_create_analysis_run(
            db,
            tenant_id=tenant_id,
            application_id=repo.application_id,
            snapshot_id=snapshot.id,
            analysis_run_id=analysis_run_id,
        )

        pairs = self._resolve_snapshot_artifacts(
            db,
            tenant_id=tenant_id,
            repository_id=repo.id,
            snapshot_artifacts=snapshot_artifacts,
        )

        # Symbol lookup for ORM entity & API handler resolution
        symbols = (
            db.execute(
                select(CodeSymbol).where(
                    CodeSymbol.tenant_id == tenant_id,
                    CodeSymbol.snapshot_id == snapshot.id,
                )
            )
            .scalars()
            .all()
        )
        symbol_by_qname: dict[str, CodeSymbol] = {s.qualified_name: s for s in symbols}
        symbol_by_short_name: dict[str, CodeSymbol] = {s.name.lower(): s for s in symbols}

        # Collections for pass 1 & pass 2
        extracted_tables: list[tuple[uuid.UUID, ExtractedDbTable]] = []
        extracted_fks: list[tuple[uuid.UUID, ExtractedDbForeignKey]] = []
        db_access_edges: list[tuple[uuid.UUID, ExtractedDbAccessEdge]] = []
        extracted_endpoints: list[tuple[uuid.UUID, ExtractedApiEndpoint]] = []
        doc_mentions_by_section: dict[uuid.UUID, tuple[uuid.UUID, list[str]]] = {}

        infra_count = 0
        doc_sections_count = 0

        # Pass 1: Extract SQL DDL, OpenAPI, GraphQL, Infrastructure, and Documentation
        code_sources: list[tuple[Artifact, ArtifactVersion, str, str]] = []
        for artifact, av in pairs:
            if not self.storage.blob_exists(tenant_id, av.content_sha256):
                continue
            raw_bytes = self.storage.get_blob_bytes(tenant_id, av.content_sha256)
            lang, kind = detect_language_and_kind(artifact.canonical_path)
            lower_path = artifact.canonical_path.lower()

            # 1a. SQL DDL files
            if lang == "sql" or lower_path.endswith(".sql"):
                sql_text = raw_bytes.decode("utf-8", errors="replace")
                ddl_res = parse_sql_ddl(sql_text, artifact.canonical_path)
                for tbl in ddl_res.tables:
                    extracted_tables.append((av.id, tbl))
                for fk in ddl_res.foreign_keys:
                    extracted_fks.append((av.id, fk))
                continue

            # 1b. GraphQL Schema files
            if lang == "graphql" or lower_path.endswith((".graphql", ".gql")):
                gql_text = raw_bytes.decode("utf-8", errors="replace")
                gql_res = parse_graphql_schema(gql_text, artifact.canonical_path)
                for ep in gql_res.endpoints:
                    extracted_endpoints.append((av.id, ep))
                continue

            # 1c. Dockerfile
            if lang == "dockerfile" or kind == "IAC_MANIFEST" and "dockerfile" in lower_path:
                df_text = raw_bytes.decode("utf-8", errors="replace")
                df_res = parse_dockerfile(df_text, artifact.canonical_path)
                for ir in df_res.resources:
                    db.add(
                        InfraResource(
                            id=uuid.uuid4(),
                            tenant_id=tenant_id,
                            snapshot_id=snapshot.id,
                            source_artifact_version_id=av.id,
                            iac_tool=ir.iac_tool,
                            resource_type=ir.resource_type,
                            resource_name=ir.resource_name,
                            configuration_attributes=ir.configuration_attributes,
                        )
                    )
                    infra_count += 1
                continue

            # 1d. Terraform HCL
            if lang == "terraform" or lower_path.endswith((".tf", ".tfvars")):
                tf_text = raw_bytes.decode("utf-8", errors="replace")
                tf_res = parse_terraform_hcl(tf_text, artifact.canonical_path)
                for ir in tf_res.resources:
                    db.add(
                        InfraResource(
                            id=uuid.uuid4(),
                            tenant_id=tenant_id,
                            snapshot_id=snapshot.id,
                            source_artifact_version_id=av.id,
                            iac_tool=ir.iac_tool,
                            resource_type=ir.resource_type,
                            resource_name=ir.resource_name,
                            configuration_attributes=ir.configuration_attributes,
                        )
                    )
                    infra_count += 1
                continue

            # 1e. YAML / JSON (OpenAPI/Swagger, Docker Compose, Kubernetes, CloudFormation)
            if lang in ("yaml", "json") or lower_path.endswith((".yaml", ".yml", ".json")):
                yj_text = raw_bytes.decode("utf-8", errors="replace")
                oa_res = parse_openapi_or_swagger(yj_text, artifact.canonical_path)
                for ep in oa_res.endpoints:
                    extracted_endpoints.append((av.id, ep))

                iac_res = parse_yaml_or_json_iac(yj_text, artifact.canonical_path)
                for ir in iac_res.resources:
                    db.add(
                        InfraResource(
                            id=uuid.uuid4(),
                            tenant_id=tenant_id,
                            snapshot_id=snapshot.id,
                            source_artifact_version_id=av.id,
                            iac_tool=ir.iac_tool,
                            resource_type=ir.resource_type,
                            resource_name=ir.resource_name,
                            configuration_attributes=ir.configuration_attributes,
                        )
                    )
                    infra_count += 1
                continue

            # 1f. Documentation files (Markdown, RST, AsciiDoc, TXT, HTML, DOCX, XLSX, PDF)
            if kind == "DOCUMENTATION" or lang in (
                "markdown",
                "rst",
                "asciidoc",
                "text",
                "html",
                "docx",
                "xlsx",
                "pdf",
            ):
                doc_res = extract_documentation(raw_bytes, lang, artifact.canonical_path)
                created_sec_ids: list[uuid.UUID] = []
                for sec in doc_res.sections:
                    parent_uuid = (
                        created_sec_ids[sec.parent_index]
                        if sec.parent_index is not None
                        and 0 <= sec.parent_index < len(created_sec_ids)
                        else None
                    )
                    sec_row = DocSection(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        artifact_version_id=av.id,
                        parent_section_id=parent_uuid,
                        heading_path=sec.heading_path,
                        heading_level=sec.heading_level,
                        start_line=sec.start_line,
                        end_line=sec.end_line,
                        content_markdown=sec.content_markdown,
                    )
                    db.add(sec_row)
                    db.flush()
                    created_sec_ids.append(sec_row.id)
                    doc_sections_count += 1
                    if sec.mentioned_identifiers:
                        doc_mentions_by_section[sec_row.id] = (av.id, sec.mentioned_identifiers)
                continue

            # 1g. Source code files queued for ORM/SQL & REST controller extraction
            if lang in SUPPORTED_CODE_LANGUAGES:
                code_text = raw_bytes.decode("utf-8", errors="replace")
                code_sources.append((artifact, av, lang, code_text))

        db.flush()

        # Pass 2: Extract ORM models, embedded SQL edges, and REST endpoints from source code
        known_tables_lower = {t.table_name.lower() for _, t in extracted_tables}
        for artifact, av, lang, code_text in code_sources:
            _, mod_name = derive_module_info(artifact.canonical_path, lang)
            orm_res = extract_orm_and_sql_from_code(
                code_text, lang, mod_name, known_table_names=None
            )
            for tbl in orm_res.tables:
                extracted_tables.append((av.id, tbl))
                known_tables_lower.add(tbl.table_name.lower())
            for fk in orm_res.foreign_keys:
                extracted_fks.append((av.id, fk))
            for edge in orm_res.access_edges:
                db_access_edges.append((av.id, edge))

            api_res = extract_api_endpoints_from_code(
                code_text, lang, mod_name, artifact.canonical_path
            )
            for ep in api_res.endpoints:
                extracted_endpoints.append((av.id, ep))

        # Persist Domain E Database Intelligence (`DbSchema`, `DbTable`, `DbColumn`, `DbForeignKey`)
        schema_map: dict[str, DbSchema] = {}
        table_map: dict[tuple[str, str], DbTable] = {}
        table_by_name_only: dict[str, DbTable] = {}
        columns_count = 0
        fks_count = 0

        for av_id, etbl in extracted_tables:
            sch_key = etbl.schema_name.lower()
            if sch_key not in schema_map:
                existing_sch = db.execute(
                    select(DbSchema).where(
                        DbSchema.tenant_id == tenant_id,
                        DbSchema.snapshot_id == snapshot.id,
                        DbSchema.schema_name == etbl.schema_name,
                    )
                ).scalar_one_or_none()
                if existing_sch is None:
                    existing_sch = DbSchema(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        snapshot_id=snapshot.id,
                        source_artifact_version_id=av_id,
                        db_engine=etbl.db_engine,
                        schema_name=etbl.schema_name,
                        discovery_source=etbl.discovery_source,
                    )
                    db.add(existing_sch)
                    db.flush()
                schema_map[sch_key] = existing_sch

            sch_obj = schema_map[sch_key]
            tbl_key = (sch_key, etbl.table_name.lower())
            orm_sym = (
                symbol_by_qname.get(etbl.mapped_orm_qualified_name)
                if etbl.mapped_orm_qualified_name
                else None
            )

            existing_tbl = db.execute(
                select(DbTable).where(
                    DbTable.tenant_id == tenant_id,
                    DbTable.db_schema_id == sch_obj.id,
                    DbTable.table_name == etbl.table_name,
                )
            ).scalar_one_or_none()

            if existing_tbl is None:
                existing_tbl = DbTable(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    db_schema_id=sch_obj.id,
                    mapped_orm_symbol_id=orm_sym.id if orm_sym else None,
                    table_name=etbl.table_name,
                    table_kind=etbl.table_kind,
                    comment_text=etbl.comment_text,
                )
                db.add(existing_tbl)
                db.flush()
            elif orm_sym and existing_tbl.mapped_orm_symbol_id is None:
                existing_tbl.mapped_orm_symbol_id = orm_sym.id

            table_map[tbl_key] = existing_tbl
            table_by_name_only[etbl.table_name.lower()] = existing_tbl

            for ecol in etbl.columns:
                existing_col = db.execute(
                    select(DbColumn).where(
                        DbColumn.tenant_id == tenant_id,
                        DbColumn.db_table_id == existing_tbl.id,
                        DbColumn.column_name == ecol.column_name,
                    )
                ).scalar_one_or_none()
                if existing_col is None:
                    db.add(
                        DbColumn(
                            id=uuid.uuid4(),
                            tenant_id=tenant_id,
                            db_table_id=existing_tbl.id,
                            column_name=ecol.column_name,
                            ordinal_position=ecol.ordinal_position,
                            data_type=ecol.data_type,
                            is_nullable=ecol.is_nullable,
                            is_primary_key=ecol.is_primary_key,
                            is_pii_candidate=ecol.is_pii_candidate,
                        )
                    )
                    columns_count += 1
            db.flush()

        for _, efk in extracted_fks:
            src_tbl = table_map.get(
                (efk.source_schema.lower(), efk.source_table.lower())
            ) or table_by_name_only.get(efk.source_table.lower())
            tgt_tbl = table_map.get(
                (efk.target_schema.lower(), efk.target_table.lower())
            ) or table_by_name_only.get(efk.target_table.lower())
            if src_tbl and tgt_tbl:
                db.add(
                    DbForeignKey(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        source_table_id=src_tbl.id,
                        target_table_id=tgt_tbl.id,
                        constraint_name=efk.constraint_name,
                        source_column_names=efk.source_columns,
                        target_column_names=efk.target_columns,
                        relation_origin=efk.relation_origin,
                    )
                )
                fks_count += 1
        db.flush()

        # Persist Domain E API Intelligence (`ApiService`, `ApiEndpoint`)
        api_service_map: dict[str, ApiService] = {}
        endpoints_count = 0
        for _, eep in extracted_endpoints:
            svc_key = eep.service_name.lower()
            if svc_key not in api_service_map:
                existing_svc = db.execute(
                    select(ApiService).where(
                        ApiService.tenant_id == tenant_id,
                        ApiService.snapshot_id == snapshot.id,
                        ApiService.service_name == eep.service_name,
                    )
                ).scalar_one_or_none()
                if existing_svc is None:
                    existing_svc = ApiService(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        snapshot_id=snapshot.id,
                        service_name=eep.service_name,
                        protocol=eep.protocol,
                        base_path=eep.base_path,
                    )
                    db.add(existing_svc)
                    db.flush()
                api_service_map[svc_key] = existing_svc

            svc_obj = api_service_map[svc_key]
            handler_sym = (
                symbol_by_qname.get(eep.handler_qualified_name)
                if eep.handler_qualified_name
                else None
            ) or (
                symbol_by_short_name.get(eep.handler_name.lower())
                if eep.handler_name
                else None
            )

            existing_ep = db.execute(
                select(ApiEndpoint).where(
                    ApiEndpoint.tenant_id == tenant_id,
                    ApiEndpoint.api_service_id == svc_obj.id,
                    ApiEndpoint.http_method == eep.http_method,
                    ApiEndpoint.route_pattern == eep.route_pattern,
                )
            ).scalar_one_or_none()
            if existing_ep is None:
                db.add(
                    ApiEndpoint(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        api_service_id=svc_obj.id,
                        handler_symbol_id=handler_sym.id if handler_sym else None,
                        http_method=eep.http_method,
                        route_pattern=eep.route_pattern,
                        auth_required_inferred=eep.auth_required_inferred,
                        request_schema_json=eep.request_schema_json,
                        response_schema_json=eep.response_schema_json,
                    )
                )
                endpoints_count += 1
        db.flush()

        # Build Unified Knowledge Graph & Provenance (Domain F)
        graph_stats = self.graph_service.build_unified_knowledge_graph(
            db,
            tenant_id=tenant_id,
            application_id=repo.application_id,
            snapshot_id=snapshot.id,
            analysis_run_id=analysis_run.id,
            db_access_edges=db_access_edges,
            doc_mentions_by_section=doc_mentions_by_section,
        )

        # Execute AI Agent Orchestration DAG (Domain I)
        orch_stats = self.orchestrator.run_wave2_agents(
            db,
            tenant_id=tenant_id,
            application_id=repo.application_id,
            snapshot_id=snapshot.id,
            analysis_run_id=analysis_run.id,
            domain_telemetry={
                "db_tables_count": len(table_map),
                "api_endpoints_count": endpoints_count,
                "infra_resources_count": infra_count,
                "doc_sections_count": doc_sections_count,
                "scc_cycles_count": graph_stats.scc_cycles_count,
            },
        )

        return Wave2PipelineSummary(
            snapshot_id=snapshot.id,
            analysis_run_id=analysis_run.id,
            db_schemas_count=len(schema_map),
            db_tables_count=len(table_map),
            db_columns_count=columns_count,
            db_foreign_keys_count=fks_count,
            api_services_count=len(api_service_map),
            api_endpoints_count=endpoints_count,
            infra_resources_count=infra_count,
            doc_sections_count=doc_sections_count,
            knowledge_entities_count=graph_stats.entities_count,
            knowledge_relationships_count=graph_stats.relationships_count,
            evidence_anchors_count=graph_stats.evidence_anchors_count,
            findings_count=graph_stats.deterministic_findings_count
            + int(orch_stats.get("findings_accepted", 0)),
            agent_runs_count=int(orch_stats.get("agents_executed", 0)) + 1,
        )
