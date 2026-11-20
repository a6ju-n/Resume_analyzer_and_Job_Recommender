"""
Resume text extraction service.

Uses PyMuPDF for PDF files and python-docx for DOCX files.
Falls back gracefully when a PDF is scanned (no selectable text).
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from services import skills as skill_vocab

# ---------------------------------------------------------------------------
# Optional imports — handle missing deps gracefully so tests can still import
# this module even before the packages are installed.
# ---------------------------------------------------------------------------
try:
    import pymupdf as fitz  # PyMuPDF ≥ 1.24 preferred import
    _FITZ_OK = True
except ImportError:
    try:
        import fitz  # older PyMuPDF fallback
        _FITZ_OK = True
    except ImportError:
        _FITZ_OK = False

try:
    import docx  # python-docx
    _DOCX_OK = True
except ImportError:
    _DOCX_OK = False


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def extract_text(filepath: str | Path, file_type: str) -> tuple[str, bool]:
    """
    Extract plain text from *filepath*.

    Returns
    -------
    (raw_text, is_scanned)
        raw_text   – extracted text (may be empty string for scanned PDFs)
        is_scanned – True when the PDF appears to have no selectable text
    """
    path = Path(filepath)
    if file_type == "pdf":
        return _extract_pdf(path)
    elif file_type == "docx":
        return _extract_docx(path), False
    else:
        raise ValueError(f"Unsupported file type: {file_type!r}")


def parse_resume_sections(raw_text: str) -> dict[str, Any]:
    """
    Parse a flat resume text into structured sections via regex heuristics.

    Returns a dict with keys:
        name, email, phone, linkedin,
        education, skills, programming_languages, frameworks,
        projects, internships, experience, certifications, achievements
    """
    text = _normalise(raw_text)
    skills_section = _extract_section(text, _SKILLS_HEADERS)
    detected = skill_vocab.detect_skills(text, skills_section)
    return {
        "name":                  _extract_name(text),
        "email":                 _extract_email(text),
        "phone":                 _extract_phone(text),
        "linkedin":              _extract_linkedin(text),
        "education":             _extract_section(text, _EDUCATION_HEADERS),
        "skills":                _extract_skills(text, detected),
        "detected_skills":       detected,
        "programming_languages": [x for x in detected if skill_vocab.kind_of(x) in skill_vocab.LANGUAGE_KINDS],
        "frameworks":            [x for x in detected if skill_vocab.kind_of(x) in skill_vocab.TOOLING_KINDS],
        "projects":              _extract_section(text, _PROJECT_HEADERS),
        "internships":           _extract_section(text, _INTERNSHIP_HEADERS),
        "experience":            _extract_section(text, _EXPERIENCE_HEADERS),
        "certifications":        _extract_section(text, _CERT_HEADERS),
        "achievements":          _extract_section(text, _ACHIEVEMENT_HEADERS),
    }


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def _extract_pdf(path: Path) -> tuple[str, bool]:
    if not _FITZ_OK:
        raise RuntimeError(
            "PyMuPDF is not installed. Run: pip install PyMuPDF"
        )
    text_parts: list[str] = []
    with fitz.open(str(path)) as doc:
        for page in doc:
            text_parts.append(page.get_text())
    raw = "\n".join(text_parts).strip()
    # Heuristic: fewer than 50 characters of real text → likely scanned
    is_scanned = len(raw) < 50
    return raw, is_scanned


# ---------------------------------------------------------------------------
# DOCX extraction
# ---------------------------------------------------------------------------

def _extract_docx(path: Path) -> str:
    if not _DOCX_OK:
        raise RuntimeError(
            "python-docx is not installed. Run: pip install python-docx"
        )
    document = docx.Document(str(path))
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    # Also extract table cells
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    paragraphs.append(cell.text.strip())
    return "\n".join(paragraphs)


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    # Convert unicode to ASCII-compatible form
    text = unicodedata.normalize("NFKC", text)
    # Collapse excessive whitespace but keep newlines
    text = re.sub(r"[^\S\n]+", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

_EMAIL_RE    = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE    = re.compile(r"(?:\+?\d[\d\s\-().]{7,}\d)")
_LINKEDIN_RE = re.compile(r"linkedin\.com/in/[\w\-]+", re.I)


def _extract_email(text: str) -> str:
    m = _EMAIL_RE.search(text)
    return m.group() if m else ""


def _extract_phone(text: str) -> str:
    m = _PHONE_RE.search(text)
    return m.group().strip() if m else ""


def _extract_linkedin(text: str) -> str:
    m = _LINKEDIN_RE.search(text)
    return m.group() if m else ""


def _extract_name(text: str) -> str:
    """
    Heuristic: the first non-empty line that is NOT an email/phone/URL
    and contains 2–5 words is likely the candidate's name.
    """
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if _EMAIL_RE.search(line) or _PHONE_RE.search(line):
            continue
        if re.search(r"https?://|linkedin|github|www\.", line, re.I):
            continue
        words = line.split()
        if 2 <= len(words) <= 5 and all(w[0].isupper() or w[0].isalpha() for w in words if w):
            return line
    return ""


# ---------------------------------------------------------------------------
# Section headers
# ---------------------------------------------------------------------------

_EDUCATION_HEADERS    = ["education", "academic background", "qualifications"]
_PROJECT_HEADERS      = ["projects", "personal projects", "academic projects"]
_INTERNSHIP_HEADERS   = ["internship", "internships", "industrial training"]
_EXPERIENCE_HEADERS   = ["experience", "work experience", "employment history",
                          "professional experience"]
_CERT_HEADERS         = ["certification", "certifications", "certificates", "courses"]
_ACHIEVEMENT_HEADERS  = ["achievement", "achievements", "awards", "honors", "honours"]
_SKILLS_HEADERS       = ["skills", "technical skills", "core competencies",
                          "technologies", "tools"]


def _extract_section(text: str, headers: list[str]) -> str:
    """
    Return the block of text that follows one of the given section headers
    until the next section header (any heading-like line).
    """
    lines   = text.splitlines()
    n       = len(lines)
    start   = -1
    end     = n

    # Find start
    for i, line in enumerate(lines):
        stripped = line.strip().lower().rstrip(":")
        if stripped in headers:
            start = i + 1
            break

    if start == -1:
        return ""

    # Find end: next line that looks like a section heading (short, mostly caps/title)
    next_header_re = re.compile(r"^[A-Z][A-Za-z &/\-]{0,40}:?\s*$")
    all_known_headers = (
        _EDUCATION_HEADERS + _PROJECT_HEADERS + _INTERNSHIP_HEADERS +
        _EXPERIENCE_HEADERS + _CERT_HEADERS + _ACHIEVEMENT_HEADERS +
        _SKILLS_HEADERS
    )
    for j in range(start, n):
        stripped = lines[j].strip().lower().rstrip(":")
        if stripped in all_known_headers:
            end = j
            break
        # Also stop at any line that looks like a new heading (all-caps short line)
        if j > start and next_header_re.match(lines[j].strip()) and len(lines[j].split()) <= 4:
            end = j
            break

    snippet = "\n".join(lines[start:end]).strip()
    return snippet[:2000]   # cap to avoid huge DB rows


# ---------------------------------------------------------------------------
# Skills / tech extraction
# ---------------------------------------------------------------------------

def get_skills_section(raw_text: str) -> str:
    """The text of the resume's Skills section ('' if it has none)."""
    return _extract_section(_normalise(raw_text), _SKILLS_HEADERS)


def _extract_programming_languages(text: str) -> list[str]:
    return skill_vocab.detect_by_kind(text, skill_vocab.LANGUAGE_KINDS)


def _extract_frameworks(text: str) -> list[str]:
    return skill_vocab.detect_by_kind(text, skill_vocab.TOOLING_KINDS)


def _extract_skills(text: str, detected: list[str] | None = None) -> list[str]:
    """
    Skills as the candidate wrote them, taken from the Skills section.
    With no Skills section, fall back to the skills recognised in the text
    rather than splitting the whole resume into meaningless fragments.
    """
    section = _extract_section(text, _SKILLS_HEADERS)
    if not section:
        return list(detected if detected is not None else skill_vocab.detect_skills(text))

    seen: set[str] = set()
    unique: list[str] = []
    for tok in re.split(r"[,•|·;\n\t/\\]+", section):
        tok = tok.rsplit(":", 1)[-1].strip().strip(".-– ")   # drop "Languages:" labels
        if 1 <= len(tok.split()) <= 4 and 1 <= len(tok) <= 40 and tok.lower() not in seen:
            seen.add(tok.lower())
            unique.append(tok)
    return unique[:40]
