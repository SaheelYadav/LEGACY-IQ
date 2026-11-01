"""Wave 2.4 — Deterministic Documentation Intelligence Extractor (Markdown, HTML, DOCX, XLSX, PDF & Entity Cross-Referencing)."""

from __future__ import annotations

from html.parser import HTMLParser
import io
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
import zlib
from dataclasses import dataclass, field


@dataclass
class ExtractedDocSection:
    heading_path: str
    heading_level: int  # 1..6
    start_line: int
    end_line: int
    content_markdown: str
    parent_index: int | None = None
    mentioned_identifiers: list[str] = field(default_factory=list)


@dataclass
class DocExtractionResult:
    sections: list[ExtractedDocSection] = field(default_factory=list)
    normalized_full_text: str = ""


_BACKTICK_OR_IDENTIFIER_RE = re.compile(
    r"`([A-Za-z0-9_./:\-]{2,120})`|\b([A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+|[a-z][a-z0-9_]{2,}_[a-z0-9_]+|/api/[A-Za-z0-9_/{}-]+)\b"
)


def extract_mentioned_identifiers(text: str) -> list[str]:
    """Extract code/table/API identifiers referenced in a documentation section."""
    found: set[str] = set()
    for m in _BACKTICK_OR_IDENTIFIER_RE.finditer(text):
        token = (m.group(1) or m.group(2) or "").strip()
        if len(token) >= 3:
            found.add(token)
    return sorted(found)[:50]


def parse_markdown_sections(md_text: str, relative_path: str) -> DocExtractionResult:
    """Parse Markdown or text documents into hierarchical `ExtractedDocSection` records."""
    lines = md_text.splitlines()
    if not lines:
        return DocExtractionResult()

    sections: list[ExtractedDocSection] = []
    heading_stack: list[tuple[int, str, int]] = []  # (level, title, section_idx)

    current_title = posixpath.basename(relative_path)
    current_level = 1
    current_start = 1
    current_parent_idx: int | None = None
    current_lines: list[str] = []

    heading_re = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

    def _flush_section(end_line_no: int) -> None:
        body = "\n".join(current_lines).strip()
        if not body and not sections and end_line_no <= 1:
            return
        breadcrumb = (
            " > ".join(h[1] for h in heading_stack)
            if heading_stack
            else current_title
        )
        content_md = body if body else f"# {current_title}"
        sections.append(
            ExtractedDocSection(
                heading_path=breadcrumb,
                heading_level=max(1, min(6, current_level)),
                start_line=current_start,
                end_line=max(current_start, end_line_no),
                content_markdown=content_md,
                parent_index=current_parent_idx,
                mentioned_identifiers=extract_mentioned_identifiers(
                    f"{breadcrumb}\n{content_md}"
                ),
            )
        )

    for idx, line in enumerate(lines, start=1):
        hm = heading_re.match(line)
        if hm:
            if current_lines or heading_stack:
                _flush_section(idx - 1)
            lvl = len(hm.group(1))
            title = hm.group(2).strip()
            while heading_stack and heading_stack[-1][0] >= lvl:
                heading_stack.pop()
            parent_idx = heading_stack[-1][2] if heading_stack else None
            new_sec_idx = len(sections)
            heading_stack.append((lvl, title, new_sec_idx))
            current_title = title
            current_level = lvl
            current_start = idx
            current_parent_idx = parent_idx
            current_lines = [line]
        else:
            current_lines.append(line)

    _flush_section(len(lines))
    return DocExtractionResult(sections=sections, normalized_full_text=md_text)


