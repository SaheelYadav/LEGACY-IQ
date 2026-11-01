"""Wave 5 Multi-Format Report Export Generators: Standards-Compliant PDF, DOCX, XLSX, and JSON without Paid External APIs."""

from __future__ import annotations

import io
import json
from typing import Any
from xml.sax.saxutils import escape as xml_escape
import zipfile
import zlib


def render_report_export(
    export_format: str,
    report_payload: dict[str, Any],
) -> tuple[bytes, str, str]:
    """
    Render `report_payload` into `(binary_bytes, mime_type, file_extension)`.
    Supported formats: `PDF`, `DOCX`, `XLSX`, `JSON`.
    """
    fmt = export_format.upper().strip()
    if fmt == "JSON":
        data = render_report_json(report_payload)
        return data, "application/json", "json"
    if fmt == "PDF":
        data = render_report_pdf(report_payload)
        return data, "application/pdf", "pdf"
    if fmt == "DOCX":
        data = render_report_docx(report_payload)
        return (
            data,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx",
        )
    if fmt == "XLSX":
        data = render_report_xlsx(report_payload)
        return (
            data,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xlsx",
        )
    raise ValueError(f"Unsupported export format: {export_format}")


def render_report_json(report_payload: dict[str, Any]) -> bytes:
    """Serialize structured report payload with branding, citations, and version metadata to UTF-8 JSON."""
    return json.dumps(report_payload, indent=2, sort_keys=False).encode("utf-8")


def _pdf_escape(text: str) -> str:
    clean = (
        text.encode("ascii", errors="replace")
        .decode("ascii")
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )
    return clean


