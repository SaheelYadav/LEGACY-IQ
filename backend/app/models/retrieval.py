"""Domain J: Retrieval & Vector Indexing SQLAlchemy 2.0 models (3 Tables)."""

from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
     Boolean,
    CHAR,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TenantScopedMixin


class EmbeddingModelVersion(Base):
    """J1. Global registry of embedding models and dimensions (`GLOBAL_SYSTEM`)."""

    __tablename__ = "embedding_model_versions"
    __table_args__ = (
        UniqueConstraint(
            "provider_name",
            "model_name",
            "model_revision",
            name="uq_embedding_model_versions_provider_model_rev",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4, nullable=False)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_revision: Mapped[str] = mapped_column(
        String(64), default="main", server_default="main", nullable=False
    )
    vector_dimension: Mapped[int] = mapped_column(
        Integer, default=384, server_default="384", nullable=False
    )
    distance_metric: Mapped[str] = mapped_column(
        String(32), default="COSINE", server_default="COSINE", nullable=False
    )
    is_active_default: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )


class DocumentChunk(Base, TenantScopedMixin):
    """J2. Content-addressed text segment extracted from an artifact_version (`TENANT_DIRECT`)."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "artifact_version_id",
            "chunk_strategy",
            "chunk_index",
            name="uq_doc_chunks_ver_strat_idx",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_document_chunks_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "artifact_version_id"],
            ["artifact_versions.tenant_id", "artifact_versions.id"],
            ondelete="CASCADE",
            name="fk_document_chunks_artifact_version",
        ),
    )

    artifact_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    chunk_strategy: Mapped[str] = mapped_column(String(48), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_tags: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )


class ArtifactEmbedding(Base, TenantScopedMixin, CreatedAtMixin):
    """J3. pgvector 384-dimensional vector embedding for a document_chunk (`TENANT_DIRECT`)."""

    __tablename__ = "artifact_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "document_chunk_id",
            "embedding_model_version_id",
            name="uq_artifact_embeddings_chunk_model",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_artifact_embeddings_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "document_chunk_id"],
            ["document_chunks.tenant_id", "document_chunks.id"],
            ondelete="CASCADE",
            name="fk_artifact_embeddings_chunk",
        ),
        ForeignKeyConstraint(
            ["embedding_model_version_id"],
            ["embedding_model_versions.id"],
            ondelete="RESTRICT",
            name="fk_artifact_embeddings_model_version",
        ),
    )

    document_chunk_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    embedding_model_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)

