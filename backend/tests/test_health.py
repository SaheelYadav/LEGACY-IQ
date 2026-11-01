"""M0 Foundation unit and endpoint verification tests."""

from pathlib import Path

from fastapi import Response
import pytest

from app.analysis.ast_analyzer import parse_python_symbols_safely
from app.analysis.graph_builder import DependencyGraphBuilder
from app.api.v1.endpoints.health import (
    check_app_health,
    check_database_health,
    check_redis_health_endpoint,
)
from app.core.config import mask_connection_url, settings
from app.core.security import validate_safe_extract_path
from app.main import app


def test_fastapi_app_routes_registered() -> None:
    registered_paths = set(app.openapi()["paths"].keys())
    assert "/api/v1/health" in registered_paths
    assert "/api/v1/health/database" in registered_paths
    assert "/api/v1/health/redis" in registered_paths
    assert "/api/v1/health/ollama" in registered_paths


def test_app_health_endpoint_handler() -> None:
    payload = check_app_health()
    assert payload.status == "healthy"
    assert payload.app_name == "LegacyIQ"
    assert payload.milestone == "M0"


def test_unconfigured_db_and_redis_report_truthfully() -> None:
    if not settings.is_database_configured:
        db_resp = Response()
        db_health = check_database_health(db_resp)
        assert db_health.status == "unconfigured"
        assert db_resp.status_code == 503

    if not settings.is_redis_configured:
        redis_resp = Response()
        redis_health = check_redis_health_endpoint(redis_resp)
        assert redis_health.status == "unconfigured"
        assert redis_resp.status_code == 503


def test_url_masking_never_exposes_password() -> None:
    raw = "postgresql+psycopg://legacyiq_admin:super_secret_pw@localhost:5432/legacyiq"
    masked = mask_connection_url(raw)
    assert "super_secret_pw" not in masked
    assert "legacyiq_admin:***@localhost:5432" in masked


def test_static_ast_analyzer_and_graph_builder() -> None:
    sample_code = "class OrderService:\n    def calculate_total(self):\n        return 42\n"
    symbols = parse_python_symbols_safely(sample_code)
    names = {s.name for s in symbols}
    assert {"OrderService", "calculate_total"} == names

    builder = DependencyGraphBuilder()
    builder.add_module_node("orders.service", "python")
    builder.add_module_node("orders.models", "python")
    builder.add_dependency_edge("orders.service", "orders.models")
    summary = builder.to_summary_dict()
    assert summary == {"node_count": 2, "edge_count": 1}


def test_zip_slip_path_traversal_guard(tmp_path: Path) -> None:
    safe_target = tmp_path / "repo" / "main.py"
    validated = validate_safe_extract_path(tmp_path, safe_target)
    assert validated == safe_target.resolve()

    unsafe_target = tmp_path / ".." / "outside.py"
    with pytest.raises(ValueError, match="path traversal"):
        validate_safe_extract_path(tmp_path, unsafe_target)
