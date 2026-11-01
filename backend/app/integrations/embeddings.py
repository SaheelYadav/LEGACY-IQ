"""Embedding provider abstraction for local Sentence Transformers (384-dim)."""

from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class EmbeddingConfigSpec:
    """Configuration descriptor for the local embedding pipeline."""

    provider: str
    model_name: str
    dimension: int
    device: str


def get_embedding_spec() -> EmbeddingConfigSpec:
    """Return configured embedding specification (BAAI/bge-small-en-v1.5, 384-dim)."""
    return EmbeddingConfigSpec(
        provider=settings.EMBEDDING_PROVIDER,
        model_name=settings.EMBEDDING_MODEL,
        dimension=settings.EMBEDDING_DIMENSION,
        device=settings.EMBEDDING_DEVICE,
    )

