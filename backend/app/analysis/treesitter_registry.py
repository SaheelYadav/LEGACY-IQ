"""Tree-sitter multi-language parser registry architecture (M0 Foundation)."""

from dataclasses import dataclass

SUPPORTED_LEGACY_LANGUAGES: tuple[str, ...] = (
    "python",
    "java",
    "javascript",
    "typescript",
    "php",
)


@dataclass(frozen=True)
class LanguageParserSpec:
    """Specification for a target language grammar."""

    language: str
    extensions: tuple[str, ...]


LANGUAGE_SPECS: dict[str, LanguageParserSpec] = {
    "python": LanguageParserSpec("python", (".py",)),
    "java": LanguageParserSpec("java", (".java",)),
    "javascript": LanguageParserSpec("javascript", (".js", ".jsx", ".mjs", ".cjs")),
    "typescript": LanguageParserSpec("typescript", (".ts", ".tsx")),
    "php": LanguageParserSpec("php", (".php",)),
}

