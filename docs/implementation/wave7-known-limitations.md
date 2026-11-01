# LegacyIQ — Wave 7 Known Limitations & Operational Boundaries

**Phase:** Wave 7 — Production Hardening & Deployment Readiness  
**Date:** 2026-11-01  
**Status:** Disclosed & Documented

---

## 1. Purpose

In accordance with Wave 7 completion criteria, this document transparently discloses all remaining known limitations, external infrastructure dependencies, and architectural boundaries that are either intentionally deferred beyond the local-first enterprise baseline or require external production infrastructure to activate.

---

## 2. Disclosed Known Limitations

| ID | Area | Status | Description & Technical Context | Mitigation / Production Path |
| :--- | :--- | :---: | :--- | :--- |
| **LIM-01** | **External OIDC / SAML Identity Provider & Password Reset Flows** | `NOT_IMPLEMENTED` | While `users` includes `auth_provider` (`LOCAL` / `OIDC` / `SAML`) and `external_subject_id`, and Wave 7 added HS256 JWT issuance (`POST /api/v1/auth/token`) and verification (`Authorization: Bearer <token>`), interactive OAuth2/OIDC redirect flows, refresh-token rotation tables, and email-based password reset flows are not implemented. | Set `AUTH_ENFORCE_BEARER_TOKEN=true` behind an enterprise API gateway or configure NextAuth/Auth.js or an OIDC reverse proxy that exchanges IdP tokens for LegacyIQ signed JWTs. |
| **LIM-02** | **Distributed Multi-Node Rate Limiting** | `IMPLEMENTED_NOT_VERIFIED` (Single-process verified) | [`SlidingWindowRateLimiter`](file:///C:/LegacyIQ/backend/app/core/security.py) enforces per-tenant/IP sliding-window limits (`120 req/min` default, `20 req/min` expensive endpoints) in process memory. Across multiple Uvicorn worker processes or horizontal pods, each worker maintains its own window unless fronted by an ingress rate limiter or Redis Lua script. | Enforce edge rate limiting at the reverse proxy / ingress controller (NGINX `limit_req_zone` or Cloudflare/ALB WAF) in multi-replica deployments. |
| **LIM-03** | **Synchronous Pipeline Execution Within Upload Request vs. Dedicated Worker Fleet** | `IMPLEMENTED_NOT_VERIFIED` (Signed `TaskEnvelope` verified) | `TaskEnvelope` HMAC-SHA256 signing and `IngestionJob` / `AnalysisRun` state machines are implemented and verified, and repositories up to `50 MB` compressed (`2,500` files) ingest synchronously within `~1.35s` for typical services. However, a separate standalone Celery/RQ consumer process is not launched by default in local mode. | For repositories approaching `50 MB` (`>1,500` files), run a dedicated worker process consuming signed `TaskEnvelope` payloads from Redis (`REDIS_URL`) so HTTP uploads return `202 Accepted` immediately. |
| **LIM-04** | **Local Filesystem Object Storage Vault (`TenantObjectStorage`)** | `VERIFIED` (Single-host) | [`TenantObjectStorage`](file:///C:/LegacyIQ/backend/app/integrations/storage.py) isolates content-addressed blobs under `<STORAGE_VAULT_ROOT>/<tenant_id>/blobs/<sha[:2]>/<sha>`. On a single host or shared POSIX volume (NFS/EFS/ReadWriteMany PVC), this works out of the box. It does not natively use the AWS S3 / GCS HTTP API without mounting or subclassing. | In multi-node container deployments, mount a shared persistent volume at `STORAGE_VAULT_ROOT` with daily encrypted snapshots, or bind an S3-compatible bucket via CSI driver. |
| **LIM-05** | **Offline Dependency Vulnerability Feed (No External Paid CVE API)** | `VERIFIED` (By Design) | To uphold the zero-hallucination and zero-paid-API rule, `RiskIntelligenceService` only flags dependencies matched against deterministic known-vulnerable version ranges or manifest hygiene rules and never fabricates CVE IDs. | Integrate an air-gapped OSV/NVD JSON mirror sync into the risk analyzer if full CVE database coverage is required in production. |
| **LIM-06** | **Remote Ollama Inference Latency on CPU-Only Hosts** | `VERIFIED` | When Ollama (`qwen2.5-coder:3b`) runs on CPU-only infrastructure or is unreachable, LLM calls can time out (`OLLAMA_TIMEOUT_SECONDS=5.0`). LegacyIQ automatically falls back to deterministic evidence-anchored synthesis without failing the pipeline, and logs `is_fallback_invocation=True` in `model_invocations`. | Provision a GPU-enabled internal inference node for `OLLAMA_BASE_URL` in production, or retain the deterministic fallback mode with zero paid API dependency. |
| **LIM-07** | **Public Cloud Deployment Execution** | `BLOCKED` (Requires User Approval & Target Cloud Credentials) | All deployment artifacts, production environment validators, health/readiness probes, and runbooks are prepared and verified locally, but no public cloud deployment has been executed because external cloud credentials and explicit user approval are required. | Provision target PostgreSQL 17 + `pgvector`, Redis 7, and container hosts following [`wave7-deployment-guide.md`](file:///C:/LegacyIQ/docs/implementation/wave7-deployment-guide.md). |

