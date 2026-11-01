"""Stage 5: AST/Window Document Chunking, Local 384-d Embeddings, and Hybrid RRF Retrieval."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
import re
from typing import Any
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.analysis.parser_registry import detect_language_and_kind
from app.core.config import settings
from app.core.security import DEFAULT_EMBEDDING_MODEL_VERSION_ID
from app.integrations.storage import TenantObjectStorage
from app.models.code_intelligence import CodeFile, CodeSymbol
from app.models.ingestion import Artifact, ArtifactVersion, Repository, RepositorySnapshot
from app.models.retrieval import (
    ArtifactEmbedding,
    DocumentChunk,
    EmbeddingModelVersion,
)

_CACHED_ST_MODEL: Any = None


def compute_embedding_vector(text_input: str) -> list[float]:
    """
    Generate a 384-dimensional unit-normalized embedding vector using local
    `BAAI/bge-small-en-v1.5` (`sentence-transformers`), with a deterministic
    384-d feature-hashing fallback if `LEGACYIQ_DETERMINISTIC_EMBEDDINGS=1` is set
    or local model loading is unavailable.
    """
    global _CACHED_ST_MODEL
    if os.environ.get("LEGACYIQ_DETERMINISTIC_EMBEDDINGS") != "1":
        try:
            if _CACHED_ST_MODEL is None:
                from sentence_transformers import SentenceTransformer

                _CACHED_ST_MODEL = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
            vec = _CACHED_ST_MODEL.encode(
                text_input, normalize_embeddings=True, show_progress_bar=False
            )
            as_list = [float(x) for x in vec.tolist()]
            if len(as_list) == settings.EMBEDDING_DIMENSION:
                return as_list
        except Exception:
            pass

    return _deterministic_hash_embedding(text_input, dim=settings.EMBEDDING_DIMENSION)


def _deterministic_hash_embedding(text_input: str, dim: int = 384) -> list[float]:
    """Deterministic unit-normalized feature-hashed 384-d vector for offline fallback."""
    vec = [0.0] * dim
    tokens = re.findall(r"[a-zA-Z0-9_]{2,}", text_input.lower())
    if not tokens:
        tokens = ["empty"]
    for tok in tokens:
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        for i in range(0, 16, 4):
            idx = int.from_bytes(digest[i : i + 2], "big") % dim
            sign = 1.0 if (digest[i + 2] & 1) == 0 else -1.0
            weight = 1.0 + (digest[i + 3] / 255.0)
            vec[idx] += sign * weight
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 6) for v in vec]


@dataclass(frozen=True)
class HybridSearchHit:
    chunk_id: uuid.UUID
    artifact_id: uuid.UUID
    artifact_version_id: uuid.UUID
    relative_path: str
    detected_language: str | None
    code_symbol_id: uuid.UUID | None
    symbol_qualified_name: str | None
    symbol_kind: str | None
    chunk_strategy: str
    start_line: int
    end_line: int
    chunk_text: str
    chunk_sha256: str
    rrf_score: float
    vector_score: float | None
    lexical_score: float | None


class RetrievalService:
    """
    Handles AST-aware and window-based chunking, 384-d `pgvector` indexing,
    and tenant- + snapshot-scoped Hybrid RRF search.
    """

    def __init__(self, storage: TenantObjectStorage | None = None) -> None:
        self.storage = storage or TenantObjectStorage()

    def ensure_default_embedding_model(self, db: Session) -> EmbeddingModelVersion:
        model = db.execute(
            select(EmbeddingModelVersion).where(
                EmbeddingModelVersion.id == DEFAULT_EMBEDDING_MODEL_VERSION_ID
            )
        ).scalar_one_or_none()
        if model is None:
            model = EmbeddingModelVersion(
                id=DEFAULT_EMBEDDING_MODEL_VERSION_ID,
                provider_name="sentence-transformers",
                model_name=settings.EMBEDDING_MODEL_NAME,
                model_revision="v1.5",
                vector_dimension=settings.EMBEDDING_DIMENSION,
                distance_metric="COSINE",
                is_active_default=True,
            )
            db.add(model)
            db.flush()
        return model

    def index_snapshot_artifacts(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        analysis_run_id: uuid.UUID | None = None,
        snapshot_artifacts: list[tuple[Artifact, ArtifactVersion]] | None = None,
    ) -> dict[str, int]:
        """
        Chunk and embed all textual `ArtifactVersion` rows in `snapshot_id`.
        Idempotent per `(tenant_id, artifact_version_id)`.
        """
        snapshot = db.execute(
            select(RepositorySnapshot).where(
                RepositorySnapshot.tenant_id == tenant_id,
                RepositorySnapshot.id == snapshot_id,
            )
        ).scalar_one_or_none()
        if snapshot is None:
            raise ValueError(f"Snapshot {snapshot_id} not found for tenant {tenant_id}.")

        model_ver = self.ensure_default_embedding_model(db)

        if snapshot_artifacts is None:
            rows = db.execute(
                select(Artifact, ArtifactVersion)
                .join(
                    ArtifactVersion,
                    (ArtifactVersion.tenant_id == Artifact.tenant_id)
                    & (ArtifactVersion.artifact_id == Artifact.id),
                )
                .where(
                    Artifact.tenant_id == tenant_id,
                    Artifact.repository_id == snapshot.repository_id,
                    ArtifactVersion.encoding != "binary",
                )
                .order_by(Artifact.canonical_path.asc())
            ).all()
            snapshot_artifacts = [(r[0], r[1]) for r in rows]

        chunks_created = 0
        embeddings_created = 0

        for artifact, version in snapshot_artifacts:
            if version.encoding == "binary":
                continue

            existing_count = db.execute(
                select(func.count(DocumentChunk.id)).where(
                    DocumentChunk.tenant_id == tenant_id,
                    DocumentChunk.artifact_version_id == version.id,
                )
            ).scalar_one()
            if existing_count and existing_count > 0:
                continue

            source_text = self.storage.get_blob_text(tenant_id, version.content_sha256)
            if not source_text.strip():
                continue

            symbols: list[CodeSymbol] = []
            if analysis_run_id is not None:
                symbols = list(
                    db.execute(
                        select(CodeSymbol)
                        .join(
                            CodeFile,
                            (CodeFile.tenant_id == CodeSymbol.tenant_id)
                            & (CodeFile.id == CodeSymbol.code_file_id),
                        )
                        .where(
                            CodeFile.tenant_id == tenant_id,
                            CodeFile.snapshot_id == snapshot_id,
                            CodeFile.artifact_version_id == version.id,
                        )
                        .order_by(CodeSymbol.start_line.asc())
                    ).scalars().all()
                )

            lang, _ = detect_language_and_kind(artifact.canonical_path)
            chunk_specs = self._build_chunks_for_file(
                relative_path=artifact.canonical_path,
                artifact_kind=artifact.artifact_kind,
                detected_language=lang,
                source_text=source_text,
                symbols=symbols,
            )

            for idx, spec in enumerate(chunk_specs):
                chunk_text = spec["chunk_text"]
                chunk_sha = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
                token_est = max(1, len(chunk_text.split()))
                chunk = DocumentChunk(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    artifact_version_id=version.id,
                    chunk_strategy=spec["chunk_strategy"],
                    chunk_index=idx,
                    start_line=spec["start_line"],
                    end_line=spec["end_line"],
                    token_count=token_est,
                    chunk_text_sha256=chunk_sha,
                    chunk_text=chunk_text,
                    metadata_tags={
                        "snapshot_id": str(snapshot_id),
                        "repository_id": str(snapshot.repository_id),
                        "detected_language": lang,
                        "code_symbol_id": (
                            str(spec["code_symbol_id"])
                            if spec["code_symbol_id"]
                            else None
                        ),
                        "symbol_qualified_name": spec["symbol_qualified_name"],
                        "symbol_kind": spec["symbol_kind"],
                    },
                )
                db.add(chunk)
                db.flush()

                vec = compute_embedding_vector(chunk_text)
                emb = ArtifactEmbedding(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    document_chunk_id=chunk.id,
                    embedding_model_version_id=model_ver.id,
                    embedding=vec,
                )
                db.add(emb)
                chunks_created += 1
                embeddings_created += 1

        db.flush()
        return {
            "chunks_created": chunks_created,
            "embeddings_created": embeddings_created,
        }

    def _build_chunks_for_file(
        self,
        *,
        relative_path: str,
        artifact_kind: str,
        detected_language: str | None,
        source_text: str,
        symbols: list[CodeSymbol],
    ) -> list[dict[str, Any]]:
        lines = source_text.splitlines()
        total_lines = max(len(lines), 1)

        if symbols:
            chunks: list[dict[str, Any]] = []
            for sym in symbols:
                s_line = max(1, sym.start_line)
                e_line = min(total_lines, max(s_line, sym.end_line))
                snippet = "\n".join(lines[s_line - 1 : e_line]).strip()
                if not snippet:
                    continue
                header = f"# File: {relative_path} | Symbol: {sym.qualified_name} ({sym.symbol_kind})\n"
                chunks.append(
                    {
                        "code_symbol_id": sym.id,
                        "symbol_qualified_name": sym.qualified_name,
                        "symbol_kind": sym.symbol_kind,
                        "chunk_strategy": "AST_SYMBOL_WINDOW",
                        "start_line": s_line,
                        "end_line": e_line,
                        "chunk_text": f"{header}{snippet}",
                    }
                )
            if chunks:
                return chunks

        strategy = (
            "MARKDOWN_SECTION" if artifact_kind == "DOCUMENTATION" else "SLIDING_WINDOW"
        )
        window_size = 50
        stride = 40
        chunks = []
        start = 1
        while start <= total_lines:
            end = min(total_lines, start + window_size - 1)
            snippet = "\n".join(lines[start - 1 : end]).strip()
            if snippet:
                header = f"# File: {relative_path} (lines {start}-{end})\n"
                chunks.append(
                    {
                        "code_symbol_id": None,
                        "symbol_qualified_name": None,
                        "symbol_kind": None,
                        "chunk_strategy": strategy,
                        "start_line": start,
                        "end_line": end,
                        "chunk_text": f"{header}{snippet}",
                    }
                )
            if end >= total_lines:
                break
            start += stride
        return chunks

    def hybrid_search(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        query_text: str,
        limit: int = 10,
        language_filter: str | None = None,
    ) -> list[HybridSearchHit]:
        """
        Execute tenant- and snapshot-scoped Hybrid Reciprocal Rank Fusion (RRF, k=60)
        combining `pgvector` cosine similarity and PostgreSQL lexical full-text search.
        """
        clean_query = query_text.strip()
        if not clean_query:
            return []

        snapshot = db.execute(
            select(RepositorySnapshot).where(
                RepositorySnapshot.tenant_id == tenant_id,
                RepositorySnapshot.id == snapshot_id,
            )
        ).scalar_one_or_none()
        if snapshot is None:
            return []

        query_vec = compute_embedding_vector(clean_query)
        vec_literal = "[" + ",".join(f"{x:.6f}" for x in query_vec) + "]"

        lang_clause = (
            "AND (dc.metadata_tags->>'detected_language') = :lang"
            if language_filter
            else ""
        )
        vec_sql = text(
            f"""
            SELECT
                dc.id AS chunk_id,
                (1.0 - (ae.embedding <=> CAST(:qvec AS vector(384)))) AS vector_score
            FROM artifact_embeddings ae
            JOIN document_chunks dc
              ON dc.tenant_id = ae.tenant_id AND dc.id = ae.document_chunk_id
            JOIN artifact_versions av
              ON av.tenant_id = dc.tenant_id AND av.id = dc.artifact_version_id
            JOIN artifacts a
              ON a.tenant_id = av.tenant_id AND a.id = av.artifact_id
            WHERE ae.tenant_id = :tid
              AND a.repository_id = :rid
              {lang_clause}
            ORDER BY ae.embedding <=> CAST(:qvec AS vector(384)) ASC
            LIMIT :top_k
            """
        )
        params: dict[str, Any] = {
            "tid": tenant_id,
            "rid": snapshot.repository_id,
            "qvec": vec_literal,
            "top_k": max(limit * 3, 20),
        }
        if language_filter:
            params["lang"] = language_filter

        vec_rows = db.execute(vec_sql, params).fetchall()

        lex_sql = text(
            f"""
            SELECT
                dc.id AS chunk_id,
                GREATEST(
                    COALESCE(ts_rank_cd(dc.search_tsv, websearch_to_tsquery('english', :qtxt)), 0.0),
                    CASE WHEN dc.chunk_text ILIKE :qlike THEN 0.5 ELSE 0.0 END
                ) AS lexical_score
            FROM document_chunks dc
            JOIN artifact_versions av
              ON av.tenant_id = dc.tenant_id AND av.id = dc.artifact_version_id
            JOIN artifacts a
              ON a.tenant_id = av.tenant_id AND a.id = av.artifact_id
            WHERE dc.tenant_id = :tid
              AND a.repository_id = :rid
              {lang_clause}
              AND (
                  dc.search_tsv @@ websearch_to_tsquery('english', :qtxt)
                  OR dc.chunk_text ILIKE :qlike
              )
            ORDER BY lexical_score DESC
            LIMIT :top_k
            """
        )
        lex_params = {
            **params,
            "qtxt": clean_query,
            "qlike": f"%{clean_query}%",
        }
        lex_rows = db.execute(lex_sql, lex_params).fetchall()

        rrf_k = 60.0
        rrf_scores: dict[uuid.UUID, float] = {}
        vec_scores: dict[uuid.UUID, float] = {}
        lex_scores: dict[uuid.UUID, float] = {}

        for rank, row in enumerate(vec_rows, start=1):
            cid = row[0]
            score = float(row[1])
            vec_scores[cid] = score
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (rrf_k + rank))

        for rank, row in enumerate(lex_rows, start=1):
            cid = row[0]
            score = float(row[1])
            lex_scores[cid] = score
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (rrf_k + rank))

        if not rrf_scores:
            return []

        ranked_chunk_ids = sorted(
            rrf_scores.keys(), key=lambda c: rrf_scores[c], reverse=True
        )[:limit]

        detail_rows = db.execute(
            select(DocumentChunk, ArtifactVersion, Artifact)
            .join(
                ArtifactVersion,
                (ArtifactVersion.tenant_id == DocumentChunk.tenant_id)
                & (ArtifactVersion.id == DocumentChunk.artifact_version_id),
            )
            .join(
                Artifact,
                (Artifact.tenant_id == ArtifactVersion.tenant_id)
                & (Artifact.id == ArtifactVersion.artifact_id),
            )
            .where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.id.in_(ranked_chunk_ids),
            )
        ).all()

        by_id = {row[0].id: row for row in detail_rows}
        results: list[HybridSearchHit] = []
        for cid in ranked_chunk_ids:
            if cid not in by_id:
                continue
            dc, av, art = by_id[cid]
            tags = dc.metadata_tags or {}
            sym_id_raw = tags.get("code_symbol_id")
            sym_uuid = uuid.UUID(sym_id_raw) if sym_id_raw else None
            results.append(
                HybridSearchHit(
                    chunk_id=dc.id,
                    artifact_id=art.id,
                    artifact_version_id=av.id,
                    relative_path=art.canonical_path,
                    detected_language=tags.get("detected_language"),
                    code_symbol_id=sym_uuid,
                    symbol_qualified_name=tags.get("symbol_qualified_name"),
                    symbol_kind=tags.get("symbol_kind"),
                    chunk_strategy=dc.chunk_strategy,
                    start_line=dc.start_line,
                    end_line=dc.end_line,
                    chunk_text=dc.chunk_text,
                    chunk_sha256=dc.chunk_text_sha256,
                    rrf_score=round(rrf_scores[cid], 6),
                    vector_score=(
                        round(vec_scores[cid], 4) if cid in vec_scores else None
                    ),
                    lexical_score=(
                        round(lex_scores[cid], 4) if cid in lex_scores else None
                    ),
                )
            )
        return results