def render_report_pdf(report_payload: dict[str, Any]) -> bytes:
    """
    Generate a standards-compliant `%PDF-1.4` document with Organization/Project branding,
    report metadata, sections, evidence references, and recommendations.
    Compatible with PDF readers and LegacyIQ's `extract_documentation(..., 'pdf')` parser.
    """
    branding = report_payload.get("branding", {})
    org_name = branding.get("organization_name", "LegacyIQ Enterprise")
    project_name = branding.get("project_name", "Core Modernization")
    title = report_payload.get("title", "Application Intelligence Report")
    report_type = report_payload.get("report_type", "COMPLETE_INTELLIGENCE")
    version_no = report_payload.get("version_no", 1)
    status = report_payload.get("lifecycle_status", "GENERATED")
    generated_at = report_payload.get("generated_at", "")
    exec_summary = report_payload.get("executive_summary_markdown", "")
    scope_method = report_payload.get("scope_and_methodology_markdown", "")
    risks_limits = report_payload.get("risks_and_limitations_markdown", "")
    sections = report_payload.get("sections", [])
    evidence_refs = report_payload.get("evidence_references", [])
    recommendations = report_payload.get("recommendations", [])

    lines: list[str] = [
        f"{org_name} | Project: {project_name}",
        f"Report: {title} ({report_type})",
        f"Version: v{version_no} | Status: {status} | Generated: {generated_at}",
        "Governance Notice: Unreviewed AI/static inferences are marked PENDING_REVIEW and are NOT presented as approved facts.",
        "-" * 85,
        "1. EXECUTIVE SUMMARY",
    ]
    for ln in exec_summary.splitlines():
        if ln.strip():
            lines.append(ln.strip()[:100])
    lines.append("2. SCOPE & METHODOLOGY")
    for ln in scope_method.splitlines():
        if ln.strip():
            lines.append(ln.strip()[:100])

    lines.append("3. FINDINGS & ANALYSIS")
    for sec in sections:
        sec_title = str(sec.get("title", "Section"))
        sec_basis = str(sec.get("metric_basis", "MEASURED"))
        lines.append(f"[{sec_basis}] {sec_title}")
        body = str(sec.get("content_markdown", ""))
        for ln in body.splitlines():
            if ln.strip():
                lines.append(f"  {ln.strip()[:96]}")

    lines.append("4. EVIDENCE REFERENCES")
    for ev in evidence_refs[:25]:
        path = ev.get("relative_path", "artifact")
        s_ln = ev.get("start_line", 1)
        e_ln = ev.get("end_line", 1)
        sha = str(ev.get("snippet_sha256", ""))[:16]
        lines.append(f"  Cite: {path}:{s_ln}-{e_ln} (sha256:{sha}...)")

    lines.append("5. RISKS & LIMITATIONS")
    for ln in risks_limits.splitlines():
        if ln.strip():
            lines.append(f"  {ln.strip()[:96]}")

    lines.append("6. RECOMMENDATIONS")
    for rec in recommendations[:15]:
        r_title = rec.get("title", "Recommendation")
        r_phase = rec.get("roadmap_phase", 1)
        r_eff = rec.get("effort_tshirt", "M")
        r_stat = rec.get("review_status", "PENDING_REVIEW")
        lines.append(f"  Phase {r_phase} [{r_eff} Estimate | {r_stat}]: {r_title[:80]}")

    # Build PDF stream commands
    stream_cmds: list[str] = ["BT", "/F1 10 Tf", "50 760 Td", "12 TL"]
    for idx, line in enumerate(lines[:60]):
        esc = _pdf_escape(line)
        if idx == 0:
            stream_cmds.append(f"({esc}) Tj")
        else:
            stream_cmds.append(f"T* ({esc}) Tj")
    stream_cmds.append("ET")
    stream_raw = "\n".join(stream_cmds).encode("ascii", errors="replace")
    compressed = zlib.compress(stream_raw)

    objs: list[bytes] = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        f"5 0 obj\n<< /Length {len(compressed)} /Filter /FlateDecode >>\nstream\n".encode(
            "ascii"
        )
        + compressed
        + b"\nendstream\nendobj\n",
    ]

    buf = io.BytesIO()
    buf.write(b"%PDF-1.4\n")
    offsets: list[int] = []
    for obj in objs:
        offsets.append(buf.tell())
        buf.write(obj)
    xref_pos = buf.tell()
    buf.write(f"xref\n0 {len(objs) + 1}\n".encode("ascii"))
    buf.write(b"0000000000 65535 f \n")
    for off in offsets:
        buf.write(f"{off:010d} 00000 n \n".encode("ascii"))
    buf.write(
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return buf.getvalue()


def render_report_docx(report_payload: dict[str, Any]) -> bytes:
    """
    Generate an ECMA-376 OpenXML `.docx` document containing branding, report metadata,
    executive summary, findings, evidence anchors, and recommendations.
    """
    branding = report_payload.get("branding", {})
    org_name = branding.get("organization_name", "LegacyIQ Enterprise")
    project_name = branding.get("project_name", "Core Modernization")
    title = report_payload.get("title", "Application Intelligence Report")
    report_type = report_payload.get("report_type", "COMPLETE_INTELLIGENCE")
    version_no = report_payload.get("version_no", 1)
    status = report_payload.get("lifecycle_status", "GENERATED")
    generated_at = report_payload.get("generated_at", "")

    paragraphs: list[tuple[str | None, str]] = [
        ("Heading1", f"{title} (v{version_no} — {status})"),
        (
            None,
            f"Organization: {org_name} | Project: {project_name} | Report Type: {report_type} | Generated: {generated_at}",
        ),
        (
            None,
            "Governance Principle: Unreviewed inferences (PENDING_REVIEW) are strictly separated from human-approved facts (APPROVED).",
        ),
        ("Heading1", "Executive Summary"),
        (None, str(report_payload.get("executive_summary_markdown", ""))),
        ("Heading1", "Scope and Methodology"),
        (None, str(report_payload.get("scope_and_methodology_markdown", ""))),
        ("Heading1", "Findings and Intelligence Analysis"),
    ]

    for sec in report_payload.get("sections", []):
        sec_title = str(sec.get("title", "Analysis Section"))
        sec_basis = str(sec.get("metric_basis", "MEASURED"))
        paragraphs.append(("Heading2", f"{sec_title} [{sec_basis}]"))
        paragraphs.append((None, str(sec.get("content_markdown", ""))))

    paragraphs.append(("Heading1", "Evidence References & Provenance"))
    for ev in report_payload.get("evidence_references", [])[:40]:
        cite_str = (
            f"[{ev.get('relative_path', 'source')}:{ev.get('start_line', 1)}-{ev.get('end_line', 1)}] "
            f"sha256={ev.get('snippet_sha256', '')} | {str(ev.get('excerpt_text', ''))[:160]}"
        )
        paragraphs.append((None, cite_str))

    paragraphs.append(("Heading1", "Risks and Limitations"))
    paragraphs.append(
        (None, str(report_payload.get("risks_and_limitations_markdown", "")))
    )

    paragraphs.append(("Heading1", "Recommendations"))
    for rec in report_payload.get("recommendations", []):
        paragraphs.append(
            (
                None,
                f"Phase {rec.get('roadmap_phase', 1)} — {rec.get('title', '')} "
                f"(Effort: {rec.get('effort_tshirt', 'M')} [Estimate], Status: {rec.get('review_status', 'PENDING_REVIEW')})",
            )
        )

    body_xml_parts: list[str] = []
    for style, text in paragraphs:
        for line in str(text).splitlines() or [""]:
            clean_txt = xml_escape(line.strip())
            if not clean_txt:
                continue
            if style:
                body_xml_parts.append(
                    f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr><w:r><w:t>{clean_txt}</w:t></w:r></w:p>'
                )
            else:
                body_xml_parts.append(f"<w:p><w:r><w:t>{clean_txt}</w:t></w:r></w:p>")

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body_xml_parts)}</w:body>"
        "</w:document>"
    )

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )

    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


