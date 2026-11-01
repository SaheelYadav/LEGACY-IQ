"""Live PostgreSQL 17 + pgvector integration and negative RLS security tests (Wave 1)."""

from __future__ import annotations

import io
import os
from pathlib import Path
import uuid
import zipfile

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.api.v1.endpoints.code_intelligence import (
    get_code_summary,
    list_code_call_edges,
    list_code_files,
    list_code_imports,
    list_code_references,
    list_code_symbols,
    list_code_type_hierarchies,
)
from app.api.v1.endpoints.organizations import bootstrap_default_context
from app.api.v1.endpoints.search import post_hybrid_search
from app.core.security import (
    ROLE_ORG_OWNER_ID,
    ROLE_VIEWER_ID,
    SecurityViolationError,
    verify_and_activate_tenant_context,
    verify_project_access,
)
from app.db.session import (
    SessionLocal,
    activate_unscoped_rls_role,
    tenant_db_session,
)
from app.integrations.storage import TenantObjectStorage
from app.models.code_intelligence import (
    CodeCallEdge,
    CodeSymbol,
    CodeTypeHierarchy,
)
from app.models.identity import Organization, OrganizationMembership, User
from app.models.ingestion import Repository
from app.models.projects import Application, Project, Workspace
from app.schemas.platform import HybridSearchRequest
from app.services.ingestion_service import IngestionService
from app.services.retrieval_service import RetrievalService


def test_postgres_33_tables_indexes_triggers_and_rls_enabled() -> None:
    with SessionLocal() as db:
        tables = set(
            db.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename != 'alembic_version'"
                )
            )
            .scalars()
            .all()
        )
        assert len(tables) >= 33

        rev = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert rev in ("0003_wave1_rls_vec", "0004_wave2_tech_intel")

        indexes = set(
            db.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
            )
            .scalars()
            .all()
        )
        assert "ux_active_analysis_run_per_snapshot" in indexes
        assert "ix_doc_chunks_search_tsv" in indexes
        assert "ix_artifact_embeddings_hnsw_cosine" in indexes

        # Verify RLS is enabled and forced on all tenant/hybrid-scoped tables
        # (GLOBAL_SYSTEM tables are users, permissions, role_permissions, embedding_model_versions)
        rls_rows = db.execute(
            text(
                """
                SELECT relname, relrowsecurity, relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind = 'r'
                  AND relname NOT IN (
                      'alembic_version',
                      'users',
                      'permissions',
                      'role_permissions',
                      'embedding_model_versions'
                  )
                """
            )
        ).fetchall()
        assert len(rls_rows) >= 29
        for relname, rowsec, forcerowsec in rls_rows:
            assert rowsec is True, f"RLS not enabled on {relname}"
            assert forcerowsec is True, f"FORCE RLS not enabled on {relname}"


