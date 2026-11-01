# LegacyIQ — Wave 7 Database Backup, Restore & Disaster Recovery Runbook

**Phase:** Wave 7 — Production Hardening & Deployment Readiness (Phase D)  
**Date:** 2026-11-01  
**Database Engine:** PostgreSQL 17.11 with `pgvector 0.8.7`  
**Verification Status:** **VERIFIED (`legacyiq` -> `legacyiq_wave7_restore_test`)**

---

## 1. Executive Summary

This runbook documents and verifies the non-destructive logical backup, isolated restore validation, object storage backup, retention, encryption, and forward-fix migration recovery procedures for the LegacyIQ enterprise application intelligence platform.

During Wave 7 Phase D, a live logical backup of the active `legacyiq` PostgreSQL database was captured and restored into an isolated verification database (`legacyiq_wave7_restore_test`) inside the `legacyiq-postgres` container—leaving the primary `legacyiq` database and all persisted tenant data 100% untouched.

---

## 2. Live Backup & Isolated Restore Verification Telemetry (Wave 7 Phase D)

Executed and verified automatically via [`test_wave7_phase_d_postgresql_backup_and_isolated_restore_verification`](file:///C:/LegacyIQ/backend/tests/test_wave7_production_hardening.py):

| Verification Metric | Measured Value | Status |
|---|---|---|
| **Verification Timestamp (UTC)** | `2026-11-01T09:59:11.846432+00:00` | `VERIFIED` |
| **Source Database** | `legacyiq` (untouched) | `VERIFIED` |
| **Isolated Target Restore Database** | `legacyiq_wave7_restore_test` | `VERIFIED` |
| **Logical Dump Size (`pg_dump`)** | `14,172,527 bytes` (`~13.52 MB`) | `VERIFIED` |
| **Backup Execution Time (`pg_dump`)** | `1,580.71 ms` (`1.58 s`) | `VERIFIED` |
| **Isolated Restore Execution Time (`psql`)** | `3,369.72 ms` (`3.37 s`) | `VERIFIED` |
| **Restored `pgvector` Extension Version** | `0.8.7` (`vector(384)` HNSW index intact) | `VERIFIED` |
| **Restored Canonical Tables Count** | `76` (100% match with production schema) | `VERIFIED` |
| **Restored `FORCE ROW LEVEL SECURITY` Tables** | `72` (100% match with D3 security architecture) | `VERIFIED` |
| **Restored Alembic Revision Head** | `0007_wave5_qa_reports_export` | `VERIFIED` |

---

## 3. PostgreSQL Logical Backup Procedure (`pg_dump`)

### 3.1 Pre-Backup Checklist
1. Confirm PostgreSQL and `pgvector` health via `/api/v1/health/database`.
2. Confirm sufficient disk space (`free_gb >= 5.0`) via `/api/v1/health/storage`.
3. Confirm current Alembic revision head matches `0007_wave5_qa_reports_export`.

### 3.2 Executing a Logical Backup (Zero-Downtime Online Dump)
`pg_dump` runs inside a single repeatable-read snapshot transaction and does not block concurrent tenant reads or writes.

```powershell
# 1. Create timestamped backup directory
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force -Path "C:\LegacyIQ-backups\postgres" | Out-Null

# 2. Run online logical backup from legacyiq-postgres container
docker exec legacyiq-postgres pg_dump `
  -U legacyiq_admin `
  -d legacyiq `
  --no-owner `
  --no-privileges `
  > "C:\LegacyIQ-backups\postgres\legacyiq_${Timestamp}.sql"

# 3. Compute SHA-256 integrity checksum
Get-FileHash "C:\LegacyIQ-backups\postgres\legacyiq_${Timestamp}.sql" -Algorithm SHA256 `
  | Select-Object Hash, Path `
  | Set-Content "C:\LegacyIQ-backups\postgres\legacyiq_${Timestamp}.sql.sha256"
```

---

## 4. Isolated Restore & Verification Procedure

> [!IMPORTANT]
> Never restore directly over the active `legacyiq` database without first validating the backup in an isolated verification database (`legacyiq_restore_verify`).

### 4.1 Step-by-Step Isolated Restore
```powershell
# 1. Verify SHA-256 checksum of backup file before restore
Get-FileHash "C:\LegacyIQ-backups\postgres\legacyiq_${Timestamp}.sql" -Algorithm SHA256

# 2. Ensure application runtime role `legacyiq_app` exists on target cluster
docker exec legacyiq-postgres psql -U legacyiq_admin -d postgres -v ON_ERROR_STOP=1 -c "
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'legacyiq_app') THEN
    CREATE ROLE legacyiq_app NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
