# LegacyIQ — Wave 7 Operations & Monitoring Guide

**Phase:** Wave 7 — Production Hardening & Deployment Readiness (Phase E)  
**Date:** 2026-11-01  
**Status:** Verified & Operational (`0` Paid Observability Dependencies Required)

---

## 1. Observability Architecture

LegacyIQ provides built-in, local-first operational observability without requiring paid third-party APM agents:

1. **Structured JSON & Redacted Text Logging** ([`backend/app/core/logging.py`](file:///C:/LegacyIQ/backend/app/core/logging.py)):
   - Controlled via `LOG_FORMAT=json|text` and `LOG_LEVEL=DEBUG|INFO|WARNING|ERROR`.
   - Every log line automatically embeds `correlation_id` from `ContextVar("correlation_id")`.
   - [`redact_sensitive_text`](file:///C:/LegacyIQ/backend/app/core/logging.py) automatically strips PostgreSQL/Redis connection passwords (`***REDACTED***`) and `Authorization: Bearer <token>` credentials before writing to `stdout`.
2. **Request Correlation & Security Headers Middleware** ([`backend/app/main.py`](file:///C:/LegacyIQ/backend/app/main.py)):
   - Reads incoming `X-Correlation-Id` (or generates a UUIDv4) and echoes `X-Correlation-Id` on every HTTP response, including `429 Too Many Requests` and sanitized `500 Internal Server Error` payloads.
   - Attaches `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and `X-RateLimit-Remaining`.
3. **Granular & Composite Health / Readiness Probes** ([`backend/app/api/v1/endpoints/health.py`](file:///C:/LegacyIQ/backend/app/api/v1/endpoints/health.py)):
   - `GET /api/v1/health` — Core liveness probe (`status: "healthy"`).
   - `GET /api/v1/health/database` — Verifies PostgreSQL 17 connectivity, `pgvector` extension version (`0.8.7`), and target embedding dimensionality (`384`). Returns HTTP `503` if unconfigured or unreachable.
   - `GET /api/v1/health/redis` — Verifies Redis connectivity via `PING -> PONG`. Returns HTTP `503` if unconfigured or unreachable.
   - `GET /api/v1/health/ollama` — Verifies Ollama reachability (`GET /api/tags`) and checks whether `OLLAMA_MODEL` (`qwen2.5-coder:3b`) is installed.
   - `GET /api/v1/health/storage` — Verifies `STORAGE_VAULT_ROOT` accessibility, tenant vault count, total/used/free disk GB, and free disk percentage (`disk_free_pct`).
   - `GET /api/v1/health/readiness` — Composite readiness probe combining Database, Redis, Storage, Ollama (with `deterministic_fallback_enabled: true`), and `validate_production_readiness()` configuration checks.

---

## 2. Job, Agent & Export Telemetry Visibility

All background and pipeline operations persist structured status and failure diagnostics in PostgreSQL under tenant RLS:

| Operational Domain | Database Tables | Inspection API Endpoint | Key Status & Failure Fields |
| :--- | :--- | :--- | :--- |
| **ZIP Archive Ingestion** | `ingestion_jobs`, `repository_snapshots` | `GET /api/v1/ingestion-jobs?project_id=<uuid>` & `GET /api/v1/ingestion-jobs/{job_id}` | `status` (`QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`), `stage`, `progress_pct`, `files_processed`, `bytes_processed`, `error_message` |
| **Static & Multi-Wave Analysis** | `analysis_runs` | `GET /api/v1/code/summary?project_id=<uuid>` | `status`, `started_at`, `completed_at`, `summary_metrics` |
| **AI Agent Orchestration & Model Fallback** | `agent_runs`, `agent_task_dependencies`, `model_invocations`, `agent_execution_events` | `GET /api/v1/snapshots/{snapshot_id}/agents` | `attempt_count`, `is_fallback_invocation` (`true` when Ollama times out and deterministic synthesis takes over), `latency_ms`, `status`, `rejected_unanchored_count` |
| **Controlled Report Exports** | `report_exports`, `audit_logs` | `GET /api/v1/snapshots/{snapshot_id}/exports` | `status` (`COMPLETED`, `FAILED`), `export_format`, `file_size_bytes`, `content_sha256`, `download_count`, `audit_log_id` |
| **Tamper-Evident Security Audit Trail** | `audit_logs` | `GET /api/v1/organizations/{tenant_id}/audit-logs` | `action_code` (`REPORT_APPROVED`, `EXPORT_GENERATED`, `EXPORT_DOWNLOADED`), `prev_audit_hash`, `entry_hash` |

---

## 3. Timeout, Retry & Graceful Shutdown Behavior

1. **Database Timeouts & Connection Pool Recycling**:
   - `DB_CONNECT_TIMEOUT_SECONDS=3` bounds TCP connection establishment.
   - `DB_STATEMENT_TIMEOUT_MS=30000` (`30s`) prevents runaway SQL queries from holding pooled connections.
   - `pool_pre_ping=True` and `DB_POOL_RECYCLE_SECONDS=1800` automatically discard stale connections.
2. **Redis Timeouts**:
   - `REDIS_CONNECT_TIMEOUT_SECONDS=3.0` bounds both `socket_connect_timeout` and `socket_timeout`.
3. **Ollama Inference Timeouts & Retry Policy**:
   - `OLLAMA_TIMEOUT_SECONDS=5.0` bounds HTTP requests to Ollama.
   - [`TechnicalIntelligenceOrchestrator`](file:///C:/LegacyIQ/backend/app/services/agent_orchestrator.py) retries transient schema/model failures up to `max_retries=2` (`attempt_count` recorded on `AgentRun`), then seamlessly falls back to deterministic evidence synthesis (`is_fallback_invocation=True`) so user workflows never stall.
4. **Graceful Shutdown**:
   - On `SIGTERM` / `SIGINT`, FastAPI's `lifespan` context manager in [`backend/app/main.py`](file:///C:/LegacyIQ/backend/app/main.py) logs shutdown and calls `engine.dispose()` to cleanly close all pooled PostgreSQL connections.

---

## 4. Operational Alerting Thresholds & Triage Playbook

Configure your container orchestrator or local cron health monitor to poll `GET /api/v1/health/readiness` every `30 seconds`:

- **Alert Condition 1: `checks.database.status != "healthy"` (Critical)**
  - **Action**: Verify `legacyiq-postgres` container status, check connection pool saturation (`SELECT count(*) FROM pg_stat_activity WHERE datname='legacyiq'`), and verify `pg_extension` contains `vector`.
- **Alert Condition 2: `checks.storage.details.disk_free_pct < 15.0` (Warning) / `< 5.0` (Critical)**
  - **Action**: Expand the volume backing `STORAGE_VAULT_ROOT` or archive old snapshots not under `legal_hold_active`.
- **Alert Condition 3: HTTP `429 Too Many Requests` Spike**
  - **Action**: Inspect structured logs by `correlation_id` to identify whether a tenant is running automated bulk uploads or hitting `RATE_LIMIT_EXPENSIVE_PER_MINUTE` (`20 req/min`).

