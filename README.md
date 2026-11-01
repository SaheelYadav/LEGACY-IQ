# LegacyIQ

**AI-Powered Legacy Application Discovery & Requirements Intelligence Platform**

LegacyIQ is a local-first, zero-initial-budget platform engineered to analyze legacy codebases (Python, Java, JavaScript, TypeScript, and PHP) and reconstruct architectural knowledge, business rules, functional/non-functional requirements, dependency graphs, and modernization pathways backed by verifiable code evidence.

---

## 1. Capabilities Roadmap

- **Automated Repository Discovery**: Safe static ingestion and language/framework inventory.
- **Business Logic Extraction**: Identification of domain rules and workflows embedded in legacy code.
- **Requirements Intelligence**: Automated synthesis of functional and non-functional requirements.
- **Architecture Reconstruction**: Structural decomposition and interactive visual topology mapping.
- **Dependency & Relationship Mapping**: Call graphs, module coupling, and data flow analysis via AST, Tree-sitter, and NetworkX.
- **Code Intelligence & Semantic Search**: Local vector indexing (`BAAI/bge-small-en-v1.5` + `pgvector`) for semantic codebase search.
- **Test Case Generation**: Characterization and regression test blueprints.
- **Modernization Recommendations**: Risk-scored refactoring and migration guidance.
- **Evidence-Backed Reports & Grounded Q&A**: Every insight linked to exact file paths and line ranges.

---

## 2. Architecture & Technology Stack

### Frontend (`frontend/`)
- **Framework**: Next.js (App Router), TypeScript
- **Styling & UI**: Tailwind CSS, shadcn/ui-ready component architecture, Lucide icons
- **Visualization & State**: React Flow-ready & Recharts-ready structures, TanStack Query, React Hook Form, Zod

### Backend (`backend/`)
- **Framework**: Python 3.10+, FastAPI, Pydantic v2
- **Data Layer**: SQLAlchemy 2.0, Alembic, PostgreSQL 17 (`pgvector`), Redis 7
- **Analysis & AI Foundation**: Python AST, Tree-sitter-ready parsers, NetworkX graph structures, Sentence Transformers (`BAAI/bge-small-en-v1.5`, 384-dim), Ollama (`qwen2.5-coder:3b`) with provider abstraction for OpenRouter, Gemini, and Groq.

---

## 3. Existing External Infrastructure

LegacyIQ connects to pre-provisioned local infrastructure located at `C:\LegacyIQ-infrastructure` (managed separately):

| Service | Container / Host | Endpoint | Notes |
| :--- | :--- | :--- | :--- |
| **PostgreSQL + pgvector** | `legacyiq-postgres` | `localhost:5432` | DB: `legacyiq`, User: `legacyiq_admin` (`pgvector/pgvector:pg17`) |
| **Redis** | `legacyiq-redis` | `localhost:6380` | Password-authenticated (`redis:7-alpine`) |
| **Ollama** | Local Host Service | `http://localhost:11434` | Model: `qwen2.5-coder:3b` |
| **Embeddings** | Local Python Runtime | In-process CPU | Model: `BAAI/bge-small-en-v1.5` (384 dims) |

> **Important**: Do not recreate or overwrite the existing Docker containers or volumes in `C:\LegacyIQ-infrastructure`.

---

## 4. Repository Structure

```text
LegacyIQ/
├── frontend/               # Next.js App Router application (TypeScript, Tailwind CSS)
├── backend/                # FastAPI application, SQLAlchemy 2, Alembic, Analysis & AI engines
│   ├── app/
│   │   ├── api/            # Versioned REST API routers (/api/v1/...)
│   │   ├── core/           # Configuration, logging, security defaults
│   │   ├── db/             # SQLAlchemy engine, session management, pgvector readiness
│   │   ├── models/         # SQLAlchemy ORM models
│   │   ├── schemas/        # Pydantic v2 request/response schemas
│   │   ├── services/       # Business and orchestration services
│   │   ├── repositories/   # Data access layer
│   │   ├── agents/         # Grounded AI reasoning and extraction agents
│   │   ├── analysis/       # AST, Tree-sitter, and NetworkX static analyzers
│   │   ├── integrations/   # LLM & embedding provider abstractions (Ollama, etc.)
│   │   └── main.py         # FastAPI application entry point
│   ├── alembic/            # Database migration environment
│   └── tests/              # Backend test suite
├── docs/                   # Architecture, API, and ADR documentation
│   ├── architecture/
│   ├── api/
│   └── decisions/
├── scripts/                # Local development utility scripts
├── .env.example            # Root environment variable template
└── README.md
```

---

## 5. Local Setup & Running Instructions

### Prerequisites
- **Node.js** v20+ (v22 LTS verified) & **npm** v10+
- **Python** 3.10+
- **Git** 2.40+
- Running local infrastructure containers (`legacyiq-postgres` on `5432`, `legacyiq-redis` on `6380`) and **Ollama** on `11434`.

### Step 1: Configure Environment Variables
Copy `backend/.env.example` to `backend/.env` and replace `REPLACE_WITH_PASSWORD` with your actual PostgreSQL and Redis passwords from `C:\LegacyIQ-infrastructure`:

```powershell
Copy-Item backend\.env.example backend\.env
```

### Step 2: Start the Backend (`http://localhost:8000`)
```powershell
cd C:\LegacyIQ\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Verify health endpoints:
- `GET http://localhost:8000/api/v1/health`
- `GET http://localhost:8000/api/v1/health/database`
- `GET http://localhost:8000/api/v1/health/redis`
- `GET http://localhost:8000/api/v1/health/ollama`

### Step 3: Start the Frontend (`http://localhost:3000`)
```powershell
cd C:\LegacyIQ\frontend
npm run dev
```

---

## 6. Security Principles
- Secrets are strictly isolated in local `.env` files excluded from Git.
- Uploaded customer repositories and archives are treated as untrusted data and are **never executed**.
- Backend credentials and database connections are never exposed to the client browser.
- CORS is explicitly restricted to configured origins.

