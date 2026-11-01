"""Domain I: AI Orchestration & Telemetry remaining models (5 Tables; `analysis_runs` is in `code_intelligence.py`)."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CHAR,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TenantScopedMixin


class AgentRun(Base, TenantScopedMixin):
    """I2. Tracks execution of individual specialized AI agents within an `analysis_run` (`TENANT_DIRECT`)."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_agent_runs_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            ondelete="CASCADE",
            name="fk_agent_runs_analysis_run",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "parent_agent_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_agent_runs_parent",
        ),
    )

    analysis_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    parent_agent_run_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="PENDING", server_default="PENDING", nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    input_context_refs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    output_summary_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentTaskDependency(Base, TenantScopedMixin):
    """I3. DAG edge table enforcing execution order and verification gates between `agent_runs` (`TENANT_DIRECT`)."""

    __tablename__ = "agent_task_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "upstream_agent_run_id",
            "downstream_agent_run_id",
            name="uq_agent_task_deps_up_down",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_agent_task_deps_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            ondelete="CASCADE",
            name="fk_agent_task_deps_analysis_run",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "upstream_agent_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            ondelete="CASCADE",
            name="fk_agent_task_deps_upstream",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "downstream_agent_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            ondelete="CASCADE",
            name="fk_agent_task_deps_downstream",
        ),
    )

    analysis_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    upstream_agent_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    downstream_agent_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    dependency_kind: Mapped[str] = mapped_column(
        String(32),
        default="DATA_PREREQUISITE",
        server_default="DATA_PREREQUISITE",
        nullable=False,
    )


class PromptTemplate(Base, CreatedAtMixin):
    """I4. Immutable versioned registry of system and user prompt templates (`HYBRID_CATALOG`)."""

    __tablename__ = "prompt_templates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_prompt_templates_tenant",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4, nullable=False)
    tenant_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    template_key: Mapped[str] = mapped_column(String(96), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    target_agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    template_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    system_prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    user_prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    output_json_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )


class ModelInvocation(Base, TenantScopedMixin):
    """I5. Records every individual LLM call (local Ollama or fallback provider) (`TENANT_DIRECT`)."""

    __tablename__ = "model_invocations"
    __table_args__ = (
        Index("ix_model_inv_agent", "tenant_id", "agent_run_id"),
        Index("ix_model_inv_time", "tenant_id", "invoked_at"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_model_invocations_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "agent_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            ondelete="CASCADE",
            name="fk_model_invocations_agent_run",
        ),
        ForeignKeyConstraint(
            ["prompt_template_id"],
            ["prompt_templates.id"],
            ondelete="RESTRICT",
            name="fk_model_invocations_prompt_template",
        ),
    )

    agent_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    prompt_template_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_name: Mapped[str] = mapped_column(String(32), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    is_fallback_invocation: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    rendered_prompt_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    storage_payload_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    invoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )


class AgentExecutionEvent(Base, TenantScopedMixin):
    """I6. Fine-grained step telemetry emitted during `agent_runs` (`TENANT_DIRECT`)."""

    __tablename__ = "agent_execution_events"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "agent_run_id",
            "sequence_no",
            name="uq_agent_exec_events_run_seq",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_agent_exec_events_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "agent_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            ondelete="CASCADE",
            name="fk_agent_exec_events_agent_run",
        ),
    )

    agent_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    event_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

