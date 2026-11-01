"""Foundational agent protocol for evidence-backed codebase analysis (M0 Stub)."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class CodeEvidenceRef:
    """Mandatory source file and line-range evidence reference."""

    file_path: str
    start_line: int
    end_line: int
    symbol_name: str | None = None


@dataclass
class GroundedAgentOutput:
    """Structured output requiring verifiable source code citations."""

    summary: str
    evidence: list[CodeEvidenceRef] = field(default_factory=list)


class DiscoveryAgentProtocol(Protocol):
    """Protocol implemented by M1+ discovery and requirements agents."""

    name: str