def test_negative_tenant_isolation_and_project_rbac() -> None:
    suffix = uuid.uuid4().hex[:8]
    tenant_a_id = uuid.uuid4()
    tenant_b_id = uuid.uuid4()
    user_a_id = uuid.uuid4()
    user_a_limited_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    # Seed users (GLOBAL_SYSTEM table)
    with SessionLocal() as db:
        db.add_all(
            [
                User(
                    id=user_a_id,
                    email=f"owner-a-{suffix}@test.local",
                    full_name="Owner A",
                ),
                User(
                    id=user_a_limited_id,
                    email=f"viewer-a-{suffix}@test.local",
                    full_name="Viewer A",
                ),
                User(
                    id=user_b_id,
                    email=f"owner-b-{suffix}@test.local",
                    full_name="Owner B",
                ),
            ]
        )
        db.commit()

    # Provision Tenant A
    ws_a_id = uuid.uuid4()
    proj_a_id = uuid.uuid4()
    with tenant_db_session(tenant_a_id) as db:
        org_a = Organization(
            id=tenant_a_id,
            slug=f"tenant-a-{suffix}",
            display_name=f"Tenant A {suffix}",
            status="ACTIVE",
            tier="ENTERPRISE",
        )
        db.add(org_a)
        db.flush()
        db.add_all(
            [
                OrganizationMembership(
                    id=uuid.uuid4(),
                    tenant_id=tenant_a_id,
                    user_id=user_a_id,
                    role_id=ROLE_ORG_OWNER_ID,
                    status="ACTIVE",
                ),
                OrganizationMembership(
                    id=uuid.uuid4(),
                    tenant_id=tenant_a_id,
                    user_id=user_a_limited_id,
                    role_id=ROLE_VIEWER_ID,
                    status="ACTIVE",
                ),
                Workspace(
                    id=ws_a_id,
                    tenant_id=tenant_a_id,
                    slug="ws-a",
                    name="Workspace A",
                ),
            ]
        )
        db.flush()
        db.add(
            Project(
                id=proj_a_id,
                tenant_id=tenant_a_id,
                workspace_id=ws_a_id,
                key="PRJA",
                name="Secret Project A",
            )
        )

    # Provision Tenant B
    ws_b_id = uuid.uuid4()
    with tenant_db_session(tenant_b_id) as db:
        org_b = Organization(
            id=tenant_b_id,
            slug=f"tenant-b-{suffix}",
            display_name=f"Tenant B {suffix}",
            status="ACTIVE",
            tier="ENTERPRISE",
        )
        db.add(org_b)
        db.flush()
        db.add_all(
            [
                OrganizationMembership(
                    id=uuid.uuid4(),
                    tenant_id=tenant_b_id,
                    user_id=user_b_id,
                    role_id=ROLE_ORG_OWNER_ID,
                    status="ACTIVE",
                ),
                Workspace(
                    id=ws_b_id,
                    tenant_id=tenant_b_id,
                    slug="ws-b",
                    name="Workspace B",
                ),
            ]
        )

    # Negative Test 1, 2, 3: From Tenant B's RLS session, reading, updating, or deleting Tenant A's records must affect 0 rows
    with tenant_db_session(tenant_b_id) as db:
        leaked_proj = db.execute(
            select(Project).where(Project.id == proj_a_id)
        ).scalar_one_or_none()
        assert leaked_proj is None

        upd_res = db.execute(
            update(Project)
            .where(Project.id == proj_a_id)
            .values(name="HACKED BY TENANT B")
        )
        assert upd_res.rowcount == 0

        del_res = db.execute(delete(Project).where(Project.id == proj_a_id))
        assert del_res.rowcount == 0

    # Verify Tenant A's project is completely untouched
    with tenant_db_session(tenant_a_id) as db:
        intact_proj = db.execute(
            select(Project).where(Project.id == proj_a_id)
        ).scalar_one()
        assert intact_proj.name == "Secret Project A"

    # Negative Test 4: Creating a record with a foreign key pointing to another tenant's workspace
    with pytest.raises((IntegrityError, ProgrammingError)):
        with tenant_db_session(tenant_b_id) as db:
            bad_proj = Project(
                id=uuid.uuid4(),
                tenant_id=tenant_b_id,
                workspace_id=ws_a_id,  # Belongs to Tenant A!
                key="CROSSFK",
                name="Cross Tenant FK Attempt",
            )
            db.add(bad_proj)
            db.flush()

    # Negative Test 5: Unauthorized project access by a user in Tenant A who is NOT in Project A's memberships
    with SessionLocal() as db:
        ctx_limited = verify_and_activate_tenant_context(
            db, user_id=user_a_limited_id, tenant_id=tenant_a_id
        )
        with pytest.raises(SecurityViolationError, match="does not have membership in project"):
            verify_project_access(
                db, tenant_context=ctx_limited, project_id=proj_a_id
            )

    # Negative Test 6: Missing tenant context fails closed under `legacyiq_app`
    with SessionLocal() as db:
        activate_unscoped_rls_role(db)
        visible_orgs = db.execute(select(Organization)).scalars().all()
        visible_projs = db.execute(select(Project)).scalars().all()
        assert visible_orgs == []
        assert visible_projs == []

    # Negative Test 7: Pooled connection context reset across transactions
    with SessionLocal() as db:
        current_tid = db.execute(
            text("SELECT COALESCE(current_setting('app.current_tenant_id', true), '')")
        ).scalar_one()
        assert current_tid == ""


