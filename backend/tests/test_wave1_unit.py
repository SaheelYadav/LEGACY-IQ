"""Stage 1, 2, 3, 4, 5, and 6 deterministic unit tests (no network required)."""

from __future__ import annotations

import io
from pathlib import Path
import uuid
import zipfile

import pytest
from sqlalchemy.orm import configure_mappers

from app.analysis.parser_registry import (
     compute_normalized_ast_hash,
    default_parser_registry,
    detect_language_and_kind,
)
from app.core.security import TaskEnvelope, build_tenant_cache_key
from app.db.base import Base
from app.integrations.storage import TenantObjectStorage
from app.main import app as fastapi_app
import app.models  # noqa: F401
from app.services.ingestion_service import ArchiveValidationError, IngestionService
from app.services.retrieval_service import _deterministic_hash_embedding


def test_wave1_33_canonical_models_and_mappers() -> None:
    configure_mappers()
    tables = set(Base.metadata.tables.keys())
    assert len(tables) >= 33
    expected_Wave1_tables = {
        "organizations",
        "users",
        "roles",
        "permissions",
        "role_permissions",
        "organization_memberships",
        "teams",
        "team_memberships",
        "workspaces",
        "projects",
        "project_memberships",
        "applications",
        "application_environments",
        "analysis_scopes",
        "source_connectors",
        "repositories",
        "repository_branches",
        "repository_commits",
        "repository_snapshots",
        "artifacts",
        "artifact_versions",
        "ingestion_jobs",
        "analysis_runs",
        "code_modules",
        "code_files",
        "code_symbols",
        "code_imports",
        "code_call_edges",
        "code_type_hierarchies",
        "code_symbol_references",
        "embedding_model_versions",
        "document_chunks",
        "artifact_embeddings",
    }
    assert expected_Wave1_tables.issubset(tables)


def test_wave1_api_v1_routes_registered() -> None:
    paths = set(fastapi_app.openapi()["paths"].keys())
    expected_paths = {
        "/api/v1/health",
        "/api/v1/health/database",
        "/api/v1/health/redis",
        "/api/v1/health/ollama",
        "/api/v1/bootstrap",
        "/api/v1/organizations",
        "/api/v1/organizations/current",
        "/api/v1/organizations/{tenant_id}/memberships",
        "/api/v1/workspaces",
        "/api/v1/projects",
        "/api/v1/projects/{project_id}",
        "/api/v1/projects/{project_id}/memberships",
        "/api/v1/applications",
        "/api/v1/repositories",
        "/api/v1/repositories/{repository_id}/upload-zip",
        "/api/v1/repositories/{repository_id}/snapshots",
        "/api/v1/snapshots",
        "/api/v1/ingestion-jobs",
        "/api/v1/ingestion-jobs/{job_id}",
        "/api/v1/code/summary",
        "/api/v1/code/files",
        "/api/v1/code/symbols",
        "/api/v1/code/imports",
        "/api/v1/code/call-edges",
        "/api/v1/code/type-hierarchies",
        "/api/v1/code/references",
        "/api/v1/search/hybrid",
    }
    assert expected_paths.issubset(paths)


def test_tenant_cache_key_and_signed_task_envelope() -> None:
    tid = uuid.uuid4()
    pid = uuid.uuid4()
    uid = uuid.uuid4()
    key = build_tenant_cache_key(tid, "code_summary", "snap-1", project_id=pid)
    assert f":t:{tid}:p:{pid}:code_summary:snap-1" in key

    env = TaskEnvelope.create(
        tenant_id=tid,
        project_id=pid,
        actor_user_id=uid,
        task_type="INGEST_SNAPSHOT",
        payload={"snapshot_id": "123"},
    )
    assert env.verify() is True

    # Tampering with tenant_id must invalidate HMAC signature
    tampered = TaskEnvelope(
        task_id=env.task_id,
        tenant_id=str(uuid.uuid4()),
        project_id=env.project_id,
        actor_user_id=env.actor_user_id,
        task_type=env.task_type,
        payload=env.payload,
        issued_at=env.issued_at,
        signature=env.signature,
    )
    assert tampered.verify() is False


def test_tenant_object_storage_isolation(tmp_path: Path) -> None:
    storage = TenantObjectStorage(vault_root=tmp_path)
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    payload = b"def calculate_interest(principal: float): return principal * 0.05\n"

    blob_a = storage.put_blob(tenant_a, payload)
    assert storage.blob_exists(tenant_a, blob_a.sha256) is True
    # Tenant B must NOT see Tenant A's blob even for identical SHA-256 content
    assert storage.blob_exists(tenant_b, blob_a.sha256) is False
    with pytest.raises(FileNotFoundError):
        storage.get_blob_bytes(tenant_b, blob_a.sha256)


