"""Wave 1 Part 3: Vector Retrieval (Domain J), HNSW/GIN Indexes, PostgreSQL RLS & Default Seeds.

Revision ID: 0003_wave1_rls_vec
Revises: 0002_wave1_code_intel
Create Date: 2026-11-01
"""

from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_wave1_rls_vec"
down_revision: Union[str, None] = "0002_wave1_code_intel"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_DIRECT_WAVE1_TABLES: tuple[str, ...] = (
    "organization_memberships",
    "teams",
    "team_memberships",
    "workspaces",
    "projects",
    "project_memberships",
    "applications",
    "application_environments",
    "analysis_scopes",
    "source_connectors",
    "repositories",
    "repository_branches",
    "repository_commits",
    "repository_snapshots",
    "artifacts",
    "artifact_versions",
    "ingestion_jobs",
    "analysis_runs",
    "code_modules",
    "code_files",
    "code_symbols",
    "code_imports",
    "code_call_edges",
    "code_type_hierarchies",
    "code_symbol_references",
    "document_chunks",
    "artifact_embeddings",
)

ALL_WAVE1_TABLES: tuple[str, ...] = (
    "organizations",
    "users",
    "roles",
    "permissions",
    "role_permissions",
    "embedding_model_versions",
    *TENANT_DIRECT_WAVE1_TABLES,
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 1. Domain J tables (3 tables)
    op.create_table(
        "embedding_model_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("model_revision", sa.String(length=64), server_default="main", nullable=False),
        sa.Column("vector_dimension", sa.Integer(), server_default="384", nullable=False),
        sa.Column("distance_metric", sa.String(length=32), server_default="COSINE", nullable=False),
        sa.Column("is_active_default", sa.Boolean(), server_default="true", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_embedding_model_versions"),
        sa.UniqueConstraint(
            "provider_name",
            "model_name",
            "model_revision",
            name="uq_embedding_model_versions_provider_model_rev",
        ),
    )

    op.create_table(
        "document_chunks",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("artifact_version_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_strategy", sa.String(length=48), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("chunk_text_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column(
            "metadata_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_document_chunks_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "artifact_version_id"],
            ["artifact_versions.tenant_id", "artifact_versions.id"],
            name="fk_document_chunks_artifact_version",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_document_chunks"),
        sa.UniqueConstraint(
            "tenant_id",
            "artifact_version_id",
            "chunk_strategy",
            "chunk_index",
            name="uq_doc_chunks_ver_strat_idx",
        ),
    )
    op.execute(
        """
        ALTER TABLE document_chunks
        ADD COLUMN search_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('simple', coalesce(chunk_text, ''))) STORED;

        CREATE INDEX ix_doc_chunks_search_tsv
        ON document_chunks USING gin (search_tsv);
        """
    )

    op.create_table(
        "artifact_embeddings",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_chunk_id", sa.Uuid(), nullable=False),
        sa.Column("embedding_model_version_id", sa.Uuid(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["embedding_model_version_id"],
            ["embedding_model_versions.id"],
            name="fk_artifact_embeddings_model_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_artifact_embeddings_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_chunk_id"],
            ["document_chunks.tenant_id", "document_chunks.id"],
            name="fk_artifact_embeddings_chunk",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_artifact_embeddings"),
        sa.UniqueConstraint(
            "tenant_id",
            "document_chunk_id",
            "embedding_model_version_id",
            name="uq_artifact_embeddings_chunk_model",
        ),
    )
    op.execute(
        """
        CREATE INDEX ix_artifact_embeddings_hnsw_cosine
        ON artifact_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
        """
    )

    # 2. Grant DML privileges on all 33 Wave 1 tables to `legacyiq_app`
    for tbl in ALL_WAVE1_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {tbl} TO legacyiq_app;")

    # 3. Enable & Force Row-Level Security on `organizations`, `roles`, and all 27 TENANT_DIRECT tables
    op.execute(
        """
        ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
        ALTER TABLE organizations FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_root_isolation_policy ON organizations
            AS PERMISSIVE
            FOR ALL
            TO legacyiq_app
            USING (id = app_current_tenant_id())
            WITH CHECK (id = app_current_tenant_id());
        """
    )

    op.execute(
        """
        ALTER TABLE roles ENABLE ROW LEVEL SECURITY;
        ALTER TABLE roles FORCE ROW LEVEL SECURITY;
        CREATE POLICY roles_select_policy ON roles
            FOR SELECT
            TO legacyiq_app
            USING (tenant_id IS NULL OR tenant_id = app_current_tenant_id());
        CREATE POLICY roles_write_policy ON roles
            FOR ALL
            TO legacyiq_app
            USING (tenant_id = app_current_tenant_id())
            WITH CHECK (tenant_id = app_current_tenant_id());
        """
    )

    for tbl in TENANT_DIRECT_WAVE1_TABLES:
        op.execute(
            f"""
            ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;
            CREATE POLICY tenant_isolation_policy ON {tbl}
                AS PERMISSIVE
                FOR ALL
                TO legacyiq_app
                USING (tenant_id = app_current_tenant_id())
                WITH CHECK (tenant_id = app_current_tenant_id());
            """
        )

    # 4. Seed Default Global Permissions, System Roles, and Default Embedding Model Version
    op.execute(
        """
        INSERT INTO permissions (id, code, category, description) VALUES
            ('00000000-0000-7000-8000-000000000101', 'org:manage', 'IDENTITY', 'Manage organization settings, teams, and members'),
            ('00000000-0000-7000-8000-000000000102', 'project:create', 'PROJECT', 'Create and configure workspaces and projects'),
            ('00000000-0000-7000-8000-000000000103', 'project:view', 'PROJECT', 'View project, application, and snapshot metadata'),
            ('00000000-0000-7000-8000-000000000104', 'repo:ingest', 'INGESTION', 'Upload ZIP archives, register repositories, and trigger ingestion'),
            ('00000000-0000-7000-8000-000000000105', 'analysis:run', 'ANALYSIS', 'Trigger deterministic code parsing and vector indexing'),
            ('00000000-0000-7000-8000-000000000106', 'code:search', 'RETRIEVAL', 'Query code symbols, call edges, and semantic search')
        ON CONFLICT (code) DO NOTHING;

        INSERT INTO roles (id, tenant_id, code, name, is_system_role) VALUES
            ('00000000-0000-7000-8000-000000000201', NULL, 'ORG_OWNER', 'Organization Owner', true),
            ('00000000-0000-7000-8000-000000000202', NULL, 'ARCHITECT', 'Lead Architect', true),
            ('00000000-0000-7000-8000-000000000203', NULL, 'REVIEWER', 'Engineering Reviewer', true),
            ('00000000-0000-7000-8000-000000000204', NULL, 'VIEWER', 'Read-Only Viewer', true)
        ON CONFLICT DO NOTHING;

        -- ORG_OWNER gets all permissions
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT '00000000-0000-7000-8000-000000000201'::uuid, id FROM permissions
        ON CONFLICT DO NOTHING;

        -- ARCHITECT gets project, repo, analysis, and search permissions
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT '00000000-0000-7000-8000-000000000202'::uuid, id FROM permissions
        WHERE code IN ('project:create', 'project:view', 'repo:ingest', 'analysis:run', 'code:search')
        ON CONFLICT DO NOTHING;

        -- REVIEWER gets project:view, repo:ingest, analysis:run, code:search
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT '00000000-0000-7000-8000-000000000203'::uuid, id FROM permissions
        WHERE code IN ('project:view', 'repo:ingest', 'analysis:run', 'code:search')
        ON CONFLICT DO NOTHING;

        -- VIEWER gets project:view and code:search
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT '00000000-0000-7000-8000-000000000204'::uuid, id FROM permissions
        WHERE code IN ('project:view', 'code:search')
        ON CONFLICT DO NOTHING;

        -- Default 384-dim BAAI/bge-small-en-v1.5 Embedding Model Version
        INSERT INTO embedding_model_versions (
            id, provider_name, model_name, model_revision, vector_dimension, distance_metric, is_active_default
        ) VALUES (
            '00000000-0000-7000-8000-000000000301',
            'sentence_transformers',
            'BAAI/bge-small-en-v1.5',
            'main',
            384,
            'COSINE',
            true
        ) ON CONFLICT (provider_name, model_name, model_revision) DO NOTHING;
        """
    )


def downgrade() -> None:
    for tbl in reversed(TENANT_DIRECT_WAVE1_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {tbl};")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")

    op.execute("DROP POLICY IF EXISTS roles_write_policy ON roles;")
    op.execute("DROP POLICY IF EXISTS roles_select_policy ON roles;")
    op.execute("ALTER TABLE roles DISABLE ROW LEVEL SECURITY;")

    op.execute("DROP POLICY IF EXISTS tenant_root_isolation_policy ON organizations;")
    op.execute("ALTER TABLE organizations DISABLE ROW LEVEL SECURITY;")

    op.execute("DROP INDEX IF EXISTS ix_artifact_embeddings_hnsw_cosine;")
    op.drop_table("artifact_embeddings")
    op.execute("DROP INDEX IF EXISTS ix_doc_chunks_search_tsv;")
    op.drop_table("document_chunks")
    op.drop_table("embedding_model_versions")

