# LegacyIQ — Knowledge Graph & Relationship Catalogue (Design Phase D3)

**Document ID**: `D3-07`  
**Status**: Architecture Specification  

---

## 1. Hybrid Relational + NetworkX Graph Architecture

LegacyIQ stores its authoritative knowledge graph in PostgreSQL (`knowledge_entities` and `knowledge_relationships`) alongside fine-grained AST edge tables (`code_call_edges`, `code_imports`, `code_type_hierarchies`, `code_symbol_references`) and projects scoped subgraphs into **NetworkX (`nx.MultiDiGraph`)** in worker memory for compute-intensive topological algorithms.

### Why This Hybrid Architecture Wins for LegacyIQ
1. **Single ACID & RLS Boundary**: Every node and edge is protected by the same PostgreSQL composite foreign keys `(tenant_id, id)` and Row-Level Security policies as the rest of the platform.
2. **Evidence-Linked Edges**: Every row in `knowledge_relationships` can be directly linked via `finding_evidence_links` to `evidence_anchors` (proving *why* edge $A \to B$ exists).
3. **Rich Graph Analytics Without Graph-DB Operational Overhead**: Python's NetworkX operates over in-memory adjacency structures fetched via fast streaming `SELECT` queries (`100,000` edges load in `< 250 ms`), computing PageRank, strongly connected components (Tarjan's algorithm), betweenness centrality, and modular decomposition without maintaining a separate Neo4j/Neptune cluster.

---

## 2. Canonical Node Taxonomy (`knowledge_entities.entity_type`)

| `entity_type` | Backing Domain Table Bridge | Granularity Level | Description |
| :--- | :--- | :--- | :--- |
| `'EXTERNAL_SYSTEM'` | None (`attributes_json`) | L0 (Context) | Third-party API, payment gateway, mainframe, or external message broker. |
| `'SERVICE'` | `api_services` / `infra_resources` | L1 (Container) | Deployable service, daemon, batch worker, or web application unit. |
| `'COMPONENT'` | Grouped `code_modules` | L2 (Component) | Logical architectural layer or domain module (e.g., `Billing Engine`, `Auth Middleware`). |
| `'MODULE'` | `code_modules` / `code_files` | L3 (Code Unit) | Package, namespace, or source file. |
| `'SYMBOL'` | `code_symbols.id` (`source_symbol_id`) | L4 (Code Symbol) | Class, interface, function, method, or global constant. |
| `'DB_TABLE'` | `db_tables.id` (`source_db_table_id`) | L2/L3 (Data Store) | Relational table, view, or NoSQL collection. |
| `'API_ENDPOINT'` | `api_endpoints.id` (`source_api_endpoint_id`) | L2/L3 (Interface) | HTTP route, GraphQL resolver, gRPC method, or queue consumer topic. |
| `'INFRA_RESOURCE'` | `infra_resources.id` | L1 (Infrastructure) | Container, Kubernetes deployment, database instance, or queue resource. |
| `'BUSINESS_CONCEPT'` | `business_domains` / `business_rules` | Domain Layer | Domain entity, business rule node, or business workflow step. |

---

## 3. Canonical Directed Edge Catalogue (`knowledge_relationships.relationship_type`)

Every edge in `knowledge_relationships` is directed (`source_entity_id` $\longrightarrow$ `target_entity_id`) and carries `origin_type`, `confidence_score`, `edge_weight`, and `edge_metadata`.

### 3.1 Code & Structural Dependency Edges

| `relationship_type` | Valid `source_entity_id` Types | Valid `target_entity_id` Types | Default `origin_type` | Semantics & `edge_metadata` Schema |
| :--- | :--- | :--- | :--- | :--- |
| `'CONTAINS'` | `SERVICE`, `COMPONENT`, `MODULE`, `SYMBOL` | `COMPONENT`, `MODULE`, `SYMBOL` | `'DETERMINISTIC_PARSER'` | Structural containment hierarchy (`{"depth": 1}`). |
| `'IMPORTS'` | `MODULE`, `SYMBOL` | `MODULE`, `SYMBOL`, `EXTERNAL_SYSTEM` | `'DETERMINISTIC_PARSER'` | Static import/require/include (`{"import_count": 3, "is_external": false}`). |
| `'CALLS'` | `SYMBOL` | `SYMBOL`, `EXTERNAL_SYSTEM` | `'DETERMINISTIC_PARSER'` | Static or type-inferred function/method invocation (`{"call_sites_count": 4, "certainty": "EXACT_STATIC"}`). |
| `'INHERITS_FROM'` | `SYMBOL` (Class/Interface) | `SYMBOL` (Class/Interface) | `'DETERMINISTIC_PARSER'` | Class `EXTENDS` or mixin inheritance (`{"relation_kind": "EXTENDS"}`). |
| `'IMPLEMENTS_INTERFACE'` | `SYMBOL` (Class) | `SYMBOL` (Interface/Trait) | `'DETERMINISTIC_PARSER'` | Interface realization or trait use. |
| `'INSTANTIATES'` | `SYMBOL` | `SYMBOL` (Class) | `'DETERMINISTIC_PARSER'` | Object construction (`new ClassName()`). |

