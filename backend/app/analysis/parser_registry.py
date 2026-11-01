"""Deterministic multi-language static analysis and AST extraction registry for Wave 1."""

from __future__ import annotations

import ast
import hashlib
import os
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path

LANGUAGE_EXTENSION_MAP: dict[str, tuple[str, str]] = {
    ".py": ("python", "SOURCE_CODE"),
    ".java": ("java", "SOURCE_CODE"),
    ".js": ("javascript", "SOURCE_CODE"),
    ".jsx": ("javascript", "SOURCE_CODE"),
    ".mjs": ("javascript", "SOURCE_CODE"),
    ".cjs": ("javascript", "SOURCE_CODE"),
    ".ts": ("typescript", "SOURCE_CODE"),
    ".tsx": ("typescript", "SOURCE_CODE"),
    ".php": ("php", "SOURCE_CODE"),
    ".sql": ("sql", "DDL_SCRIPT"),
    ".md": ("markdown", "DOCUMENTATION"),
    ".rst": ("rst", "DOCUMENTATION"),
    ".txt": ("text", "DOCUMENTATION"),
    ".adoc": ("asciidoc", "DOCUMENTATION"),
    ".html": ("html", "DOCUMENTATION"),
    ".htm": ("html", "DOCUMENTATION"),
    ".pdf": ("pdf", "DOCUMENTATION"),
    ".docx": ("docx", "DOCUMENTATION"),
    ".xlsx": ("xlsx", "DOCUMENTATION"),
    ".graphql": ("graphql", "API_SPEC"),
    ".gql": ("graphql", "API_SPEC"),
    ".tf": ("terraform", "IAC_MANIFEST"),
    ".tfvars": ("terraform", "IAC_MANIFEST"),
    ".json": ("json", "CONFIG"),
    ".yaml": ("yaml", "CONFIG"),
    ".yml": ("yaml", "CONFIG"),
    ".toml": ("toml", "CONFIG"),
    ".xml": ("xml", "CONFIG"),
    ".ini": ("ini", "CONFIG"),
    ".cfg": ("ini", "CONFIG"),
    ".env.example": ("dotenv", "CONFIG"),
}

SUPPORTED_CODE_LANGUAGES: frozenset[str] = frozenset(
    {"python", "java", "javascript", "typescript", "php"}
)


def detect_language_and_kind(relative_path: str) -> tuple[str | None, str]:
    """Detect programming language and artifact kind from a normalized file path."""
    lower_path = relative_path.lower().replace("\\", "/")
    base_name = posixpath.basename(lower_path)
    if lower_path.endswith(".env.example") or base_name.startswith(".env"):
        return "dotenv", "CONFIG"
    if base_name == "dockerfile" or base_name.startswith("dockerfile.") or base_name.endswith(".dockerfile"):
        return "dockerfile", "IAC_MANIFEST"
    if "docker-compose" in base_name or base_name in ("compose.yml", "compose.yaml"):
        return "yaml", "IAC_MANIFEST"
    if "openapi" in base_name or "swagger" in base_name:
        _, ext = os.path.splitext(lower_path)
        return ("json" if ext == ".json" else "yaml"), "API_SPEC"
    _, ext = os.path.splitext(lower_path)
    if ext in LANGUAGE_EXTENSION_MAP:
        return LANGUAGE_EXTENSION_MAP[ext]
    return None, "OTHER"


def derive_module_info(relative_path: str, language: str) -> tuple[str, str]:
    """Derive canonical `(module_path, module_name)` from a relative path."""
    norm = relative_path.replace("\\", "/").strip("/")
    parent = posixpath.dirname(norm)
    base, _ = posixpath.splitext(posixpath.basename(norm))
    if language == "python":
        if base == "__init__":
            mod_path = parent or "."
            mod_name = mod_path.replace("/", ".") if mod_path != "." else "root"
        else:
            mod_path = parent or "."
            dotted_parent = parent.replace("/", ".") if parent else ""
            mod_name = f"{dotted_parent}.{base}".strip(".")
        return mod_path, mod_name
    mod_path = parent or "."
    mod_name = mod_path.replace("/", ".") if mod_path != "." else "root"
    return mod_path, mod_name


def compute_normalized_ast_hash(text_body: str) -> str:
    """Compute a deterministic SHA-256 hash over whitespace-normalized code structure."""
    normalized = re.sub(r"\s+", " ", text_body.strip())
    return hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()


