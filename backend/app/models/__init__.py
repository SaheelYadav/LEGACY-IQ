"""SQLAlchemy ORM models package (Wave 1 + Wave 2 — 54 Canonical Tables across Domains A, B, C, D, E, F, I, J)."""

from app.db.base import Base
from app.models.agent_orchestration import (
    AgentExecutionEvent,
    AgentRun,
    AgentTaskDependency,
    ModelInvocation,
    PromptTemplate,
)
from app.models.code_intelligence import (
    AnalysisRun,
    CodeCallEdge,
    CodeFile,
    CodeImport,
    CodeModule,
    CodeSymbol,
    CodeSymbolReference,
    CodeTypeHierarchy,
)
from app.models.identity import (
    Organization,
    OrganizationMembership,
    Permission,
    Role,
    RolePermission,
    Team,
    TeamMembership,
    User,
)
from app.models.ingestion import (
    Artifact,
    ArtifactVersion,
    IngestionJob,
    Repository,
    RepositoryBranch,
    RepositoryCommit,
    RepositorySnapshot,
    SourceConnector,
)
from app.models.knowledge_graph import (
    EvidenceAnchor,
    Finding,
    FindingEvidenceLink,
    KnowledgeConflict,
    KnowledgeEntity,
    KnowledgeRelationship,
    ReviewHistory,
)
from app.models.projects import (
    AnalysisScope,
    Application,
    ApplicationEnvironment,
    Project,
    ProjectMembership,
    Workspace,
)
from app.models.retrieval import (
    ArtifactEmbedding,
    DocumentChunk,
    EmbeddingModelVersion,
)
from app.models.technical_intelligence import (
    ApiEndpoint,
    ApiService,
    DbColumn,
    DbForeignKey,
    DbSchema,
    DbTable,
    DocSection,
    InfraResource,
    RuntimeObservation,
)

__all__ = [
    "Base",
    # Domain A (8)
    "Organization",
    "User",
    "Role",
    "Permission",
    "RolePermission",
    "OrganizationMembership",
    "Team",
    "TeamMembership",
    # Domain B (6)
    "Workspace",
    "Project",
    "ProjectMembership",
    "Application",
    "ApplicationEnvironment",
    "AnalysisScope",
    # Domain C (8)
    "SourceConnector",
    "Repository",
    "RepositoryBranch",
    "RepositoryCommit",
    "RepositorySnapshot",
    "Artifact",
    "ArtifactVersion",
    "IngestionJob",
    # Domain I anchor + Domain D (8)
    "AnalysisRun",
    "CodeModule",
    "CodeFile",
    "CodeSymbol",
    "CodeImport",
    "CodeCallEdge",
    "CodeTypeHierarchy",
    "CodeSymbolReference",
    # Domain E (9)
    "DbSchema",
    "DbTable",
    "DbColumn",
    "DbForeignKey",
    "ApiService",
    "ApiEndpoint",
    "InfraResource",
    "DocSection",
    "RuntimeObservation",
    # Domain F (7)
    "KnowledgeEntity",
    "KnowledgeRelationship",
    "Finding",
    "EvidenceAnchor",
    "FindingEvidenceLink",
    "KnowledgeConflict",
    "ReviewHistory",
    # Domain I remaining (5)
    "AgentRun",
    "AgentTaskDependency",
    "PromptTemplate",
    "ModelInvocation",
    "AgentExecutionEvent",
    # Domain J (3)
    "EmbeddingModelVersion",
    "DocumentChunk",
    "ArtifactEmbedding",
]
