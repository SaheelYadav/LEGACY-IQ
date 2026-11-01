"""Stage 3: Secure ZIP Source Ingestion, Snapshot Creation, and Artifact Versioning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import mimetypes
from pathlib import Path, PurePosixPath
import tempfile
import uuid
import zipfile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.parser_registry import count_lines_of_code, detect_language_and_kind
from app.core.security import validate_safe_extract_path
from app.integrations.storage import TenantObjectStorage
from app.models.ingestion import (
    Artifact,
    ArtifactVersion,
    IngestionJob,
    Repository,
    RepositorySnapshot,
)
from app.services.code_intelligence_service import CodeIntelligenceService
from app.services.retrieval_service import RetrievalService
from app.services.technical_intelligence_service import TechnicalIntelligenceService

MAX_ARCHIVE_COMPRESSED_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 150 * 1024 * 1024  # 150 MB
MAX_SINGLE_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_ARCHIVE_FILE_COUNT = 2500
MAX_COMPRESSION_RATIO = 100.0

IGNORED_PATH_SEGMENTS = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".next",
        "dist",
        "build",
        ".DS_Store",
    }
)


class ArchiveValidationError(ValueError):
    """Raised when an uploaded ZIP archive violates safety, size, or traversal rules."""


@dataclass(frozen=True)
class ValidatedZipEntry:
    relative_path: str
    content: bytes
    content_sha256: str
    byte_size: int
    is_binary: bool
    detected_language: str | None
    artifact_kind: str
    mime_type: str
    line_count: int | None


@dataclass(frozen=True)
class ZipIngestionOutcome:
    repository_id: uuid.UUID
    snapshot_id: uuid.UUID
    ingestion_job_id: uuid.UUID
    analysis_run_id: uuid.UUID | None
    tree_hash: str
    is_duplicate_snapshot: bool
    files_processed: int
    total_bytes: int
    chunks_indexed: int


class IngestionService:
    """
    Validates untrusted ZIP archives, persists tenant-isolated content-addressed blobs,
    creates immutable `RepositorySnapshot` + `Artifact` + `ArtifactVersion` + `IngestionJob`
    records, and runs deterministic code intelligence and hybrid retrieval indexing.
    """

    def __init__(
        self,
        storage: TenantObjectStorage | None = None,
        code_intel_service: CodeIntelligenceService | None = None,
        retrieval_service: RetrievalService | None = None,
        tech_intel_service: TechnicalIntelligenceService | None = None,
        *,
        max_file_count: int = MAX_ARCHIVE_FILE_COUNT,
        max_total_uncompressed_bytes: int = MAX_ARCHIVE_UNCOMPRESSED_BYTES,
        max_single_file_bytes: int = MAX_SINGLE_FILE_BYTES,
        max_compression_ratio: float = MAX_COMPRESSION_RATIO,
    ) -> None:
        self.storage = storage or TenantObjectStorage()
        self.code_intel_service = code_intel_service or CodeIntelligenceService(self.storage)
        self.retrieval_service = retrieval_service or RetrievalService(self.storage)
        self.tech_intel_service = tech_intel_service or TechnicalIntelligenceService(self.storage)
        self.max_file_count = max_file_count
        self.max_total_uncompressed_bytes = max_total_uncompressed_bytes
        self.max_single_file_bytes = max_single_file_bytes
        self.max_compression_ratio = max_compression_ratio

    def validate_and_inspect_zip(self, zip_bytes: bytes) -> tuple[list[ValidatedZipEntry], str]:
        """
        Validate a raw ZIP payload in memory and sandbox directory check without executing anything.
        Returns `(sorted_entries, tree_hash)`.
        """
        if not zip_bytes:
            raise ArchiveValidationError("Uploaded ZIP archive is empty.")
        if len(zip_bytes) > MAX_ARCHIVE_COMPRESSED_BYTES:
            raise ArchiveValidationError(
                f"Compressed archive size ({len(zip_bytes)} bytes) exceeds limit ({MAX_ARCHIVE_COMPRESSED_BYTES} bytes)."
            )

        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes), mode="r")
        except zipfile.BadZipFile as exc:
            raise ArchiveValidationError("Invalid or corrupted ZIP archive.") from exc

        entries: list[ValidatedZipEntry] = []
        total_uncompressed = 0
        seen_paths: set[str] = set()

        with zf, tempfile.TemporaryDirectory(prefix="legacyiq_zip_guard_") as sandbox_dir:
            sandbox_root = Path(sandbox_dir).resolve()
            info_list = zf.infolist()

            file_entries_count = 0
            for info in info_list:
                raw_name = info.filename.replace("\\", "/")
                if not raw_name or raw_name.endswith("/"):
                    continue

                if (
                    raw_name.startswith("/")
                    or ":" in raw_name
                    or ".." in PurePosixPath(raw_name).parts
                ):
                    raise ArchiveValidationError(
                        f"Security violation: unsafe archive path '{info.filename}' rejected."
                    )

                candidate_target = sandbox_root / Path(raw_name)
                validate_safe_extract_path(sandbox_root, candidate_target)

                unix_mode = (info.external_attr >> 16) & 0o170000
                if unix_mode == 0o120000:
                    raise ArchiveValidationError(
                        f"Security violation: symbolic link entry '{info.filename}' is not permitted."
                    )

                parts = PurePosixPath(raw_name).parts
                if any(p in IGNORED_PATH_SEGMENTS for p in parts):
                    continue

                file_entries_count += 1
                if file_entries_count > self.max_file_count:
                    raise ArchiveValidationError(
                        f"Archive exceeds maximum allowed file count ({self.max_file_count})."
                    )

                if info.file_size > self.max_single_file_bytes:
                    raise ArchiveValidationError(
                        f"File '{raw_name}' size ({info.file_size} bytes) exceeds per-file limit ({self.max_single_file_bytes} bytes)."
                    )

                if info.compress_size > 0:
                    ratio = info.file_size / max(info.compress_size, 1)
                    if ratio > self.max_compression_ratio and info.file_size > 65536:
                        raise ArchiveValidationError(
                            f"Security violation: suspicious compression ratio ({ratio:.1f}x) on '{raw_name}'."
                        )

                total_uncompressed += info.file_size
                if total_uncompressed > self.max_total_uncompressed_bytes:
                    raise ArchiveValidationError(
                        f"Total uncompressed size ({total_uncompressed} bytes) exceeds limit ({self.max_total_uncompressed_bytes} bytes)."
                    )

                content = zf.read(info)
                if len(content) > self.max_single_file_bytes:
                    raise ArchiveValidationError(
                        f"Actual read size of '{raw_name}' exceeds per-file limit."
                    )

                norm_path = str(PurePosixPath(raw_name))
                if norm_path in seen_paths:
                    continue
                seen_paths.add(norm_path)

                sha256_hex = hashlib.sha256(content).hexdigest()
                is_bin = b"\x00" in content[:8192]
                lang, kind = detect_language_and_kind(norm_path)
                if is_bin and kind == "OTHER":
                    kind = "BINARY_METADATA"

                guessed_mime, _ = mimetypes.guess_type(norm_path)
                mime_type = guessed_mime or (
                    "application/octet-stream" if is_bin else "text/plain"
                )

                line_count: int | None = None
                if not is_bin:
                    text_str = content.decode("utf-8", errors="replace")
                    line_count, _ = count_lines_of_code(text_str)

                entries.append(
                    ValidatedZipEntry(
                        relative_path=norm_path,
                        content=content,
                        content_sha256=sha256_hex,
                        byte_size=len(content),
                        is_binary=is_bin,
                        detected_language=lang,
                        artifact_kind=kind,
                        mime_type=mime_type,
                        line_count=line_count,
                    )
                )

        if not entries:
            raise ArchiveValidationError("Archive contains no ingestible files.")

        entries.sort(key=lambda e: e.relative_path)
        tree_hasher = hashlib.sha256()
        for entry in entries:
            tree_hasher.update(
                f"{entry.relative_path}:{entry.content_sha256}\n".encode("utf-8")
            )
        tree_hash = tree_hasher.hexdigest()
        return entries, tree_hash

    def ingest_zip_archive(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        repository_id: uuid.UUID,
        zip_bytes: bytes,
        snapshot_label: str | None = None,
        triggered_by_user_id: uuid.UUID | None = None,
        run_analysis_and_indexing: bool = True,
    ) -> ZipIngestionOutcome:
        repo = db.execute(
            select(Repository).where(
                Repository.tenant_id == tenant_id,
                Repository.id == repository_id,
            )
        ).scalar_one_or_none()
        if repo is None:
            raise ValueError(
                f"Repository {repository_id} not found for tenant {tenant_id}."
            )

        entries, tree_hash = self.validate_and_inspect_zip(zip_bytes)
        total_bytes = sum(e.byte_size for e in entries)
        now = datetime.now(timezone.utc)

        existing_snapshot = db.execute(
            select(RepositorySnapshot).where(
                RepositorySnapshot.tenant_id == tenant_id,
                RepositorySnapshot.repository_id == repository_id,
                RepositorySnapshot.tree_or_archive_sha256 == tree_hash,
            )
        ).scalar_one_or_none()

        if existing_snapshot is not None:
            job = IngestionJob(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                repository_id=repository_id,
                snapshot_id=existing_snapshot.id,
                triggered_by_user_id=triggered_by_user_id,
                idempotency_key=f"idempotent-{tree_hash[:24]}-{uuid.uuid4().hex[:6]}",
                status="COMPLETED",
                stats_summary={
                    "stage": "COMPLETED_IDEMPOTENT_REUSE",
                    "progress_pct": 100,
                    "files_processed": int(existing_snapshot.total_files_count),
                    "bytes_processed": int(existing_snapshot.total_bytes_size),
                },
                started_at=now,
                completed_at=now,
            )
            db.add(job)
            db.flush()
            return ZipIngestionOutcome(
                repository_id=repository_id,
                snapshot_id=existing_snapshot.id,
                ingestion_job_id=job.id,
                analysis_run_id=None,
                tree_hash=tree_hash,
                is_duplicate_snapshot=True,
                files_processed=int(existing_snapshot.total_files_count),
                total_bytes=int(existing_snapshot.total_bytes_size),
                chunks_indexed=0,
            )

        # Store raw archive in tenant vault
        self.storage.put_blob(tenant_id, zip_bytes)

        existing_nums = db.execute(
            select(RepositorySnapshot.snapshot_number).where(
                RepositorySnapshot.tenant_id == tenant_id,
                RepositorySnapshot.repository_id == repository_id,
            )
        ).scalars().all()
        next_snap_num = (max(existing_nums) + 1) if existing_nums else 1

        snapshot = RepositorySnapshot(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            repository_id=repository_id,
            branch_id=None,
            commit_id=None,
            snapshot_number=next_snap_num,
            tree_or_archive_sha256=tree_hash,
            total_files_count=len(entries),
            total_bytes_size=total_bytes,
            legal_hold_active=False,
            status="READY",
        )
        db.add(snapshot)
        db.flush()

        job = IngestionJob(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            repository_id=repository_id,
            snapshot_id=snapshot.id,
            triggered_by_user_id=triggered_by_user_id,
            idempotency_key=f"zip-{tree_hash[:24]}",
            status="RUNNING",
            stats_summary={
                "stage": "INGESTING_ARTIFACTS",
                "progress_pct": 25,
                "files_processed": 0,
                "bytes_processed": 0,
            },
            started_at=now,
        )
        db.add(job)
        db.flush()

        snapshot_artifacts: list[tuple[Artifact, ArtifactVersion]] = []
        for entry in entries:
            stored_blob = self.storage.put_blob(tenant_id, entry.content)

            artifact = db.execute(
                select(Artifact).where(
                    Artifact.tenant_id == tenant_id,
                    Artifact.application_id == repo.application_id,
                    Artifact.repository_id == repository_id,
                    Artifact.canonical_path == entry.relative_path,
                )
            ).scalar_one_or_none()

            if artifact is None:
                artifact = Artifact(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    application_id=repo.application_id,
                    repository_id=repository_id,
                    artifact_kind=entry.artifact_kind,
                    canonical_path=entry.relative_path,
                )
                db.add(artifact)
                db.flush()

            existing_ver = db.execute(
                select(ArtifactVersion).where(
                    ArtifactVersion.tenant_id == tenant_id,
                    ArtifactVersion.artifact_id == artifact.id,
                    ArtifactVersion.content_sha256 == entry.content_sha256,
                )
            ).scalar_one_or_none()

            if existing_ver is None:
                av = ArtifactVersion(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    artifact_id=artifact.id,
                    content_sha256=entry.content_sha256,
                    byte_size=entry.byte_size,
                    line_count=entry.line_count,
                    encoding="binary" if entry.is_binary else "utf-8",
                    mime_type=entry.mime_type,
                    storage_object_uri=stored_blob.storage_uri,
                )
                db.add(av)
                db.flush()
            else:
                av = existing_ver

            snapshot_artifacts.append((artifact, av))

        db.flush()

        analysis_run_id: uuid.UUID | None = None
        chunks_indexed = 0

        if run_analysis_and_indexing:
            analysis_run = self.code_intel_service.run_static_analysis(
                db,
                tenant_id=tenant_id,
                snapshot_id=snapshot.id,
                triggered_by_user_id=triggered_by_user_id,
                snapshot_artifacts=snapshot_artifacts,
            )
            analysis_run_id = analysis_run.id

            idx_stats = self.retrieval_service.index_snapshot_artifacts(
                db,
                tenant_id=tenant_id,
                snapshot_id=snapshot.id,
                analysis_run_id=analysis_run.id,
                snapshot_artifacts=snapshot_artifacts,
            )
            chunks_indexed = idx_stats["chunks_created"]

            self.tech_intel_service.run_wave2_pipeline(
                db,
                tenant_id=tenant_id,
                snapshot_id=snapshot.id,
                analysis_run_id=analysis_run.id,
                snapshot_artifacts=snapshot_artifacts,
            )

        job.status = "COMPLETED"
        job.stats_summary = {
            "stage": "COMPLETED",
            "progress_pct": 100,
            "files_processed": len(entries),
            "bytes_processed": total_bytes,
            "chunks_indexed": chunks_indexed,
            "snapshot_label": snapshot_label or f"v{next_snap_num}",
        }
        job.completed_at = datetime.now(timezone.utc)
        db.flush()

        return ZipIngestionOutcome(
            repository_id=repository_id,
            snapshot_id=snapshot.id,
            ingestion_job_id=job.id,
            analysis_run_id=analysis_run_id,
            tree_hash=tree_hash,
            is_duplicate_snapshot=False,
            files_processed=len(entries),
            total_bytes=total_bytes,
            chunks_indexed=chunks_indexed,
        )