### 3.2 Data & Persistence Edges

| `relationship_type` | Valid `source_entity_id` Types | Valid `target_entity_id` Types | Default `origin_type` | Semantics & `edge_metadata` Schema |
| :--- | :--- | :--- | :--- | :--- |
| `'MAPS_TO_TABLE'` | `SYMBOL` (ORM Entity) | `DB_TABLE` | `'DETERMINISTIC_PARSER'` | ORM model mapping (`__tablename__`, `@Table`, Eloquent model). |
| `'READS_TABLE'` | `SYMBOL`, `COMPONENT` | `DB_TABLE` | `'DETERMINISTIC_RULE'` / `'HYBRID_AI_STATIC'` | Executes `SELECT` or ORM query read (`{"columns_read": ["id", "credit_limit"]}`). |
| `'WRITES_TABLE'` | `SYMBOL`, `COMPONENT` | `DB_TABLE` | `'DETERMINISTIC_RULE'` / `'HYBRID_AI_STATIC'` | Executes `INSERT`, `UPDATE`, `DELETE`, or ORM flush (`{"ops": ["INSERT", "UPDATE"]}`). |
| `'REFERENCES_TABLE_FK'` | `DB_TABLE` | `DB_TABLE` | `'DETERMINISTIC_PARSER'` | Foreign key or inferred join relationship (`{"fk_columns": ["customer_id"]}`). |

### 3.3 API, Integration & Infrastructure Edges

| `relationship_type` | Valid `source_entity_id` Types | Valid `target_entity_id` Types | Default `origin_type` | Semantics & `edge_metadata` Schema |
| :--- | :--- | :--- | :--- | :--- |
| `'EXPOSES_API'` | `SERVICE`, `COMPONENT` | `API_ENDPOINT` | `'DETERMINISTIC_PARSER'` | Service exposes HTTP/RPC route. |
| `'HANDLES_ENDPOINT'` | `SYMBOL` (Controller/Handler) | `API_ENDPOINT` | `'DETERMINISTIC_PARSER'` | Code symbol handles incoming endpoint requests. |
| `'INVOKES_EXTERNAL_API'` | `SYMBOL`, `COMPONENT` | `API_ENDPOINT`, `EXTERNAL_SYSTEM` | `'HYBRID_AI_STATIC'` | Outbound HTTP/SOAP/gRPC client call (`{"target_host": "api.stripe.com"}`). |
| `'DEPLOYED_ON'` | `SERVICE`, `DB_TABLE` | `INFRA_RESOURCE` | `'DETERMINISTIC_PARSER'` | Service/store provisioned on container or IaC resource. |

### 3.4 Business Logic, Requirement & Testing Edges

| `relationship_type` | Valid `source_entity_id` Types | Valid `target_entity_id` Types | Default `origin_type` | Semantics & `edge_metadata` Schema |
| :--- | :--- | :--- | :--- | :--- |
| `'IMPLEMENTS_RULE'` | `SYMBOL`, `COMPONENT` | `BUSINESS_CONCEPT` (`business_rules`) | `'HYBRID_AI_STATIC'` | Code symbol implements extracted domain business rule. |
| `'DERIVES_REQUIREMENT'` | `BUSINESS_CONCEPT` (Rule) | `BUSINESS_CONCEPT` (`requirements`) | `'AI_INFERRED'` | Requirement is derived from underlying business rule. |
| `'SATISFIES_REQ'` | `SYMBOL`, `COMPONENT`, `API_ENDPOINT` | `BUSINESS_CONCEPT` (`requirements`) | `'HYBRID_AI_STATIC'` | Architectural or code element satisfies requirement. |
| `'TESTED_BY'` | `SYMBOL`, `BUSINESS_CONCEPT` | `SYMBOL` (`test_cases`) | `'DETERMINISTIC_RULE'` | Target entity is covered by unit/integration/characterization test. |
| `'DEPENDS_ON'` | `COMPONENT`, `SERVICE` | `COMPONENT`, `SERVICE` | `'DETERMINISTIC_RULE'` | Aggregated component-to-component dependency rolled up from symbol-level edges (`edge_weight` = total cross-component edges). |