def render_report_xlsx(report_payload: dict[str, Any]) -> bytes:
    """
    Generate an ECMA-376 OpenXML `.xlsx` multi-worksheet workbook:
    - Sheet 1: `Overview` (Metadata, Branding, Summary Metrics)
    - Sheet 2: `Findings_Analysis` (Sections & Metric Basis)
    - Sheet 3: `Evidence_Citations` (Anchor IDs, Paths, Lines, SHA-256)
    - Sheet 4: `Recommendations` (Phased Modernization & Risk Remediation)
    """
    branding = report_payload.get("branding", {})
    shared_strings: list[str] = []
    str_index: dict[str, int] = {}

    def _s_idx(val: Any) -> int:
        s = str(val if val is not None else "")
        if s not in str_index:
            str_index[s] = len(shared_strings)
            shared_strings.append(s)
        return str_index[s]

    def _build_sheet_xml(rows_data: list[list[Any]]) -> str:
        col_letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        row_xmls: list[str] = []
        for r_idx, row in enumerate(rows_data, start=1):
            cells: list[str] = []
            for c_idx, cell_val in enumerate(row[:20]):
                col = col_letters[c_idx]
                sid = _s_idx(cell_val)
                cells.append(f'<c r="{col}{r_idx}" t="s"><v>{sid}</v></c>')
            row_xmls.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(row_xmls)}</sheetData>'
            "</worksheet>"
        )

    sheet1_rows: list[list[Any]] = [
        ["Field", "Value", "Basis / Governance"],
        ["Organization", branding.get("organization_name", "LegacyIQ Enterprise"), "BRANDING"],
        ["Project", branding.get("project_name", "Core Modernization"), "BRANDING"],
        ["Report Title", report_payload.get("title", ""), "METADATA"],
        ["Report Type", report_payload.get("report_type", ""), "METADATA"],
        ["Version", f"v{report_payload.get('version_no', 1)}", "VERSIONING"],
        ["Lifecycle Status", report_payload.get("lifecycle_status", "GENERATED"), "GOVERNANCE"],
        ["Content SHA-256", report_payload.get("content_sha256", ""), "INTEGRITY"],
        ["Executive Summary", report_payload.get("executive_summary_markdown", ""), "SYNTHESIS"],
    ]

    sheet2_rows: list[list[Any]] = [
        ["Section Key", "Title", "Metric Basis", "Review Posture", "Content"],
    ]
    for sec in report_payload.get("sections", []):
        sheet2_rows.append(
            [
                sec.get("section_key", ""),
                sec.get("title", ""),
                sec.get("metric_basis", "MEASURED"),
                sec.get("review_posture", "MIXED"),
                str(sec.get("content_markdown", ""))[:500],
            ]
        )

    sheet3_rows: list[list[Any]] = [
        ["Anchor ID", "File Path", "Start Line", "End Line", "SHA-256", "Excerpt"],
    ]
    for ev in report_payload.get("evidence_references", []):
        sheet3_rows.append(
            [
                ev.get("anchor_id", ""),
                ev.get("relative_path", ""),
                ev.get("start_line", 1),
                ev.get("end_line", 1),
                ev.get("snippet_sha256", ""),
                str(ev.get("excerpt_text", ""))[:300],
            ]
        )

    sheet4_rows: list[list[Any]] = [
        ["Phase", "Strategy", "Title", "Effort (T-Shirt)", "Effort Basis", "Review Status"],
    ]
    for rec in report_payload.get("recommendations", []):
        sheet4_rows.append(
            [
                rec.get("roadmap_phase", 1),
                rec.get("strategy_pattern", ""),
                rec.get("title", ""),
                rec.get("effort_tshirt", "M"),
                rec.get("effort_nature", "HEURISTIC_ESTIMATE"),
                rec.get("review_status", "PENDING_REVIEW"),
            ]
        )

    s1_xml = _build_sheet_xml(sheet1_rows)
    s2_xml = _build_sheet_xml(sheet2_rows)
    s3_xml = _build_sheet_xml(sheet3_rows)
    s4_xml = _build_sheet_xml(sheet4_rows)

    sst_items = "".join(f"<si><t>{xml_escape(s)}</t></si>" for s in shared_strings)
    shared_strings_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(shared_strings)}" uniqueCount="{len(shared_strings)}">'
        f"{sst_items}</sst>"
    )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        '<sheet name="Overview" sheetId="1" r:id="rId1"/>'
        '<sheet name="Findings_Analysis" sheetId="2" r:id="rId2"/>'
        '<sheet name="Evidence_Citations" sheetId="3" r:id="rId3"/>'
        '<sheet name="Recommendations" sheetId="4" r:id="rId4"/>'
        "</sheets>"
        "</workbook>"
    )

    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet3.xml"/>'
        '<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet4.xml"/>'
        '<Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
        "</Relationships>"
    )

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/worksheets/sheet4.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        "</Types>"
    )

    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", root_rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        zf.writestr("xl/sharedStrings.xml", shared_strings_xml)
        zf.writestr("xl/worksheets/sheet1.xml", s1_xml)
        zf.writestr("xl/worksheets/sheet2.xml", s2_xml)
        zf.writestr("xl/worksheets/sheet3.xml", s3_xml)
        zf.writestr("xl/worksheets/sheet4.xml", s4_xml)
    return buf.getvalue()


__all__ = [
    "render_report_docx",
    "render_report_export",
    "render_report_json",
    "render_report_pdf",
    "render_report_xlsx",
]