def test_multi_language_parsers_python_java_js_ts_php() -> None:
    # 1. Python
    py_src = (
        "import math\n"
        "from app.billing import BaseCalculator\n\n"
        "MAX_RATE = 0.25\n\n"
        "class InvoiceService(BaseCalculator):\n"
        '    """Handles customer invoices."""\n'
        "    def compute_tax(self, amount: float) -> float:\n"
        "        if amount <= 0:\n"
        "            return 0.0\n"
        "        return self.round_currency(amount * MAX_RATE)\n"
        "    def round_currency(self, val: float) -> float:\n"
        "        return round(val, 2)\n"
    )
    py_res = default_parser_registry.parse_file("billing/invoice.py", "python", py_src)
    assert py_res.parse_status == "PARSED"
    py_sym_names = {s.symbol_name for s in py_res.symbols}
    assert {"MAX_RATE", "InvoiceService", "compute_tax", "round_currency"} == py_sym_names
    assert len(py_res.imports) == 2

    # 2. Java
    java_src = (
        "package com.acme.orders;\n"
        "import java.math.BigDecimal;\n"
        "public class OrderProcessor extends BaseProcessor implements Auditable {\n"
        "    public BigDecimal authorizePayment(String orderId) {\n"
        "        validateOrder(orderId);\n"
        "        return BigDecimal.TEN;\n"
        "    }\n"
        "}\n"
    )
    java_res = default_parser_registry.parse_file("src/OrderProcessor.java", "java", java_src)
    assert java_res.parse_status == "PARSED"
    assert {s.symbol_name for s in java_res.symbols} == {"OrderProcessor", "authorizePayment"}
    assert java_res.symbols[0].base_types == [
        ("BaseProcessor", "EXTENDS"),
        ("Auditable", "IMPLEMENTS"),
    ]

    # 3. TypeScript
    ts_src = (
        "import { LedgerClient } from './ledger';\n"
        "export class PaymentGateway extends BaseGateway {\n"
        "    public async settleTransaction(txId: string): Promise<boolean> {\n"
        "        return verifySignature(txId);\n"
        "    }\n"
        "}\n"
    )
    ts_res = default_parser_registry.parse_file("src/gateway.ts", "typescript", ts_src)
    assert ts_res.parse_status == "PARSED"
    assert {s.symbol_name for s in ts_res.symbols} == {"PaymentGateway", "settleTransaction"}
    assert len(ts_res.imports) == 1

    # 4. JavaScript
    js_src = (
        "import { formatCurrency } from './utils.js';\n"
        "export function calculateDiscount(subtotal) {\n"
        "    if (subtotal > 100) {\n"
        "        return formatCurrency(subtotal * 0.9);\n"
        "    }\n"
        "    return formatCurrency(subtotal);\n"
        "}\n"
    )
    js_res = default_parser_registry.parse_file("src/discount.js", "javascript", js_src)
    assert js_res.parse_status == "PARSED"
    assert {s.symbol_name for s in js_res.symbols} == {"calculateDiscount"}

    # 5. PHP
    php_src = (
        "<?php\n"
        "namespace Acme\\Legacy\\Billing;\n"
        "use Acme\\Common\\Logger;\n"
        "class LedgerController extends BaseController {\n"
        "    public function postEntry($accountId, $amount) {\n"
        "        $this->auditEntry($accountId);\n"
        "        return true;\n"
        "    }\n"
        "}\n"
    )
    php_res = default_parser_registry.parse_file("app/LedgerController.php", "php", php_src)
    assert php_res.parse_status == "PARSED"
    assert {s.symbol_name for s in php_res.symbols} == {"LedgerController", "postEntry"}


def test_python_parser_syntax_error_handled_gracefully() -> None:
    broken_py = "def broken_func(:\n    pass\n"
    res = default_parser_registry.parse_file("broken.py", "python", broken_py)
    assert res.parse_status == "PARSE_ERROR"
    assert res.error_message is not None


def test_zip_ingestion_security_guards(tmp_path: Path) -> None:
    svc = IngestionService(
        storage=TenantObjectStorage(vault_root=tmp_path),
        max_file_count=5,
        max_single_file_bytes=2048,
        max_total_uncompressed_bytes=4096,
    )

    # 1. Empty payload
    with pytest.raises(ArchiveValidationError, match="empty"):
        svc.validate_and_inspect_zip(b"")

    # 2. Invalid non-zip bytes
    with pytest.raises(ArchiveValidationError, match="Invalid or corrupted ZIP"):
        svc.validate_and_inspect_zip(b"not a zip archive")

    # 3. Zip-Slip path traversal
    buf_slip = io.BytesIO()
    with zipfile.ZipFile(buf_slip, "w") as zf:
        zf.writestr("../../etc/passwd", "root:x:0:0")
    with pytest.raises(ArchiveValidationError, match="unsafe archive path"):
        svc.validate_and_inspect_zip(buf_slip.getvalue())

    # 4. Symlink entry
    buf_sym = io.BytesIO()
    with zipfile.ZipFile(buf_sym, "w") as zf:
        info = zipfile.ZipInfo("link.py")
        info.external_attr = (0o120777) << 16
        zf.writestr(info, "/etc/shadow")
    with pytest.raises(ArchiveValidationError, match="symbolic link"):
        svc.validate_and_inspect_zip(buf_sym.getvalue())

    # 5. File count overflow
    buf_many = io.BytesIO()
    with zipfile.ZipFile(buf_many, "w") as zf:
        for i in range(7):
            zf.writestr(f"file_{i}.py", f"X = {i}\n")
    with pytest.raises(ArchiveValidationError, match="maximum allowed file count"):
        svc.validate_and_inspect_zip(buf_many.getvalue())

    # 6. Single-file size overflow
    buf_big = io.BytesIO()
    with zipfile.ZipFile(buf_big, "w") as zf:
        zf.writestr("huge.py", "a = 1\n" * 600)
    with pytest.raises(ArchiveValidationError, match="exceeds per-file limit"):
        svc.validate_and_inspect_zip(buf_big.getvalue())


def test_deterministic_384d_embedding_properties() -> None:
    vec1 = _deterministic_hash_embedding("calculate loan amortization schedule", dim=384)
    vec2 = _deterministic_hash_embedding("calculate loan amortization schedule", dim=384)
    assert len(vec1) == 384
    assert vec1 == vec2
    norm_sq = sum(x * x for x in vec1)
    assert 0.99 <= norm_sq <= 1.01
