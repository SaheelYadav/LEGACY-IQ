"""Wave 2.1 — Deterministic Database Intelligence Extractor (SQL DDL, Views, Procedures, Triggers, ORM & Code-to-DB Dependency Mapping)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

PII_COLUMN_KEYWORDS: frozenset[str] = frozenset(
    {
        "email",
        "ssn",
        "social_security",
        "tax_id",
        "password",
        "password_hash",
        "passwd",
        "phone",
        "mobile",
        "credit_card",
        "card_number",
        "cvv",
        "iban",
        "routing_number",
        "dob",
        "date_of_birth",
        "birth_date",
        "passport",
        "driver_license",
        "national_id",
        "address",
        "street_address",
        "secret",
        "api_key",
        "access_token",
    }
)


def is_pii_column_candidate(column_name: str) -> bool:
    """Heuristically flag sensitive/PII column identifiers."""
    lower = column_name.lower().strip("\"'`[]")
    if lower in PII_COLUMN_KEYWORDS:
        return True
    return any(
        kw in lower
        for kw in (
            "email",
            "ssn",
            "password",
            "credit_card",
            "tax_id",
            "passport",
            "phone",
            "birth_date",
            "iban",
        )
    )


def _clean_ident(raw: str) -> str:
    return raw.strip().strip("\"'`[]")


def _split_schema_and_name(raw_ident: str, default_schema: str = "public") -> tuple[str, str]:
    cleaned = raw_ident.strip()
    if "." in cleaned:
        parts = [ _clean_ident(p) for p in cleaned.split(".", 1) ]
        return (parts[0] or default_schema, parts[1])
    return default_schema, _clean_ident(cleaned)


@dataclass
class ExtractedDbColumn:
    column_name: str
    ordinal_position: int
    data_type: str
    is_nullable: bool
    is_primary_key: bool
    is_pii_candidate: bool
    line_number: int = 1


@dataclass
class ExtractedDbForeignKey:
    source_schema: str
    source_table: str
    target_schema: str
    target_table: str
    constraint_name: str | None
    source_columns: list[str]
    target_columns: list[str]
    relation_origin: str  # EXPLICIT_DDL | ORM_RELATION | INFERRED_SQL_JOIN
    start_line: int = 1
    end_line: int = 1
    snippet: str = ""


@dataclass
class ExtractedDbProgrammableObject:
    object_kind: str  # STORED_PROCEDURE | FUNCTION | TRIGGER | INDEX
    schema_name: str
    object_name: str
    target_table: str | None
    definition_summary: str
    start_line: int
    end_line: int


@dataclass
class ExtractedDbTable:
    schema_name: str
    table_name: str
    table_kind: str  # TABLE | VIEW | MATERIALIZED_VIEW | COLLECTION
    discovery_source: str  # SQL_DDL | ORM_MODEL | MIGRATION_FILE
    db_engine: str  # POSTGRESQL | MYSQL | ORACLE | MSSQL | SQLITE
    comment_text: str | None = None
    mapped_orm_qualified_name: str | None = None
    columns: list[ExtractedDbColumn] = field(default_factory=list)
    indexes: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    programmable_objects: list[ExtractedDbProgrammableObject] = field(default_factory=list)
    start_line: int = 1
    end_line: int = 1
    snippet: str = ""


@dataclass
class ExtractedDbAccessEdge:
    """Maps a source file / symbol to a database table (`READS_TABLE`, `WRITES_TABLE`, `MAPS_TO_TABLE`)."""

    table_name: str
    relationship_type: str  # READS_TABLE | WRITES_TABLE | MAPS_TO_TABLE
    symbol_qualified_name: str | None
    start_line: int
    end_line: int
    snippet: str


@dataclass
class DatabaseExtractionResult:
    tables: list[ExtractedDbTable] = field(default_factory=list)
    foreign_keys: list[ExtractedDbForeignKey] = field(default_factory=list)
    programmable_objects: list[ExtractedDbProgrammableObject] = field(default_factory=list)
    access_edges: list[ExtractedDbAccessEdge] = field(default_factory=list)


_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+(?:GLOBAL\s+TEMPORARY\s+|TEMP\s+|TEMPORARY\s+|UNLOGGED\s+)?TABLE\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_.\"`\[\]]+)\s*\((.*?)\)\s*(?:WITH\s*\([^)]*\)|TABLESPACE\s+\S+|ENGINE\s*=\s*\S+)*\s*;",
    re.IGNORECASE | re.DOTALL,
)

_CREATE_VIEW_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(MATERIALIZED\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"([A-Za-z0-9_.\"`\[\]]+)\s+AS\s+(.*?);",
    re.IGNORECASE | re.DOTALL,
)

_CREATE_INDEX_RE = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?"
    r"([A-Za-z0-9_\"`\[\]]+)\s+ON\s+(?:ONLY\s+)?([A-Za-z0-9_.\"`\[\]]+)\s*(?:USING\s+\w+\s*)?\(([^)]+)\)",
    re.IGNORECASE,
)

_CREATE_PROC_OR_FUNC_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(PROCEDURE|FUNCTION)\s+([A-Za-z0-9_.\"`\[\]]+)\s*\(([^)]*)\)",
    re.IGNORECASE,
)

_CREATE_TRIGGER_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:CONSTRAINT\s+)?TRIGGER\s+([A-Za-z0-9_\"`\[\]]+)\s+"
    r"(?:BEFORE|AFTER|INSTEAD\s+OF)\s+[^;]+?\s+ON\s+([A-Za-z0-9_.\"`\[\]]+)",
    re.IGNORECASE | re.DOTALL,
)

_ALTER_TABLE_FK_RE = re.compile(
    r"ALTER\s+TABLE\s+(?:ONLY\s+)?([A-Za-z0-9_.\"`\[\]]+)\s+"
    r"ADD\s+(?:CONSTRAINT\s+([A-Za-z0-9_\"`\[\]]+)\s+)?"
    r"FOREIGN\s+KEY\s*\(([^)]+)\)\s*REFERENCES\s+([A-Za-z0-9_.\"`\[\]]+)\s*\(([^)]+)\)",
    re.IGNORECASE | re.DOTALL,
)

_TABLE_COMMENT_RE = re.compile(
    r"COMMENT\s+ON\s+TABLE\s+([A-Za-z0-9_.\"`\[\]]+)\s+IS\s+'([^']*)'",
    re.IGNORECASE,
)


def _detect_sql_engine(sql_text: str) -> str:
    upper = sql_text.upper()
    if "SERIAL" in upper or "JSONB" in upper or "TIMESTAMPTZ" in upper or "PLPGSQL" in upper:
        return "POSTGRESQL"
    if "AUTO_INCREMENT" in upper or "ENGINE=INNODB" in upper:
        return "MYSQL"
    if "NVARCHAR2" in upper or "VARCHAR2" in upper or "SYSDATE" in upper:
        return "ORACLE"
    if "IDENTITY(" in upper or "[DBO]." in upper:
        return "MSSQL"
    return "POSTGRESQL"


def _split_top_level_commas(body: str) -> list[tuple[str, int]]:
    """Split a CREATE TABLE parenthesized body by top-level commas, tracking relative line offsets."""
    items: list[tuple[str, int]] = []
    depth = 0
    current: list[str] = []
    line_offset = 0
    item_start_offset = 0
    in_quote = False
    for ch in body:
        if ch == "'":
            in_quote = not in_quote
        elif not in_quote:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            elif ch == "," and depth == 0:
                stmt = "".join(current).strip()
                if stmt:
                    items.append((stmt, item_start_offset))
                current = []
                item_start_offset = line_offset
                continue
        if ch == "\n":
            line_offset += 1
        current.append(ch)
    tail = "".join(current).strip()
    if tail:
        items.append((tail, item_start_offset))
    return items


def parse_sql_ddl(sql_text: str, relative_path: str = "") -> DatabaseExtractionResult:
    """Deterministically parse SQL DDL script into schemas, tables, views, columns, FKs, indexes, procedures, and triggers."""
    result = DatabaseExtractionResult()
    db_engine = _detect_sql_engine(sql_text)
    lower_path = relative_path.lower()
    discovery_source = (
        "MIGRATION_FILE"
        if ("migration" in lower_path or "alembic" in lower_path or "flyway" in lower_path)
        else "SQL_DDL"
    )

    table_comments: dict[tuple[str, str], str] = {}
    for cm in _TABLE_COMMENT_RE.finditer(sql_text):
        sch, tbl = _split_schema_and_name(cm.group(1))
        table_comments[(sch.lower(), tbl.lower())] = cm.group(2).strip()

    table_lookup: dict[tuple[str, str], ExtractedDbTable] = {}

    # 1. Parse CREATE TABLE blocks
    for match in _CREATE_TABLE_RE.finditer(sql_text):
        raw_table_name = match.group(1)
        body = match.group(2)
        schema_name, table_name = _split_schema_and_name(raw_table_name)
        start_line = sql_text.count("\n", 0, match.start()) + 1
        end_line = sql_text.count("\n", 0, match.end()) + 1
        snippet = match.group(0)[:1800]

        columns: list[ExtractedDbColumn] = []
        constraints: list[str] = []
        pk_columns: set[str] = set()

        clauses = _split_top_level_commas(body)
        ordinal = 0
        for clause_raw, rel_offset in clauses:
            # Strip leading SQL line comments inside the clause
            cleaned_lines = [
                ln for ln in clause_raw.splitlines() if not ln.strip().startswith("--")
            ]
            clause = " ".join(cleaned_lines).strip()
            if not clause:
                continue
            upper_clause = clause.upper()
            clause_line = start_line + rel_offset

            # Table-level PRIMARY KEY (...)
            pk_match = re.match(
                r"^(?:CONSTRAINT\s+([A-Za-z0-9_\"`\[\]]+)\s+)?PRIMARY\s+KEY\s*\(([^)]+)\)",
                clause,
                re.IGNORECASE,
            )
            if pk_match:
                cols = [_clean_ident(c) for c in pk_match.group(2).split(",") if c.strip()]
                pk_columns.update(c.lower() for c in cols)
                constraints.append(clause)
                continue

            # Table-level FOREIGN KEY (...) REFERENCES ...
            fk_match = re.match(
                r"^(?:CONSTRAINT\s+([A-Za-z0-9_\"`\[\]]+)\s+)?FOREIGN\s+KEY\s*\(([^)]+)\)\s*"
                r"REFERENCES\s+([A-Za-z0-9_.\"`\[\]]+)\s*\(([^)]+)\)",
                clause,
                re.IGNORECASE,
            )
            if fk_match:
                cname = _clean_ident(fk_match.group(1)) if fk_match.group(1) else None
                src_cols = [_clean_ident(c) for c in fk_match.group(2).split(",") if c.strip()]
                tgt_schema, tgt_table = _split_schema_and_name(fk_match.group(3), schema_name)
                tgt_cols = [_clean_ident(c) for c in fk_match.group(4).split(",") if c.strip()]
                result.foreign_keys.append(
                    ExtractedDbForeignKey(
                        source_schema=schema_name,
                        source_table=table_name,
                        target_schema=tgt_schema,
                        target_table=tgt_table,
                        constraint_name=cname,
                        source_columns=src_cols,
                        target_columns=tgt_cols,
                        relation_origin="EXPLICIT_DDL",
                        start_line=clause_line,
                        end_line=clause_line,
                        snippet=clause[:500],
                    )
                )
                constraints.append(clause)
                continue

            if upper_clause.startswith(("CONSTRAINT ", "UNIQUE ", "CHECK ", "KEY ", "INDEX ")):
                constraints.append(clause)
                continue

            # Column definition: <col_name> <data_type> [constraints...]
            col_match = re.match(
                r"^([A-Za-z0-9_\"`\[\]]+)\s+([A-Za-z0-9_]+(?:\s*\([^)]*\))?(?:\s+WITH\s+TIME\s+ZONE|\s+WITHOUT\s+TIME\s+ZONE|\s+UNSIGNED|\s+VARYING)?)(.*)$",
                clause,
                re.IGNORECASE,
            )
            if not col_match:
                continue

            col_name = _clean_ident(col_match.group(1))
            data_type = col_match.group(2).strip().upper()
            modifiers = col_match.group(3) or ""
            upper_mods = modifiers.upper()

            ordinal += 1
            is_pk = "PRIMARY KEY" in upper_mods or col_name.lower() in pk_columns
            is_nullable = not ("NOT NULL" in upper_mods or is_pk)

            # Inline REFERENCES target_table(target_col)
            inline_ref = re.search(
                r"REFERENCES\s+([A-Za-z0-9_.\"`\[\]]+)\s*(?:\(([^)]+)\))?",
                modifiers,
                re.IGNORECASE,
            )
            if inline_ref:
                tgt_schema, tgt_table = _split_schema_and_name(inline_ref.group(1), schema_name)
                tgt_cols = (
                    [_clean_ident(c) for c in inline_ref.group(2).split(",") if c.strip()]
                    if inline_ref.group(2)
                    else ["id"]
                )
                result.foreign_keys.append(
                    ExtractedDbForeignKey(
                        source_schema=schema_name,
                        source_table=table_name,
                        target_schema=tgt_schema,
                        target_table=tgt_table,
                        constraint_name=f"fk_{table_name}_{col_name}",
                        source_columns=[col_name],
                        target_columns=tgt_cols,
                        relation_origin="EXPLICIT_DDL",
                        start_line=clause_line,
                        end_line=clause_line,
                        snippet=clause[:500],
                    )
                )

            columns.append(
                ExtractedDbColumn(
                    column_name=col_name,
                    ordinal_position=ordinal,
                    data_type=data_type[:128],
                    is_nullable=is_nullable,
                    is_primary_key=is_pk,
                    is_pii_candidate=is_pii_column_candidate(col_name),
                    line_number=clause_line,
                )
            )

        # Backfill table-level PK flags onto columns
        for col in columns:
            if col.column_name.lower() in pk_columns:
                col.is_primary_key = True
                col.is_nullable = False

        comment = table_comments.get((schema_name.lower(), table_name.lower()))
        tbl_obj = ExtractedDbTable(
            schema_name=schema_name,
            table_name=table_name,
            table_kind="TABLE",
            discovery_source=discovery_source,
            db_engine=db_engine,
            comment_text=comment,
            columns=columns,
            constraints=constraints,
            start_line=start_line,
            end_line=end_line,
            snippet=snippet,
        )
        result.tables.append(tbl_obj)
        table_lookup[(schema_name.lower(), table_name.lower())] = tbl_obj

    # 2. Parse CREATE [MATERIALIZED] VIEW blocks
    for vmatch in _CREATE_VIEW_RE.finditer(sql_text):
        is_mat = bool(vmatch.group(1))
        schema_name, view_name = _split_schema_and_name(vmatch.group(2))
        query_body = vmatch.group(3).strip()
        start_line = sql_text.count("\n", 0, vmatch.start()) + 1
        end_line = sql_text.count("\n", 0, vmatch.end()) + 1

        # Infer projected columns from SELECT list if simple
        cols: list[ExtractedDbColumn] = []
        sel_match = re.search(r"SELECT\s+(.*?)\s+FROM\s+", query_body, re.IGNORECASE | re.DOTALL)
        if sel_match:
            raw_proj = sel_match.group(1)
            for idx, expr in enumerate(_split_top_level_commas(raw_proj), start=1):
                expr_text = expr[0].strip()
                as_match = re.search(r"\bAS\s+([A-Za-z0-9_\"`]+)$", expr_text, re.IGNORECASE)
                if as_match:
                    cname = _clean_ident(as_match.group(1))
                else:
                    cname = _clean_ident(expr_text.split(".")[-1].split()[-1])
                if cname and cname != "*":
                    cols.append(
                        ExtractedDbColumn(
                            column_name=cname[:255],
                            ordinal_position=idx,
                            data_type="VIEW_COLUMN",
                            is_nullable=True,
                            is_primary_key=False,
                            is_pii_candidate=is_pii_column_candidate(cname),
                            line_number=start_line,
                        )
                    )

        view_obj = ExtractedDbTable(
            schema_name=schema_name,
            table_name=view_name,
            table_kind="MATERIALIZED_VIEW" if is_mat else "VIEW",
            discovery_source=discovery_source,
            db_engine=db_engine,
            comment_text=f"SQL View query: {query_body[:300]}",
            columns=cols,
            start_line=start_line,
            end_line=end_line,
            snippet=vmatch.group(0)[:1800],
        )
        result.tables.append(view_obj)
        table_lookup[(schema_name.lower(), view_name.lower())] = view_obj

    # 3. Parse ALTER TABLE ... ADD FOREIGN KEY
    for fk_alt in _ALTER_TABLE_FK_RE.finditer(sql_text):
        src_schema, src_table = _split_schema_and_name(fk_alt.group(1))
        cname = _clean_ident(fk_alt.group(2)) if fk_alt.group(2) else None
        src_cols = [_clean_ident(c) for c in fk_alt.group(3).split(",") if c.strip()]
        tgt_schema, tgt_table = _split_schema_and_name(fk_alt.group(4), src_schema)
        tgt_cols = [_clean_ident(c) for c in fk_alt.group(5).split(",") if c.strip()]
        start_line = sql_text.count("\n", 0, fk_alt.start()) + 1
        end_line = sql_text.count("\n", 0, fk_alt.end()) + 1
        result.foreign_keys.append(
            ExtractedDbForeignKey(
                source_schema=src_schema,
                source_table=src_table,
                target_schema=tgt_schema,
                target_table=tgt_table,
                constraint_name=cname,
                source_columns=src_cols,
                target_columns=tgt_cols,
                relation_origin="EXPLICIT_DDL",
                start_line=start_line,
                end_line=end_line,
                snippet=fk_alt.group(0)[:500],
            )
        )

    # 4. Parse CREATE INDEX and attach to table metadata
    for idx_match in _CREATE_INDEX_RE.finditer(sql_text):
        idx_name = _clean_ident(idx_match.group(1))
        sch, tbl_name = _split_schema_and_name(idx_match.group(2))
        idx_cols = idx_match.group(3).strip()
        start_line = sql_text.count("\n", 0, idx_match.start()) + 1
        end_line = sql_text.count("\n", 0, idx_match.end()) + 1
        tbl_obj = table_lookup.get((sch.lower(), tbl_name.lower()))
        if tbl_obj:
            tbl_obj.indexes.append(f"{idx_name}({idx_cols})")
            if not tbl_obj.comment_text:
                tbl_obj.comment_text = f"Indexes: {idx_name}({idx_cols})"
            elif "Indexes:" not in tbl_obj.comment_text:
                tbl_obj.comment_text += f" | Indexes: {idx_name}({idx_cols})"
        result.programmable_objects.append(
            ExtractedDbProgrammableObject(
                object_kind="INDEX",
                schema_name=sch,
                object_name=idx_name,
                target_table=tbl_name,
                definition_summary=f"INDEX {idx_name} ON {tbl_name}({idx_cols})",
                start_line=start_line,
                end_line=end_line,
            )
        )

    # 5. Parse Stored Procedures & Functions
    for pmatch in _CREATE_PROC_OR_FUNC_RE.finditer(sql_text):
        kind = "STORED_PROCEDURE" if pmatch.group(1).upper() == "PROCEDURE" else "FUNCTION"
        sch, pname = _split_schema_and_name(pmatch.group(2))
        args = pmatch.group(3).strip()
        start_line = sql_text.count("\n", 0, pmatch.start()) + 1
        end_line = sql_text.count("\n", 0, pmatch.end()) + 1
        result.programmable_objects.append(
            ExtractedDbProgrammableObject(
                object_kind=kind,
                schema_name=sch,
                object_name=pname,
                target_table=None,
                definition_summary=f"{kind} {sch}.{pname}({args})",
                start_line=start_line,
                end_line=end_line,
            )
        )

    # 6. Parse Triggers
    for tmatch in _CREATE_TRIGGER_RE.finditer(sql_text):
        trig_name = _clean_ident(tmatch.group(1))
        sch, tbl_name = _split_schema_and_name(tmatch.group(2))
        start_line = sql_text.count("\n", 0, tmatch.start()) + 1
        end_line = sql_text.count("\n", 0, tmatch.end()) + 1
        prog = ExtractedDbProgrammableObject(
            object_kind="TRIGGER",
            schema_name=sch,
            object_name=trig_name,
            target_table=tbl_name,
            definition_summary=f"TRIGGER {trig_name} ON {sch}.{tbl_name}",
            start_line=start_line,
            end_line=end_line,
        )
        result.programmable_objects.append(prog)
        tbl_obj = table_lookup.get((sch.lower(), tbl_name.lower()))
        if tbl_obj:
            tbl_obj.programmable_objects.append(prog)
            note = f"Trigger: {trig_name}"
            tbl_obj.comment_text = f"{tbl_obj.comment_text} | {note}" if tbl_obj.comment_text else note

    return result


def extract_orm_and_sql_from_code(
    source_text: str,
    language: str,
    module_name: str,
    known_table_names: set[str] | None = None,
) -> DatabaseExtractionResult:
    """
    Extract ORM-mapped tables/columns/FKs and embedded SQL READS_TABLE / WRITES_TABLE edges
    from Python (SQLAlchemy/Django), Java (JPA/Hibernate/JDBC), JS/TS (Prisma/TypeORM/Knex), and PHP (Eloquent/PDO).
    """
    result = DatabaseExtractionResult()
    lines = source_text.splitlines()

    # 1. Python SQLAlchemy / Django ORM detection
    if language == "python":
        class_pattern = re.compile(r"^(\s*)class\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(([^)]*)\))?:")
        tablename_pattern = re.compile(r"__tablename__\s*(?::\s*[^=]+)?=\s*['\"]([A-Za-z0-9_]+)['\"]")
        django_db_table_pattern = re.compile(r"db_table\s*=\s*['\"]([A-Za-z0-9_]+)['\"]")
        col_pattern = re.compile(
            r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*Mapped\[([^\]]+)\])?\s*=\s*(?:mapped_column|Column|models\.(\w+Field))\s*\((.*)\)"
        )
        fk_call_pattern = re.compile(r"ForeignKey\s*\(\s*['\"]([A-Za-z0-9_.]+)['\"]")

        i = 0
        while i < len(lines):
            cm = class_pattern.match(lines[i])
            if not cm:
                i += 1
                continue
            indent = len(cm.group(1))
            cls_name = cm.group(2)
            start_line = i + 1
            j = i + 1
            while j < len(lines):
                stripped = lines[j].strip()
                if stripped and not stripped.startswith("#"):
                    cur_indent = len(lines[j]) - len(lines[j].lstrip())
                    if cur_indent <= indent:
                        break
                j += 1
            end_line = j
            class_body = "\n".join(lines[i:j])

            tbl_match = tablename_pattern.search(class_body) or django_db_table_pattern.search(class_body)
            if tbl_match:
                table_name = tbl_match.group(1)
                qname = f"{module_name}.{cls_name}"
                cols: list[ExtractedDbColumn] = []
                ordinal = 0
                for offset, raw_line in enumerate(lines[i:j]):
                    colm = col_pattern.match(raw_line)
                    if not colm:
                        continue
                    cname = colm.group(1)
                    mapped_type = colm.group(2) or colm.group(3) or "VARCHAR"
                    args_str = colm.group(4) or ""
                    ordinal += 1
                    is_pk = "primary_key=True" in args_str
                    is_nullable = "nullable=False" not in args_str and not is_pk
                    cols.append(
                        ExtractedDbColumn(
                            column_name=cname,
                            ordinal_position=ordinal,
                            data_type=mapped_type.strip()[:128],
                            is_nullable=is_nullable,
                            is_primary_key=is_pk,
                            is_pii_candidate=is_pii_column_candidate(cname),
                            line_number=start_line + offset,
                        )
                    )
                    fk_m = fk_call_pattern.search(args_str)
                    if fk_m:
                        ref_parts = fk_m.group(1).split(".")
                        if len(ref_parts) >= 2:
                            tgt_table = ref_parts[-2]
                            tgt_col = ref_parts[-1]
                            result.foreign_keys.append(
                                ExtractedDbForeignKey(
                                    source_schema="public",
                                    source_table=table_name,
                                    target_schema="public",
                                    target_table=tgt_table,
                                    constraint_name=f"fk_orm_{table_name}_{cname}",
                                    source_columns=[cname],
                                    target_columns=[tgt_col],
                                    relation_origin="ORM_RELATION",
                                    start_line=start_line + offset,
                                    end_line=start_line + offset,
                                    snippet=raw_line.strip()[:400],
                                )
                            )

                result.tables.append(
                    ExtractedDbTable(
                        schema_name="public",
                        table_name=table_name,
                        table_kind="TABLE",
                        discovery_source="ORM_MODEL",
                        db_engine="POSTGRESQL",
                        comment_text=f"ORM Model Class `{qname}`",
                        mapped_orm_qualified_name=qname,
                        columns=cols,
                        start_line=start_line,
                        end_line=end_line,
                        snippet=class_body[:1500],
                    )
                )
                result.access_edges.append(
                    ExtractedDbAccessEdge(
                        table_name=table_name,
                        relationship_type="MAPS_TO_TABLE",
                        symbol_qualified_name=qname,
                        start_line=start_line,
                        end_line=end_line,
                        snippet=lines[i].strip(),
                    )
                )
            i = j

    # 2. Java JPA `@Table(name = "...")` / `@Entity` detection
    elif language == "java":
        jpa_table_re = re.compile(
            r"@Table\s*\(\s*(?:[^)]*?\bname\s*=\s*)?\"([A-Za-z0-9_]+)\"[^)]*\)\s*"
            r"(?:@\w+(?:\([^)]*\))?\s*)*"
            r"(?:public\s+|protected\s+|final\s+|abstract\s+)*class\s+([A-Za-z_][A-Za-z0-9_]*)",
            re.DOTALL,
        )
        for m in jpa_table_re.finditer(source_text):
            tname = m.group(1)
            cname = m.group(2)
            qname = f"{module_name}.{cname}"
            sline = source_text.count("\n", 0, m.start()) + 1
            eline = source_text.count("\n", 0, m.end()) + 1
            result.tables.append(
                ExtractedDbTable(
                    schema_name="public",
                    table_name=tname,
                    table_kind="TABLE",
                    discovery_source="ORM_MODEL",
                    db_engine="POSTGRESQL",
                    comment_text=f"JPA Entity `{qname}`",
                    mapped_orm_qualified_name=qname,
                    start_line=sline,
                    end_line=eline,
                    snippet=m.group(0)[:500],
                )
            )
            result.access_edges.append(
                ExtractedDbAccessEdge(
                    table_name=tname,
                    relationship_type="MAPS_TO_TABLE",
                    symbol_qualified_name=qname,
                    start_line=sline,
                    end_line=eline,
                    snippet=m.group(0)[:400],
                )
            )

    # 3. PHP Laravel Eloquent `protected $table = '...'`
    elif language == "php":
        php_table_re = re.compile(
            r"class\s+([A-Za-z_][A-Za-z0-9_]*)\s+extends\s+[A-Za-z0-9_\\]+.*?protected\s+\$table\s*=\s*['\"]([A-Za-z0-9_]+)['\"]",
            re.DOTALL,
        )
        for m in php_table_re.finditer(source_text):
            cname = m.group(1)
            tname = m.group(2)
            qname = f"{module_name}.{cname}"
            sline = source_text.count("\n", 0, m.start()) + 1
            eline = source_text.count("\n", 0, m.end()) + 1
            result.tables.append(
                ExtractedDbTable(
                    schema_name="public",
                    table_name=tname,
                    table_kind="TABLE",
                    discovery_source="ORM_MODEL",
                    db_engine="MYSQL",
                    comment_text=f"Eloquent Model `{qname}`",
                    mapped_orm_qualified_name=qname,
                    start_line=sline,
                    end_line=eline,
                    snippet=m.group(0)[:500],
                )
            )
            result.access_edges.append(
                ExtractedDbAccessEdge(
                    table_name=tname,
                    relationship_type="MAPS_TO_TABLE",
                    symbol_qualified_name=qname,
                    start_line=sline,
                    end_line=eline,
                    snippet=m.group(0)[:400],
                )
            )

    # 4. Scan embedded SQL statements (SELECT ... FROM / JOIN -> READS_TABLE, INSERT/UPDATE/DELETE -> WRITES_TABLE)
    read_sql_re = re.compile(
        r"\b(?:SELECT\b[\s\S]{1,240}?\bFROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)\b",
        re.IGNORECASE,
    )
    write_sql_re = re.compile(
        r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([A-Za-z_][A-Za-z0-9_]*)\b",
        re.IGNORECASE,
    )
    sql_noise = {
        "select",
        "where",
        "values",
        "set",
        "dual",
        "unnest",
        "lateral",
        "jsonb_each",
        "information_schema",
        "pg_catalog",
    }

    for rm in read_sql_re.finditer(source_text):
        candidate = rm.group(1)
        if candidate.lower() in sql_noise:
            continue
        if known_table_names and candidate.lower() not in known_table_names:
            continue
        sline = source_text.count("\n", 0, rm.start()) + 1
        eline = source_text.count("\n", 0, rm.end()) + 1
        result.access_edges.append(
            ExtractedDbAccessEdge(
                table_name=candidate,
                relationship_type="READS_TABLE",
                symbol_qualified_name=None,
                start_line=sline,
                end_line=eline,
                snippet=rm.group(0)[:300],
            )
        )

    for wm in write_sql_re.finditer(source_text):
        candidate = wm.group(1)
        if candidate.lower() in sql_noise:
            continue
        if known_table_names and candidate.lower() not in known_table_names:
            continue
        sline = source_text.count("\n", 0, wm.start()) + 1
        eline = source_text.count("\n", 0, wm.end()) + 1
        result.access_edges.append(
            ExtractedDbAccessEdge(
                table_name=candidate,
                relationship_type="WRITES_TABLE",
                symbol_qualified_name=None,
                start_line=sline,
                end_line=eline,
                snippet=wm.group(0)[:300],
            )
        )

    return result