---

## 4. Querying the Graph in PostgreSQL (Cycle-Safe Recursive CTEs)

For interactive UI queries (e.g., rendering a 1-to-3 hop impact/blast-radius neighborhood around a selected `knowledge_entity` in React Flow), LegacyIQ executes bounded recursive CTEs directly in PostgreSQL using PostgreSQL's built-in `CYCLE` detection clause (supported natively in PostgreSQL 14–17):

```sql
-- Example: 3-Hop Downstream Impact Traversal with Native PG17 CYCLE Guard
WITH RECURSIVE impact_graph AS (
    -- Anchor member: direct outgoing edges from selected root entity
    SELECT
        kr.tenant_id,
        kr.id AS edge_id,
        kr.source_entity_id,
        kr.target_entity_id,
        kr.relationship_type,
        kr.confidence_score,
        kr.edge_weight,
        1 AS hop_depth
    FROM knowledge_relationships kr
    WHERE kr.tenant_id = current_setting('app.current_tenant_id')::uuid
      AND kr.snapshot_id = :snapshot_id
      AND kr.analysis_run_id = :analysis_run_id
      AND kr.source_entity_id = :root_entity_id
      AND kr.review_status != 'REJECTED'

    UNION ALL

    -- Recursive member: traverse up to max_hops (e.g., 3)
    SELECT
        next_kr.tenant_id,
        next_kr.id AS edge_id,
        next_kr.source_entity_id,
        next_kr.target_entity_id,
        next_kr.relationship_type,
        next_kr.confidence_score,
        next_kr.edge_weight,
        ig.hop_depth + 1 AS hop_depth
    FROM knowledge_relationships next_kr
    INNER JOIN impact_graph ig
        ON next_kr.tenant_id = ig.tenant_id
       AND next_kr.source_entity_id = ig.target_entity_id
    WHERE next_kr.snapshot_id = :snapshot_id
      AND next_kr.analysis_run_id = :analysis_run_id
      AND next_kr.review_status != 'REJECTED'
      AND ig.hop_depth < 3
)
CYCLE source_entity_id, target_entity_id SET is_cycle USING traversal_path
SELECT DISTINCT ON (edge_id)
    edge_id,
    source_entity_id,
    target_entity_id,
    relationship_type,
    confidence_score,
    edge_weight,
    hop_depth,
    is_cycle
FROM impact_graph
WHERE NOT is_cycle
LIMIT 1500;
```

---

## 5. NetworkX In-Memory Projection Protocol

When executing whole-repository graph algorithms during an `analysis_run`:

1. **Scoped Streaming Load**:
   - Worker queries `knowledge_entities` and `knowledge_relationships` filtered by `(tenant_id, snapshot_id, analysis_run_id)` using server-side cursor streaming (`yield_per(5000)`).
2. **Graph Construction (`nx.MultiDiGraph`)**:
   - Constructs a directed multigraph where nodes are `knowledge_entities.id` and edges carry `relationship_type`, `edge_weight`, and `confidence_score`.
3. **Computed Graph Algorithms**:
   - **Tarjan's Strongly Connected Components (`nx.strongly_connected_components`)**: Detects circular dependencies among modules, classes, or services; emits `findings` (`finding_category = 'ARCHITECTURE'`, `technical_debt_items.debt_category = 'CIRCULAR_DEPENDENCY'`).
   - **PageRank & Betweenness Centrality (`nx.pagerank`, `nx.betweenness_centrality`)**: Identifies critical architectural hubs and "God classes" (`debt_category = 'GOD_CLASS'`).
   - **Weakly Connected Components & Community Detection (`nx.community.louvain_communities`)**: Proposes candidate microservice/module decomposition boundaries for `modernization_recommendations` (`strategy_pattern = 'EXTRACT_DOMAIN_SERVICE'`).
   - **Topological Sort & Layering (`nx.topological_generations` on condensed DAG)**: Computes vertical/horizontal rank coordinates cached in `knowledge_entities.attributes_json` (`{"layout_rank": 2, "pagerank": 0.0412, "in_degree": 18, "out_degree": 4}`) for instant React Flow rendering.

