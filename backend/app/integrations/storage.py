"""Tenant-isolated content-addressed object storage adapter for Wave 1."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Any

from app.core.config import settings
from app.core.security import validate_safe_extract_path

DEFAULT_VAULT_ROOT = Path(settings.STORAGE_VAULT_ROOT).resolve()


@dataclass(frozen=True)
class StoredBlob:
    """Metadata returned when a blob is persisted to tenant-isolated storage."""

    tenant_id: uuid.UUID
    sha256: str
    byte_size: int
    storage_uri: str
    local_path: Path


class TenantObjectStorage:
    """
    Local tenant-isolated content-addressed blob vault.
    Blobs are strictly partitioned by `tenant_id` (`<vault_root>/<tenant_id>/blobs/<sha[:2]>/<sha>`)
    so content-addressed deduplication never crosses tenant boundaries (D3-04).
    """

    def __init__(self, vault_root: Path | None = None) -> None:
        self.vault_root = (vault_root or DEFAULT_VAULT_ROOT).resolve()
        self.vault_root.mkdir(parents=True, exist_ok=True)

    def _tenant_root(self, tenant_id: uuid.UUID | str) -> Path:
        tid = str(uuid.UUID(str(tenant_id)))
        t_root = self.vault_root / tid
        return validate_safe_extract_path(self.vault_root, t_root)

    def _blob_path(self, tenant_id: uuid.UUID | str, sha256_hex: str) -> Path:
        clean_hash = sha256_hex.strip().lower()
        if len(clean_hash) != 64 or any(c not in "0123456789abcdef" for c in clean_hash):
            raise ValueError(f"Invalid SHA-256 hex digest: {sha256_hex!r}")
        tenant_root = self._tenant_root(tenant_id)
        target = tenant_root / "blobs" / clean_hash[:2] / clean_hash
        return validate_safe_extract_path(tenant_root, target)

    @staticmethod
    def compute_sha256(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def put_blob(self, tenant_id: uuid.UUID | str, content: bytes) -> StoredBlob:
        tid = uuid.UUID(str(tenant_id))
        sha256_hex = self.compute_sha256(content)
        blob_path = self._blob_path(tid, sha256_hex)
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        if not blob_path.exists():
            blob_path.write_bytes(content)
        uri = f"vault://{tid}/blobs/{sha256_hex[:2]}/{sha256_hex}"
        return StoredBlob(
            tenant_id=tid,
            sha256=sha256_hex,
            byte_size=len(content),
            storage_uri=uri,
            local_path=blob_path,
        )

    def get_blob_bytes(self, tenant_id: uuid.UUID | str, sha256_hex: str) -> bytes:
        blob_path = self._blob_path(tenant_id, sha256_hex)
        if not blob_path.exists():
            raise FileNotFoundError(
                f"Blob {sha256_hex} not found in tenant vault {tenant_id}."
            )
        return blob_path.read_bytes()

    def get_blob_text(self, tenant_id: uuid.UUID | str, sha256_hex: str) -> str:
        raw = self.get_blob_bytes(tenant_id, sha256_hex)
        return raw.decode("utf-8", errors="replace")

    def blob_exists(self, tenant_id: uuid.UUID | str, sha256_hex: str) -> bool:
        return self._blob_path(tenant_id, sha256_hex).exists()

    def get_storage_metrics(self) -> dict[str, Any]:
        """Return disk space and tenant vault blob statistics for observability."""
        try:
            usage = shutil.disk_usage(self.vault_root)
            tenant_dirs = [
                p for p in self.vault_root.iterdir() if p.is_dir()
            ]
            return {
                "status": "healthy",
                "service": "storage",
                "latency_ms": 0.1,
                "details": {
                    "vault_root": str(self.vault_root),
                    "tenant_vault_count": len(tenant_dirs),
                    "disk_total_gb": round(usage.total / (1024**3), 2),
                    "disk_used_gb": round(usage.used / (1024**3), 2),
                    "disk_free_gb": round(usage.free / (1024**3), 2),
                    "disk_free_pct": round((usage.free / usage.total) * 100, 2)
                    if usage.total
                    else 0.0,
                },
                "error": None,
            }
        except Exception as exc:
            return {
                "status": "unhealthy",
                "service": "storage",
                "latency_ms": None,
                "details": {"vault_root": str(self.vault_root)},
                "error": f"{type(exc).__name__}: {str(exc)}",
            }


