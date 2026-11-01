"""Wave 1 Part 1: Identity, Tenancy (Domain A) & Workspace/Project Management (Domain B).

Revision ID: 0001_wave1_identity
Revises: None
Create Date: 2026-11-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_wave1_identity"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create non-superuser, NOBYPASSRLS application runtime role `legacyiq_app`
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'legacyiq_app') THEN
                CREATE ROLE legacyiq_app NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
            END IF;
        END
        $$;
        GRANT USAGE ON SCHEMA public TO legacyiq_app;
        """
    )

    # 2. Create session tenant resolver function `app_current_tenant_id()`
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_current_tenant_id()
        RETURNS uuid
        LANGUAGE sql
        STABLE
        PARALLEL SAFE
        AS $$
            SELECT NULLIF(current_setting('app.current_tenant_id', true), '')::uuid;
        $$;
        """
    )

    # 3. Domain A tables (8 tables)
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("tier", sa.String(length=32), server_default="FREE", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="ACTIVE", nullable=False),
        sa.Column("kms_key_id", sa.Uuid(), nullable=True),
        sa.Column("legal_hold_active", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "settings_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_index("ix_organizations_status", "organizations", ["status"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("auth_provider", sa.String(length=32), server_default="LOCAL", nullable=False),
        sa.Column("external_subject_id", sa.String(length=255), nullable=True),
        sa.Column("is_system_admin", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint(
            "auth_provider", "external_subject_id", name="uq_users_provider_subject"
        ),
    )

    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("is_system_role", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_roles_tenant_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ux_roles_tenant_code
        ON roles (COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid), code);
        """
    )

    op.create_table(
        "permissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=96), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_permissions"),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name="fk_role_permissions_permission_id_permissions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_role_permissions_role_id_roles",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name="pk_role_permissions"),
    )

    op.create_table(
        "organization_memberships",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="ACTIVE", nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_org_memberships_role",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_org_memberships_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_org_memberships_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_organization_memberships"),
        sa.UniqueConstraint("tenant_id", "user_id", name="ux_org_members_tenant_user"),
    )

    op.create_table(
        "teams",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_teams_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_teams"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_teams_tenant_name"),
    )

    op.create_table(
        "team_memberships",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("org_membership_id", sa.Uuid(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_team_memberships_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "org_membership_id"],
            ["organization_memberships.tenant_id", "organization_memberships.id"],
            name="fk_team_memberships_org_member",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "team_id"],
            ["teams.tenant_id", "teams.id"],
            name="fk_team_memberships_team",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_team_memberships"),
        sa.UniqueConstraint(
            "tenant_id",
            "team_id",
            "org_membership_id",
            name="uq_team_memberships_member",
        ),
    )

    # 4. Domain B tables (6 tables)
    op.create_table(
        "workspaces",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_workspaces_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_workspaces"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_workspaces_tenant_slug"),
    )

    op.create_table(
        "projects",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("lifecycle_status", sa.String(length=32), server_default="ACTIVE", nullable=False),
        sa.Column("legal_hold_active", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_projects_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workspace_id"],
            ["workspaces.tenant_id", "workspaces.id"],
            name="fk_projects_workspace",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_projects"),
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "key", name="ux_projects_workspace_key"
        ),
    )

    op.create_table(
        "project_memberships",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("org_membership_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_project_memberships_role",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_project_memberships_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "org_membership_id"],
            ["organization_memberships.tenant_id", "organization_memberships.id"],
            name="fk_project_memberships_org_member",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            name="fk_project_memberships_project",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_project_memberships"),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "org_membership_id",
            name="uq_project_memberships_member",
        ),
    )

    op.create_table(
        "applications",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("architecture_style", sa.String(length=64), nullable=True),
        sa.Column(
            "criticality_tier", sa.String(length=32), server_default="TIER_2", nullable=False
        ),
        sa.Column(
            "primary_languages",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_applications_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            name="fk_applications_project",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_applications"),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "code", name="ux_applications_proj_code"
        ),
    )

    op.create_table(
        "application_environments",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("env_name", sa.String(length=64), nullable=False),
        sa.Column("env_type", sa.String(length=32), nullable=False),
        sa.Column(
            "metadata_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_app_environments_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            name="fk_app_environments_application",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_application_environments"),
        sa.UniqueConstraint(
            "tenant_id",
            "application_id",
            "env_name",
            name="uq_app_environments_name",
        ),
    )

    op.create_table(
        "analysis_scopes",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "include_globs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='["**/*"]',
            nullable=False,
        ),
        sa.Column(
            "exclude_globs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='["**/node_modules/**","**/vendor/**","**/.git/**","**/__pycache__/**"]',
            nullable=False,
        ),
        sa.Column(
            "language_parsers_enabled",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='["python","java","javascript","typescript","php"]',
            nullable=False,
        ),
        sa.Column(
            "max_file_size_bytes", sa.Integer(), server_default="5242880", nullable=False
        ),
        sa.Column("is_default", sa.Boolean(), server_default="true", nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_analysis_scopes_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            name="fk_analysis_scopes_application",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_analysis_scopes"),
        sa.UniqueConstraint(
            "tenant_id", "application_id", "name", name="uq_analysis_scopes_name"
        ),
    )

    # 5. Hybrid Catalog Role Cross-Tenant Guard Trigger (`D3-ISS-001`)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_hybrid_role_tenant_match()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            v_role_tenant uuid;
        BEGIN
            SELECT r.tenant_id INTO v_role_tenant
            FROM roles r
            WHERE r.id = NEW.role_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION 'Referenced role_id % does not exist', NEW.role_id
                    USING ERRCODE = 'foreign_key_violation';
            END IF;

            IF v_role_tenant IS NOT NULL AND v_role_tenant != NEW.tenant_id THEN
                RAISE EXCEPTION 'Cross-tenant reference violation: role_id % belongs to a different tenant', NEW.role_id
                    USING ERRCODE = 'foreign_key_violation';
            END IF;

            RETURN NEW;
        END;
        $$;

        CREATE TRIGGER trg_org_memberships_role_tenant_guard
        BEFORE INSERT OR UPDATE OF role_id, tenant_id ON organization_memberships
        FOR EACH ROW EXECUTE FUNCTION enforce_hybrid_role_tenant_match();

        CREATE TRIGGER trg_project_memberships_role_tenant_guard
        BEFORE INSERT OR UPDATE OF role_id, tenant_id ON project_memberships
        FOR EACH ROW EXECUTE FUNCTION enforce_hybrid_role_tenant_match();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_project_memberships_role_tenant_guard ON project_memberships;")
    op.execute("DROP TRIGGER IF EXISTS trg_org_memberships_role_tenant_guard ON organization_memberships;")
    op.execute("DROP FUNCTION IF EXISTS enforce_hybrid_role_tenant_match();")

    op.drop_table("analysis_scopes")
    op.drop_table("application_environments")
    op.drop_table("applications")
    op.drop_table("project_memberships")
    op.drop_table("projects")
    op.drop_table("workspaces")
    op.drop_table("team_memberships")
    op.drop_table("teams")
    op.drop_table("organization_memberships")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("users")
    op.drop_index("ix_organizations_status", table_name="organizations")
    op.drop_table("organizations")
    op.execute("DROP FUNCTION IF EXISTS app_current_tenant_id();")

