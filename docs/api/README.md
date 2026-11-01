# LegacyIQ API Specification (M0 Foundation)

## Base Path
`/api/v1`

## Health & Infrastructure Readiness Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Returns overall backend application status, environment, and version. |
| `GET` | `/api/v1/health/database` | Verifies real PostgreSQL connectivity and checks `pgvector` extension availability. Returns HTTP 503 if unreachable or unconfigured. |
| `GET` | `/api/v1/health/redis` | Verifies real Redis connectivity (`PING` -> `PONG`). Returns HTTP 503 if unreachable or unconfigured. |
| `GET` | `/api/v1/health/ollama` | Verifies real connectivity to the local Ollama HTTP API (`/api/tags`) and checks whether the configured model (`qwen2.5-coder:3b`) is installed. Returns HTTP 503 if unreachable. |