END
\$\$;"

# 3. Create isolated restore database
docker exec legacyiq-postgres psql -U legacyiq_admin -d postgres -v ON_ERROR_STOP=1 `
  -c "CREATE DATABASE legacyiq_restore_verify;"

# 4. Restore logical SQL dump into isolated database
Get-Content "C:\LegacyIQ-backups\postgres\legacyiq_${Timestamp}.sql" -Raw | `
  docker exec -i legacyiq-postgres psql -U legacyiq_admin -d legacyiq_restore_verify -v ON_ERROR_STOP=1
```

### 4.2 Post-Restore Verification Queries (`pgvector`, Tables, RLS, Alembic Head)
Run the following verification query against `legacyiq_restore_verify` and confirm the output matches `0.8.7|76|72|0007_wave5_qa_reports_export`:

```powershell
docker exec legacyiq-postgres psql -U legacyiq_admin -d legacyiq_restore_verify -t -A -c "
SELECT
  (SELECT extversion FROM pg_extension WHERE extname = 'vector') AS vec_ver,
  (SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tablename != 'alembic_version') AS tbl_count,
  (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity = true AND c.relforcerowsecurity = true) AS rls_count,
  (SELECT version_num FROM alembic_version LIMIT 1) AS alembic_rev;
"
```

### 4.3 Cleanup Isolated Verification Database
```powershell
docker exec legacyiq-postgres psql -U legacyiq_admin -d postgres -v ON_ERROR_STOP=1 `
  -c "DROP DATABASE IF EXISTS legacyiq_restore_verify WITH (FORCE);"
```

---

## 5. Tenant Object Storage Vault Backup & Restore

LegacyIQ stores content-addressed source archives, extracted files, and generated report exports (`PDF`, `DOCX`, `XLSX`, `JSON`) under `STORAGE_VAULT_ROOT` (`backend/.storage_vault/<tenant_id>/<sha256[:2]>/<sha256>`).

### 5.1 Consistent Backup Ordering
Always back up PostgreSQL **first**, then back up `STORAGE_VAULT_ROOT` immediately afterward. Because `TenantObjectStorage` is content-addressed by SHA-256 and immutable (blobs are never overwritten in place), backing up the vault after `pg_dump` guarantees that every `storage_object_key` referenced in `artifacts`, `artifact_versions`, and `report_exports` is present in the vault archive.

```powershell
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force -Path "C:\LegacyIQ-backups\vault" | Out-Null
Compress-Archive `
  -Path "C:\LegacyIQ\backend\.storage_vault\*" `
  -DestinationPath "C:\LegacyIQ-backups\vault\storage_vault_${Timestamp}.zip" `
  -CompressionLevel Optimal
```

---

## 6. Backup Retention, Encryption & Failed Migration Recovery

### 6.1 Retention Policy
| Backup Tier | Frequency | Retention Period | Storage Location |
|---|---|---|---|
| **Pre-Deployment / Pre-Migration Snapshot** | Prior to every `alembic upgrade` | 90 days | Local backup volume + off-host encrypted storage |
| **Daily Operational Backup** | Every 24 hours (`02:00 UTC`) | 30 days | Off-host encrypted object storage |
| **Weekly Compliance Archive** | Every Sunday (`03:00 UTC`) | 1 year | Cold immutable archive storage |

### 6.2 Backup Encryption Recommendations
- Encrypt all logical SQL dumps and storage vault archives at rest using AES-256 (`age`, `gpg --cipher-algo AES256`, or KMS-managed envelope encryption) before transferring off-host.
- Store encryption keys separately from backup archives in an enterprise secret manager.

### 6.3 Failed Migration Rollback & Forward-Fix Policy
1. **Mandatory Pre-Migration Backup**: Always execute Section 3.2 (`pg_dump`) immediately before running `alembic upgrade head`.
2. **Transactional DDL**: PostgreSQL executes Alembic migration scripts inside a transaction; if a statement fails mid-migration, PostgreSQL automatically rolls back the uncommitted DDL transaction.
3. **Forward-Fix vs. Restore**:
   - If a migration fails and rolls back cleanly, fix the migration script in staging and re-run `alembic upgrade head`.
   - If data corruption occurs after a committed migration, restore the pre-migration backup into a new database, verify `76` tables and `72` `FORCE RLS` policies per Section 4.2, and switch the application connection to the verified restored database. Never run destructive `DROP SCHEMA` or `alembic downgrade base` on production data.