def test_end_to_end_zip_ingestion_code_intelligence_and_hybrid_rrf_search(
    tmp_path: Path,
) -> None:
    os.environ["LEGACYIQ_DETERMINISTIC_EMBEDDINGS"] = "1"
    suffix = uuid.uuid4().hex[:8]
    tenant_a_id = uuid.uuid4()
    tenant_b_id = uuid.uuid4()
    user_a_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    app_id = uuid.uuid4()
    repo_id = uuid.uuid4()

    with SessionLocal() as db:
        # Also verify bootstrap_default_context works cleanly
        boot = bootstrap_default_context(db)
        assert boot.project_key == "CORE"

        db.add(
            User(
                id=user_a_id,
                email=f"ingest-{suffix}@test.local",
                full_name="Ingest Architect",
            )
        )
        db.commit()

    with tenant_db_session(tenant_a_id) as db:
        db.add(
            Organization(
                id=tenant_a_id,
                slug=f"ingest-org-{suffix}",
                display_name=f"Ingest Org {suffix}",
                status="ACTIVE",
                tier="ENTERPRISE",
            )
        )
        db.flush()
        db.add(
            OrganizationMembership(
                id=uuid.uuid4(),
                tenant_id=tenant_a_id,
                user_id=user_a_id,
                role_id=ROLE_ORG_OWNER_ID,
                status="ACTIVE",
            )
        )
        db.add(
            Workspace(
                id=ws_id,
                tenant_id=tenant_a_id,
                slug="ingest-ws",
                name="Ingest Workspace",
            )
        )
        db.flush()
        db.add(
            Project(
                id=proj_id,
                tenant_id=tenant_a_id,
                workspace_id=ws_id,
                key="INGEST",
                name="Legacy Billing System",
            )
        )
        db.flush()
        db.add(
            Application(
                id=app_id,
                tenant_id=tenant_a_id,
                project_id=proj_id,
                code="billing-app",
                name="Billing Application",
                criticality_tier="TIER_1",
                primary_languages=["python", "java"],
            )
        )
        db.flush()
        db.add(
            Repository(
                id=repo_id,
                tenant_id=tenant_a_id,
                application_id=app_id,
                name="billing-monolith",
                source_type="ZIP_ARCHIVE",
                default_branch="main",
                status="REGISTERED",
            )
        )

    # Build a multi-language ZIP archive in memory
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr(
            "billing/tax_engine.py",
            "class BaseTaxRule:\n"
            "    def base_rate(self) -> float:\n"
            "        return 0.05\n\n"
            "class VatTaxCalculator(BaseTaxRule):\n"
            '    """Calculates European value-added tax for cross-border invoices."""\n'
            "    def calculate_vat_liability(self, net_amount: float) -> float:\n"
            "        return net_amount * self.base_rate()\n",
        )
        zf.writestr(
            "billing/invoice_runner.py",
            "from billing.tax_engine import VatTaxCalculator\n\n"
            "def process_monthly_settlement(subtotal: float) -> float:\n"
            "    calc = VatTaxCalculator()\n"
            "    return calc.calculate_vat_liability(subtotal)\n",
        )
        zf.writestr(
            "java/com/acme/PaymentLedger.java",
            "package com.acme;\n"
            "public class PaymentLedger {\n"
            "    public boolean reconcileSettlementBatch(String batchId) {\n"
            "        return true;\n"
            "    }\n"
            "}\n",
        )
        zf.writestr(
            "docs/architecture.md",
            "# Legacy Billing Architecture\n"
            "The VAT tax liability calculation runs inside `VatTaxCalculator`.\n",
        )

    raw_zip = zip_buf.getvalue()
    storage = TenantObjectStorage(vault_root=tmp_path)
    ingest_svc = IngestionService(storage=storage)
    retrieval_svc = RetrievalService(storage=storage)

    with tenant_db_session(tenant_a_id) as db:
        ctx_a = verify_and_activate_tenant_context(
            db, user_id=user_a_id, tenant_id=tenant_a_id
        )
        outcome1 = ingest_svc.ingest_zip_archive(
            db,
            tenant_id=tenant_a_id,
            project_id=proj_id,
            repository_id=repo_id,
            zip_bytes=raw_zip,
            snapshot_label="v1.0-initial",
            triggered_by_user_id=user_a_id,
            run_analysis_and_indexing=True,
        )
        assert outcome1.is_duplicate_snapshot is False
        assert outcome1.files_processed == 4
        assert outcome1.analysis_run_id is not None
        assert outcome1.chunks_indexed > 0

        # Verify extracted code symbols, call edges, type hierarchies, and imports
        symbols = (
            db.execute(
                select(CodeSymbol).where(
                    CodeSymbol.snapshot_id == outcome1.snapshot_id
                )
            )
            .scalars()
            .all()
        )
        sym_names = {s.name for s in symbols}
        assert {
            "BaseTaxRule",
            "base_rate",
            "VatTaxCalculator",
            "calculate_vat_liability",
            "process_monthly_settlement",
            "PaymentLedger",
            "reconcileSettlementBatch",
        }.issubset(sym_names)

        hierarchies = (
            db.execute(
                select(CodeTypeHierarchy).where(
                    CodeTypeHierarchy.snapshot_id == outcome1.snapshot_id
                )
            )
            .scalars()
            .all()
        )
        assert len(hierarchies) >= 1

        call_edges = (
            db.execute(
                select(CodeCallEdge).where(
                    CodeCallEdge.snapshot_id == outcome1.snapshot_id
                )
            )
            .scalars()
            .all()
        )
        assert len(call_edges) >= 1

        # Verify API endpoint handlers for code intelligence
        summary_resp = get_code_summary(
            project_id=proj_id, snapshot_id=outcome1.snapshot_id, deps=(db, ctx_a)
        )
        assert summary_resp.total_files == 3
        assert summary_resp.total_symbols >= 7

        files_resp = list_code_files(
            project_id=proj_id,
            snapshot_id=outcome1.snapshot_id,
            language=None,
            limit=50,
            offset=0,
            deps=(db, ctx_a),
        )
        assert len(files_resp) == 3

        syms_resp = list_code_symbols(
            project_id=proj_id,
            snapshot_id=outcome1.snapshot_id,
            code_file_id=None,
            symbol_kind=None,
            q="VatTax",
            limit=50,
            offset=0,
            deps=(db, ctx_a),
        )
        assert len(syms_resp) >= 1

        edges_resp = list_code_call_edges(
            project_id=proj_id,
            snapshot_id=outcome1.snapshot_id,
            limit=50,
            deps=(db, ctx_a),
        )
        assert len(edges_resp) >= 1

        hier_resp = list_code_type_hierarchies(
            project_id=proj_id,
            snapshot_id=outcome1.snapshot_id,
            limit=50,
            deps=(db, ctx_a),
        )
        assert len(hier_resp) >= 1

        imports_resp = list_code_imports(
            project_id=proj_id,
            snapshot_id=outcome1.snapshot_id,
            source_file_id=None,
            limit=50,
            deps=(db, ctx_a),
        )
        assert len(imports_resp) >= 1

        refs_resp = list_code_references(
            project_id=proj_id,
            snapshot_id=outcome1.snapshot_id,
            target_symbol_id=None,
            limit=50,
            deps=(db, ctx_a),
        )
        assert len(refs_resp) >= 1

        # Verify idempotent re-upload of identical ZIP archive
        outcome2 = ingest_svc.ingest_zip_archive(
            db,
            tenant_id=tenant_a_id,
            project_id=proj_id,
            repository_id=repo_id,
            zip_bytes=raw_zip,
            snapshot_label="v1.0-reupload",
            triggered_by_user_id=user_a_id,
            run_analysis_and_indexing=True,
        )
        assert outcome2.is_duplicate_snapshot is True
        assert outcome2.snapshot_id == outcome1.snapshot_id

        # Execute Hybrid RRF search in Tenant A via service and API handler
        hits_a = retrieval_svc.hybrid_search(
            db,
            tenant_id=tenant_a_id,
            project_id=proj_id,
            snapshot_id=outcome1.snapshot_id,
            query_text="calculate_vat_liability cross-border invoices",
            limit=5,
        )
        assert len(hits_a) >= 1
        top_paths = {h.relative_path for h in hits_a}
        assert "billing/tax_engine.py" in top_paths

        api_search_resp = post_hybrid_search(
            HybridSearchRequest(
                project_id=proj_id,
                snapshot_id=outcome1.snapshot_id,
                query="calculate_vat_liability cross-border invoices",
                limit=5,
            ),
            deps=(db, ctx_a),
        )
        assert api_search_resp.total_hits >= 1

    # Cross-tenant search isolation: Tenant B searching for Tenant A's symbols must return 0 hits
    with tenant_db_session(tenant_b_id) as db:
        hits_b = retrieval_svc.hybrid_search(
            db,
            tenant_id=tenant_b_id,
            project_id=proj_id,
            snapshot_id=outcome1.snapshot_id,
            query_text="calculate_vat_liability cross-border invoices",
            limit=5,
        )
        assert hits_b == []
