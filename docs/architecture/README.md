# LegacyIQ Architecture Overview (M0 Foundation)

## System Boundaries

1. **Frontend (`frontend/`)**:
   - Next.js App Router (TypeScript, Tailwind CSS)
   - Communicates exclusively with the FastAPI backend over REST (`/api/v1/*`)
   - Never accesses PostgreSQL, Redis, or AI provider credentials directly.

2. **Backend (`backend/`)**:
   - FastAPI modular monolith organized into clear domain layers (`api`, `core`, `db`, `models`, `schemas`, `services`, `repositories`, `agents`, `analysis`, `integrations`).
   - Enforces static-only code analysis (never executing untrusted customer code).
   - Connects to external local infrastructure (`legacyiq-postgres` on port 5432, `legacyiq-redis` on port 6380, and Ollama on port 11434).

3. **External Local Infrastructure (`C:\LegacyIQ-infrastructure`)**:
   - Pre-provisioned Docker containers (`pgvector/pgvector:pg17` and `redis:7-alpine`) and local Ollama host runtime (`qwen2.5-coder:3b`).