def count_lines_of_code(source_text: str) -> tuple[int, int]:
    """Return `(loc_total, loc_code)` excluding blank and pure comment lines."""
    lines = source_text.splitlines()
    loc_total = len(lines)
    loc_code = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", "//", "/*", "*", "*/")):
            continue
        loc_code += 1
    return loc_total, loc_code


@dataclass
class ExtractedSymbol:
    qualified_name: str
    symbol_name: str
    symbol_kind: str  # CLASS, INTERFACE, FUNCTION, METHOD, VARIABLE, CONSTANT
    visibility: str  # PUBLIC, PROTECTED, PRIVATE, INTERNAL
    signature_text: str
    docstring_text: str | None
    body_ast_hash: str
    start_line: int
    end_line: int
    start_col: int
    end_col: int
    cyclomatic_complexity: int
    parent_qualified_name: str | None = None
    calls_made: list[tuple[str, int, bool]] = field(default_factory=list)  # (callee_name, line, is_dynamic)
    base_types: list[tuple[str, str]] = field(default_factory=list)  # (parent_type_name, relationship_kind)


@dataclass
class ExtractedImport:
    imported_module_name: str
    imported_symbol_name: str | None
    is_relative: bool
    is_external: bool
    line_number: int


@dataclass
class ExtractedReference:
    target_symbol_name: str
    reference_kind: str  # CALL, INSTANTIATION, TYPE_ANNOTATION, IMPORT, READ, WRITE
    line_number: int
    col_number: int


@dataclass
class FileParseResult:
    language: str
    parser_version: str
    parse_status: str  # PARSED, PARSE_ERROR
    loc_total: int
    loc_code: int
    module_path: str
    module_name: str
    symbols: list[ExtractedSymbol] = field(default_factory=list)
    imports: list[ExtractedImport] = field(default_factory=list)
    references: list[ExtractedReference] = field(default_factory=list)
    error_message: str | None = None


