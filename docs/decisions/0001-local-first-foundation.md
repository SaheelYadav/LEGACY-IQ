# ADR-0001: Local-First Architecture & Pre-Provisioned Infrastructure

## Status
Accepted (M0 Foundation)

## Context
LegacyIQ requires vector search, caching/queueing, static code analysis, and LLM inference with zero initial cloud budget while preserving strict code privacy.

## Decision
1. Reuse the existing local Docker infrastructure in `C:\LegacyIQ-infrastructure` (`legacyiq-postgres` with `pgvector:pg17` on port 5432 and `legacyiq-redis` on port 6380).
2. Use local Ollama (`qwen2.5-coder:3b`) as the default inference provider and `sentence-transformers` (`BAAI/bge-small-en-v1.5`, 384 dimensions) for local embeddings behind clean provider abstractions.
3. Never hardcode or guess database/Redis credentials; require explicit local `.env` configuration.

