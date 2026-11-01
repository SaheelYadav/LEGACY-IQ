"""SQLAlchemy ORM models package (Wave 1 + Wave 2 + Wave 3 + Wave 4 — 65 Canonical Tables across Domains A, B, C, D, E, F, G, H, I, J)."""

from app.db.base import Base
from app.models.agent_orchestration import (
    AgentExecutionEvent,
    AgentRun,
    AgentTaskDependency,
    ModelInvocation,
    PromptTemplate,
)
from app.models.business_intelligence import (
    BusinessDomain,
    BusinessProcess,
    BusinessRule,
    Requirement,
    RequirementAcceptanceCriterion,
    RequirementTraceabilityLink,
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
from app.models.testing_modernization import (
    ModernizationRecommendation,
    TechnicalDebtItem,
    TestCase,
    TestCoverageLink,
    TestSuite,
)
from app.models.reporting_governance import (
    ApprovalRequest,
    AuditLog,
    DeletionRequest,
    IntelligenceReport,
    IntelligenceReportVersion,
    QaConversation,
    QaMessage,
    ReportExport,
    RetentionPolicy,
    TenantSubscription,
    TenantUsageQuota,
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
    # Domain G (6)
    "BusinessDomain",
    "BusinessProcess",
    "BusinessRule",
    "Requirement",
    "RequirementAcceptanceCriterion",
    "RequirementTraceabilityLink",
    # Domain H (5)
    "TestSuite",
    "TestCase",
    "TestCoverageLink",
    "TechnicalDebtItem",
    "ModernizationRecommendation",
    # Domain I remaining (7)
    "AgentRun",
    "AgentTaskDependency",
    "PromptTemplate",
    "ModelInvocation",
    "AgentExecutionEvent",
    "QaConversation",
    "QaMessage",
    # Domain J (3)
    "EmbeddingModelVersion",
    "DocumentChunk",
    "ArtifactEmbedding",
    # Domain K (9)
    "AuditLog",
    "ApprovalRequest",
    "RetentionPolicy",
    "DeletionRequest",
    "TenantSubscription",
    "TenantUsageQuota",
    "IntelligenceReport",
    "IntelligenceReportVersion",
    "ReportExport",
]