class PythonAstParser:
    """Deterministic Python AST extractor using stdlib `ast` (never executes code)."""

    parser_version = "python-ast-1.0"

    def parse(self, relative_path: str, source_text: str) -> FileParseResult:
        loc_total, loc_code = count_lines_of_code(source_text)
        module_path, module_name = derive_module_info(relative_path, "python")
        try:
            tree = ast.parse(source_text, filename=relative_path)
        except SyntaxError as exc:
            return FileParseResult(
                language="python",
                parser_version=self.parser_version,
                parse_status="PARSE_ERROR",
                loc_total=loc_total,
                loc_code=loc_code,
                module_path=module_path,
                module_name=module_name,
                error_message=f"SyntaxError at line {exc.lineno}: {exc.msg}",
            )

        lines = source_text.splitlines()
        symbols: list[ExtractedSymbol] = []
        imports: list[ExtractedImport] = []
        references: list[ExtractedReference] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(
                        ExtractedImport(
                            imported_module_name=alias.name,
                            imported_symbol_name=alias.asname,
                            is_relative=False,
                            is_external=True,
                            line_number=getattr(node, "lineno", 1),
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                is_rel = (node.level or 0) > 0
                prefix = "." * (node.level or 0)
                full_mod = f"{prefix}{mod}" if mod else prefix
                for alias in node.names:
                    imports.append(
                        ExtractedImport(
                            imported_module_name=full_mod,
                            imported_symbol_name=alias.name,
                            is_relative=is_rel,
                            is_external=not is_rel,
                            line_number=getattr(node, "lineno", 1),
                        )
                    )
                    references.append(
                        ExtractedReference(
                            target_symbol_name=alias.name,
                            reference_kind="IMPORT",
                            line_number=getattr(node, "lineno", 1),
                            col_number=getattr(node, "col_offset", 0),
                        )
                    )

        self._visit_body(
            body=tree.body,
            parent_qname=module_name,
            parent_is_class=False,
            lines=lines,
            symbols=symbols,
            references=references,
        )

        return FileParseResult(
            language="python",
            parser_version=self.parser_version,
            parse_status="PARSED",
            loc_total=loc_total,
            loc_code=loc_code,
            module_path=module_path,
            module_name=module_name,
            symbols=symbols,
            imports=imports,
            references=references,
        )

    def _visit_body(
        self,
        *,
        body: list[ast.stmt],
        parent_qname: str,
        parent_is_class: bool,
        lines: list[str],
        symbols: list[ExtractedSymbol],
        references: list[ExtractedReference],
    ) -> None:
        for stmt in body:
            if isinstance(stmt, ast.ClassDef):
                qname = f"{parent_qname}.{stmt.name}" if parent_qname else stmt.name
                visibility = "PRIVATE" if stmt.name.startswith("_") else "PUBLIC"
                start_line = getattr(stmt, "lineno", 1)
                end_line = getattr(stmt, "end_lineno", start_line)
                base_names: list[tuple[str, str]] = []
                for base in stmt.bases:
                    bname = self._expr_name(base)
                    if bname:
                        base_names.append((bname, "EXTENDS"))
                        references.append(
                            ExtractedReference(
                                target_symbol_name=bname.split(".")[-1],
                                reference_kind="TYPE_ANNOTATION",
                                line_number=start_line,
                                col_number=getattr(base, "col_offset", 0),
                            )
                        )
                sig_bases = ", ".join(b[0] for b in base_names)
                sig = f"class {stmt.name}({sig_bases})" if sig_bases else f"class {stmt.name}"
                doc = ast.get_docstring(stmt)
                body_dump = ast.dump(stmt, include_attributes=False)
                ast_hash = hashlib.sha256(body_dump.encode("utf-8")).hexdigest()
                sym = ExtractedSymbol(
                    qualified_name=qname,
                    symbol_name=stmt.name,
                    symbol_kind="CLASS",
                    visibility=visibility,
                    signature_text=sig,
                    docstring_text=doc,
                    body_ast_hash=ast_hash,
                    start_line=start_line,
                    end_line=end_line,
                    start_col=getattr(stmt, "col_offset", 0),
                    end_col=getattr(stmt, "end_col_offset", 0) or 0,
                    cyclomatic_complexity=self._calc_complexity(stmt),
                    parent_qualified_name=parent_qname if parent_is_class else None,
                    base_types=base_names,
                )
                symbols.append(sym)
                self._visit_body(
                    body=stmt.body,
                    parent_qname=qname,
                    parent_is_class=True,
                    lines=lines,
                    symbols=symbols,
                    references=references,
                )
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qname = f"{parent_qname}.{stmt.name}" if parent_qname else stmt.name
                kind = "METHOD" if parent_is_class else "FUNCTION"
                if stmt.name.startswith("__") and not stmt.name.endswith("__"):
                    visibility = "PRIVATE"
                elif stmt.name.startswith("_"):
                    visibility = "PROTECTED"
                else:
                    visibility = "PUBLIC"
                start_line = getattr(stmt, "lineno", 1)
                end_line = getattr(stmt, "end_lineno", start_line)
                arg_names = [a.arg for a in stmt.args.args]
                prefix = "async def" if isinstance(stmt, ast.AsyncFunctionDef) else "def"
                sig = f"{prefix} {stmt.name}({', '.join(arg_names)})"
                doc = ast.get_docstring(stmt)
                body_dump = ast.dump(stmt, include_attributes=False)
                ast_hash = hashlib.sha256(body_dump.encode("utf-8")).hexdigest()
                calls = self._extract_calls(stmt, references)
                sym = ExtractedSymbol(
                    qualified_name=qname,
                    symbol_name=stmt.name,
                    symbol_kind=kind,
                    visibility=visibility,
                    signature_text=sig,
                    docstring_text=doc,
                    body_ast_hash=ast_hash,
                    start_line=start_line,
                    end_line=end_line,
                    start_col=getattr(stmt, "col_offset", 0),
                    end_col=getattr(stmt, "end_col_offset", 0) or 0,
                    cyclomatic_complexity=self._calc_complexity(stmt),
                    parent_qualified_name=parent_qname if parent_is_class else None,
                    calls_made=calls,
                )
                symbols.append(sym)
            elif isinstance(stmt, ast.Assign) and not parent_is_class:
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        qname = f"{parent_qname}.{target.id}" if parent_qname else target.id
                        start_line = getattr(stmt, "lineno", 1)
                        end_line = getattr(stmt, "end_lineno", start_line)
                        body_dump = ast.dump(stmt, include_attributes=False)
                        symbols.append(
                            ExtractedSymbol(
                                qualified_name=qname,
                                symbol_name=target.id,
                                symbol_kind="CONSTANT",
                                visibility="PUBLIC",
                                signature_text=f"{target.id} = ...",
                                docstring_text=None,
                                body_ast_hash=hashlib.sha256(body_dump.encode("utf-8")).hexdigest(),
                                start_line=start_line,
                                end_line=end_line,
                                start_col=getattr(stmt, "col_offset", 0),
                                end_col=getattr(stmt, "end_col_offset", 0) or 0,
                                cyclomatic_complexity=1,
                            )
                        )

    @staticmethod
    def _calc_complexity(node: ast.AST) -> int:
        complexity = 1
        for child in ast.walk(node):
            if isinstance(
                child,
                (
                    ast.If,
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                    ast.ExceptHandler,
                    ast.With,
                    ast.AsyncWith,
                    ast.IfExp,
                ),
            ):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += max(len(child.values) - 1, 1)
        return complexity

    def _extract_calls(
        self, fn_node: ast.AST, references: list[ExtractedReference]
    ) -> list[tuple[str, int, bool]]:
        calls: list[tuple[str, int, bool]] = []
        for child in ast.walk(fn_node):
            if isinstance(child, ast.Call):
                callee = self._expr_name(child.func)
                if callee:
                    line = getattr(child, "lineno", 1)
                    col = getattr(child, "col_offset", 0)
                    is_dynamic = "." in callee and not callee.startswith("self.")
                    short_name = callee.split(".")[-1]
                    calls.append((short_name, line, is_dynamic))
                    references.append(
                        ExtractedReference(
                            target_symbol_name=short_name,
                            reference_kind="CALL",
                            line_number=line,
                            col_number=col,
                        )
                    )
        return calls

    def _expr_name(self, expr: ast.AST) -> str | None:
        if isinstance(expr, ast.Name):
            return expr.id
        if isinstance(expr, ast.Attribute):
            base = self._expr_name(expr.value)
            return f"{base}.{expr.attr}" if base else expr.attr
        return None


class BraceStructuralParser:
    """
    Deterministic structural parser for Java, JavaScript, TypeScript, and PHP.
    Extracts classes/interfaces, methods/functions, imports, type hierarchies, and call edges.
    """

    def __init__(self, language: str) -> None:
        self.language = language
        self.parser_version = f"{language}-structural-1.0"

    def parse(self, relative_path: str, source_text: str) -> FileParseResult:
        loc_total, loc_code = count_lines_of_code(source_text)
        module_path, module_name = derive_module_info(relative_path, self.language)
        lines = source_text.splitlines()
        symbols: list[ExtractedSymbol] = []
        imports: list[ExtractedImport] = []
        references: list[ExtractedReference] = []

        # Package / namespace override for Java & PHP
        for line in lines[:40]:
            s = line.strip()
            if self.language == "java" and s.startswith("package "):
                pkg = s[len("package ") :].rstrip(";").strip()
                if pkg:
                    module_name = pkg
                break
            if self.language == "php" and s.startswith("namespace "):
                ns = s[len("namespace ") :].rstrip(";{").strip().replace("\\", ".")
                if ns:
                    module_name = ns
                break

        # Imports extraction
        for idx, line in enumerate(lines, start=1):
            s = line.strip()
            if self.language == "java" and s.startswith("import "):
                imp = s[len("import ") :].rstrip(";").strip()
                if imp.startswith("static "):
                    imp = imp[len("static ") :].strip()
                parts = imp.split(".")
                sym_name = parts[-1] if parts else None
                imports.append(
                    ExtractedImport(
                        imported_module_name=imp,
                        imported_symbol_name=sym_name,
                        is_relative=False,
                        is_external=True,
                        line_number=idx,
                    )
                )
            elif self.language in ("javascript", "typescript"):
                m_from = re.match(
                    r"^import\s+(.+?)\s+from\s+['\"]([^'\"]+)['\"]", s
                )
                if m_from:
                    spec, mod = m_from.group(1).strip(), m_from.group(2).strip()
                    is_rel = mod.startswith(".")
                    sym_names = [
                        tok.strip().split(" as ")[0].strip()
                        for tok in re.sub(r"[{}]", "", spec).split(",")
                        if tok.strip()
                    ]
                    for sym_n in sym_names or [None]:
                        imports.append(
                            ExtractedImport(
                                imported_module_name=mod,
                                imported_symbol_name=sym_n,
                                is_relative=is_rel,
                                is_external=not is_rel,
                                line_number=idx,
                            )
                        )
            elif self.language == "php" and s.startswith("use "):
                imp = s[len("use ") :].rstrip(";").strip().replace("\\", ".")
                sym_n = imp.split(".")[-1]
                imports.append(
                    ExtractedImport(
                        imported_module_name=imp,
                        imported_symbol_name=sym_n,
                        is_relative=False,
                        is_external=True,
                        line_number=idx,
                    )
                )

        # Class / Interface extraction
        class_pattern = re.compile(
            r"^\s*(?:export\s+)?(?:default\s+)?(?:(public|protected|private)\s+)?"
            r"(?:abstract\s+|final\s+)*(class|interface)\s+([A-Za-z_][A-Za-z0-9_]*)"
            r"(?:\s+extends\s+([A-Za-z0-9_.,\\]+))?"
            r"(?:\s+implements\s+([A-Za-z0-9_.,\s\\]+?))?\s*(?:\{|$)"
        )
        fn_pattern = self._get_function_pattern()

        current_class_qname: str | None = None
        current_class_end_line: int = 0

        for idx, line in enumerate(lines, start=1):
            if current_class_qname and idx > current_class_end_line:
                current_class_qname = None

            cm = class_pattern.match(line)
            if cm:
                vis_raw, kind_raw, cname, ext_raw, impl_raw = cm.groups()
                vis = (vis_raw or "public").upper()
                kind = "INTERFACE" if kind_raw == "interface" else "CLASS"
                qname = f"{module_name}.{cname}" if module_name else cname
                end_line = self._find_block_end(lines, idx)
                block_text = "\n".join(lines[idx - 1 : end_line])
                base_types: list[tuple[str, str]] = []
                if ext_raw:
                    for b in ext_raw.split(","):
                        bn = b.strip().split("\\")[-1].split("<")[0].strip()
                        if bn:
                            base_types.append((bn, "EXTENDS"))
                if impl_raw:
                    for b in impl_raw.split(","):
                        bn = b.strip().split("\\")[-1].split("<")[0].strip()
                        if bn:
                            base_types.append((bn, "IMPLEMENTS"))
                symbols.append(
                    ExtractedSymbol(
                        qualified_name=qname,
                        symbol_name=cname,
                        symbol_kind=kind,
                        visibility=vis,
                        signature_text=line.strip().rstrip("{").strip(),
                        docstring_text=self._extract_leading_comment(lines, idx),
                        body_ast_hash=compute_normalized_ast_hash(block_text),
                        start_line=idx,
                        end_line=end_line,
                        start_col=len(line) - len(line.lstrip()),
                        end_col=len(line),
                        cyclomatic_complexity=self._estimate_block_complexity(block_text),
                        parent_qualified_name=None,
                        base_types=base_types,
                    )
                )
                current_class_qname = qname
                current_class_end_line = end_line
                continue

            fm = fn_pattern.match(line)
            if fm:
                vis, fname, sig_text = self._unpack_fn_match(fm, line)
                if fname in ("if", "for", "while", "switch", "catch", "return", "new"):
                    continue
                parent_q = current_class_qname or module_name
                qname = f"{parent_q}.{fname}" if parent_q else fname
                kind = "METHOD" if current_class_qname else "FUNCTION"
                end_line = self._find_block_end(lines, idx)
                block_text = "\n".join(lines[idx - 1 : end_line])
                calls = self._extract_block_calls(lines, idx, end_line, fname, references)
                symbols.append(
                    ExtractedSymbol(
                        qualified_name=qname,
                        symbol_name=fname,
                        symbol_kind=kind,
                        visibility=vis,
                        signature_text=sig_text,
                        docstring_text=self._extract_leading_comment(lines, idx),
                        body_ast_hash=compute_normalized_ast_hash(block_text),
                        start_line=idx,
                        end_line=end_line,
                        start_col=len(line) - len(line.lstrip()),
                        end_col=len(line),
                        cyclomatic_complexity=self._estimate_block_complexity(block_text),
                        parent_qualified_name=current_class_qname,
                        calls_made=calls,
                    )
                )

        return FileParseResult(
            language=self.language,
            parser_version=self.parser_version,
            parse_status="PARSED",
            loc_total=loc_total,
            loc_code=loc_code,
            module_path=module_path,
            module_name=module_name,
            symbols=symbols,
            imports=imports,
            references=references,
        )

    def _get_function_pattern(self) -> re.Pattern[str]:
        if self.language == "php":
            return re.compile(
                r"^\s*(?:(public|protected|private)\s+)?(?:static\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)"
            )
        if self.language == "java":
            return re.compile(
                r"^\s*(public|protected|private)?\s*(?:static\s+|final\s+|synchronized\s+|abstract\s+)*"
                r"(?:[A-Za-z0-9_<>\[\],\s]+\s+)([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*(?:throws\s+[A-Za-z0-9_,\s]+)?\s*\{"
            )
        # JavaScript / TypeScript
        return re.compile(
            r"^\s*(?:export\s+)?(?:default\s+)?(?:(public|protected|private)\s+)?(?:async\s+)?"
            r"(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*(?::\s*[A-Za-z0-9_<>\[\]|&\s]+)?\s*\{"
        )

    @staticmethod
    def _unpack_fn_match(
        match: re.Match[str], line: str
    ) -> tuple[str, str, str]:
        vis_raw = match.group(1)
        fname = match.group(2)
        vis = (vis_raw or "public").upper()
        sig = line.strip().rstrip("{").strip()
        return vis, fname, sig

    @staticmethod
    def _find_block_end(lines: list[str], start_line: int) -> int:
        depth = 0
        opened = False
        for i in range(start_line - 1, len(lines)):
            for ch in lines[i]:
                if ch == "{":
                    depth += 1
                    opened = True
                elif ch == "}":
                    depth -= 1
                    if opened and depth <= 0:
                        return i + 1
        return min(start_line + 1, len(lines))

    @staticmethod
    def _extract_leading_comment(lines: list[str], start_line: int) -> str | None:
        collected: list[str] = []
        idx = start_line - 2
        while idx >= 0:
            s = lines[idx].strip()
            if s.startswith(("//", "*", "/*", "/**")) or s.endswith("*/"):
                cleaned = s.lstrip("/* ").rstrip("*/ ").strip()
                if cleaned:
                    collected.append(cleaned)
                idx -= 1
            else:
                break
        if not collected:
            return None
        collected.reverse()
        return "\n".join(collected)

    @staticmethod
    def _estimate_block_complexity(block_text: str) -> int:
        tokens = re.findall(r"\b(if|else\s+if|for|foreach|while|case|catch|\&\&|\|\|)\b", block_text)
        return 1 + len(tokens)

    @staticmethod
    def _extract_block_calls(
        lines: list[str],
        start_line: int,
        end_line: int,
        own_name: str,
        references: list[ExtractedReference],
    ) -> list[tuple[str, int, bool]]:
        call_re = re.compile(r"(?:([A-Za-z0-9_$]+)(?:\.|->))?([A-Za-z_][A-Za-z0-9_]*)\s*\(")
        keywords = {
            "if",
            "for",
            "foreach",
            "while",
            "switch",
            "catch",
            "return",
            "function",
            "new",
            "super",
            own_name,
        }
        calls: list[tuple[str, int, bool]] = []
        for line_no in range(start_line + 1, end_line + 1):
            text_line = lines[line_no - 1]
            for m in call_re.finditer(text_line):
                receiver, callee = m.group(1), m.group(2)
                if callee in keywords:
                    continue
                is_dyn = bool(receiver and receiver not in ("this", "$this", "self", "static"))
                calls.append((callee, line_no, is_dyn))
                references.append(
                    ExtractedReference(
                        target_symbol_name=callee,
                        reference_kind="CALL",
                        line_number=line_no,
                        col_number=m.start(2),
                    )
                )
        return calls


class ParserRegistry:
    """Central registry mapping supported source languages to deterministic AST/structural parsers."""

    def __init__(self) -> None:
        self._python_parser = PythonAstParser()
        self._structural_parsers = {
            lang: BraceStructuralParser(lang)
            for lang in ("java", "javascript", "typescript", "php")
        }

    def supports_language(self, language: str | None) -> bool:
        return bool(language and language in SUPPORTED_CODE_LANGUAGES)

    def parse_file(self, relative_path: str, language: str, source_text: str) -> FileParseResult:
        if language == "python":
            return self._python_parser.parse(relative_path, source_text)
        if language in self._structural_parsers:
            return self._structural_parsers[language].parse(relative_path, source_text)
        raise ValueError(f"Unsupported source language for structural parsing: {language!r}")


default_parser_registry = ParserRegistry()