class _SimpleHTMLSectionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []
        self._current_heading_level: int | None = None
        self._buf: list[str] = []
        self._in_ignored = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in ("script", "style"):
            self._in_ignored = True
            return
        if t in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush_buf()
            self._current_heading_level = int(t[1])
        elif t in ("p", "div", "li", "tr", "br", "section", "article"):
            self._flush_buf()

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("script", "style"):
            self._in_ignored = False
            self._buf = []
            return
        if t in ("h1", "h2", "h3", "h4", "h5", "h6"):
            text = " ".join("".join(self._buf).split()).strip()
            self._buf = []
            lvl = self._current_heading_level or 1
            self._current_heading_level = None
            if text:
                self.lines.append(f"{'#' * lvl} {text}")
        elif t in ("p", "div", "li", "tr", "section", "article"):
            self._flush_buf()

    def handle_data(self, data: str) -> None:
        if not self._in_ignored:
            self._buf.append(data)

    def _flush_buf(self) -> None:
        text = " ".join("".join(self._buf).split()).strip()
        self._buf = []
        if text:
            self.lines.append(text)


def parse_html_document(raw_html: str, relative_path: str) -> DocExtractionResult:
    """Convert HTML headings and paragraphs into Markdown hierarchy and parse sections."""
    parser = _SimpleHTMLSectionParser()
    parser.feed(raw_html)
    parser._flush_buf()
    md_text = "\n".join(parser.lines)
    return parse_markdown_sections(md_text, relative_path)


def parse_docx_bytes(raw_bytes: bytes, relative_path: str) -> DocExtractionResult:
    """Extract headings and paragraphs from a `.docx` OpenXML archive using standard library `zipfile` + `xml`."""
    md_lines: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            if "word/document.xml" not in zf.namelist():
                return DocExtractionResult()
            xml_bytes = zf.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        for p in root.findall(".//w:p", ns):
            style_el = p.find("./w:pPr/w:pStyle", ns)
            style_val = (
                style_el.attrib.get(f"{{{ns['w']}}}val", "") if style_el is not None else ""
            )
            texts = [t.text for t in p.findall(".//w:t", ns) if t.text]
            paragraph_text = "".join(texts).strip()
            if not paragraph_text:
                continue
            m_head = re.match(r"Heading([1-6])", style_val, re.IGNORECASE)
            if m_head:
                lvl = int(m_head.group(1))
                md_lines.append(f"{'#' * lvl} {paragraph_text}")
            else:
                md_lines.append(paragraph_text)
    except Exception:
        return DocExtractionResult()

    md_text = "\n".join(md_lines)
    return parse_markdown_sections(md_text, relative_path)


def parse_xlsx_bytes(raw_bytes: bytes, relative_path: str) -> DocExtractionResult:
    """Extract worksheets and tabular rows from an `.xlsx` OpenXML workbook using `zipfile` + `xml`."""
    md_lines: list[str] = [f"# Workbook {posixpath.basename(relative_path)}"]
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for si in ss_root.iter():
                    if si.tag.endswith("}t") and si.text:
                        shared_strings.append(si.text)

            sheet_names: list[tuple[str, str]] = []
            if "xl/workbook.xml" in zf.namelist():
                wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
                idx = 1
                for el in wb_root.iter():
                    if el.tag.endswith("}sheet"):
                        sname = el.attrib.get("name", f"Sheet{idx}")
                        sheet_names.append((sname, f"xl/worksheets/sheet{idx}.xml"))
                        idx += 1

            if not sheet_names:
                sheet_files = sorted(
                    n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
                )
                sheet_names = [(posixpath.basename(f), f) for f in sheet_files]

            for sname, spath in sheet_names:
                if spath not in zf.namelist():
                    continue
                md_lines.append(f"## Sheet: {sname}")
                sh_root = ET.fromstring(zf.read(spath))
                for row_el in sh_root.iter():
                    if not row_el.tag.endswith("}row"):
                        continue
                    row_vals: list[str] = []
                    for c_el in row_el:
                        if not c_el.tag.endswith("}c"):
                            continue
                        cell_type = c_el.attrib.get("t", "")
                        val_text = ""
                        for child in c_el:
                            if child.tag.endswith("}v") and child.text:
                                if cell_type == "s":
                                    s_idx = int(child.text)
                                    if 0 <= s_idx < len(shared_strings):
                                        val_text = shared_strings[s_idx]
                                else:
                                    val_text = child.text
                            elif child.tag.endswith("}is"):
                                inline_ts = [
                                    t.text for t in child.iter() if t.tag.endswith("}t") and t.text
                                ]
                                val_text = "".join(inline_ts)
                        if val_text:
                            row_vals.append(val_text.strip())
                    if row_vals:
                        md_lines.append(" | ".join(row_vals))
    except Exception:
        return DocExtractionResult()

    md_text = "\n".join(md_lines)
    return parse_markdown_sections(md_text, relative_path)


def parse_pdf_bytes(raw_bytes: bytes, relative_path: str) -> DocExtractionResult:
    """
    Extract text and sections from a `.pdf` document.
    Uses `pypdf` if installed, with a deterministic pure-Python PDF stream & text-operator parser fallback.
    """
    extracted_lines: list[str] = [f"# PDF Document: {posixpath.basename(relative_path)}"]
    try:
        import pypdf  # type: ignore[import-not-found]

        reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
        for page_idx, page in enumerate(reader.pages, start=1):
            txt = (page.extract_text() or "").strip()
            if txt:
                extracted_lines.append(f"## Page {page_idx}")
                extracted_lines.extend(txt.splitlines())
    except Exception:
        # Pure-Python PDF content stream fallback
        stream_re = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
        tj_re = re.compile(r"\(([^()\\]*(?:\\.[^()\\]*)*)\)\s*(?:Tj|')")
        tj_arr_re = re.compile(r"\[(.*?)\]\s*TJ", re.DOTALL)

        def _collect_text_ops(decoded_str: str) -> list[str]:
            found_tokens: list[str] = []
            for m in tj_re.finditer(decoded_str):
                found_tokens.append(m.group(1))
            for m in tj_arr_re.finditer(decoded_str):
                inner = m.group(1)
                parts = re.findall(r"\(([^()\\]*(?:\\.[^()\\]*)*)\)", inner)
                if parts:
                    found_tokens.append("".join(parts))
            return found_tokens

        page_no = 0
        for sm in stream_re.finditer(raw_bytes):
            chunk = sm.group(1)
            decoded_bytes = chunk
            try:
                decoded_bytes = zlib.decompress(chunk)
            except Exception:
                pass
            decoded_str = decoded_bytes.decode("latin-1", errors="ignore")
            tokens = _collect_text_ops(decoded_str)
            if tokens:
                page_no += 1
                extracted_lines.append(f"## Section {page_no}")
                extracted_lines.extend(tokens)

        if page_no == 0:
            raw_str = raw_bytes.decode("latin-1", errors="ignore")
            tokens = _collect_text_ops(raw_str)
            if tokens:
                extracted_lines.append("## Content")
                extracted_lines.extend(tokens)

    md_text = "\n".join(extracted_lines)
    return parse_markdown_sections(md_text, relative_path)


def extract_documentation(
    raw_bytes: bytes,
    language: str | None,
    relative_path: str,
) -> DocExtractionResult:
    """Unified dispatcher for Markdown, RST, AsciiDoc, HTML, DOCX, XLSX, and PDF documentation files."""
    lower = relative_path.lower()
    if lower.endswith(".docx") or language == "docx":
        return parse_docx_bytes(raw_bytes, relative_path)
    if lower.endswith(".xlsx") or language == "xlsx":
        return parse_xlsx_bytes(raw_bytes, relative_path)
    if lower.endswith(".pdf") or language == "pdf":
        return parse_pdf_bytes(raw_bytes, relative_path)
    raw_text = raw_bytes.decode("utf-8", errors="replace")
    if lower.endswith((".html", ".htm")) or language == "html":
        return parse_html_document(raw_text, relative_path)
    return parse_markdown_sections(raw_text, relative_path)

