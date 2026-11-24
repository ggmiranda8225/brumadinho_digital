from __future__ import annotations

import logging
import re
from pathlib import Path

ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt"}
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024
_TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "latin-1", "gb2312", "gbk")

logger = logging.getLogger(__name__)


def parse_file(file_path: str) -> str:
    """Parse PDF, Markdown, or TXT file to plain text.
    Auto-detects encoding for text files.
    Raises ValueError for unsupported file types.
    Raises FileNotFoundError if file doesn't exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    extension = path.suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {extension}")

    if extension == ".pdf":
        return _parse_pdf(file_path)
    if extension in {".md", ".markdown"}:
        return _parse_markdown(file_path)
    return _parse_text(file_path)


def _parse_pdf(file_path: str) -> str:
    """Extract text from PDF using PyPDF2.
    Concatenate all pages with double newline separator.
    Handle encrypted PDFs gracefully (raise ValueError).
    """
    try:
        from PyPDF2 import PdfReader
    except ImportError as exc:
        logger.exception("PyPDF2 is required for PDF parsing")
        raise ValueError("PyPDF2 is required for PDF parsing") from exc

    try:
        reader = PdfReader(file_path)
    except Exception as exc:
        logger.exception("Failed to open PDF file: %s", file_path)
        raise ValueError(f"Failed to parse PDF: {file_path}") from exc

    if reader.is_encrypted:
        raise ValueError(f"Encrypted PDF is not supported: {file_path}")

    pages: list[str] = []
    for page_index, page in enumerate(reader.pages):
        try:
            pages.append((page.extract_text() or "").strip())
        except Exception as exc:
            logger.exception("Failed to extract text from PDF page %s", page_index)
            raise ValueError(f"Failed to extract text from PDF: {file_path}") from exc

    return "\n\n".join(filter(None, pages)).strip()


def _parse_markdown(file_path: str) -> str:
    """Read markdown file, strip HTML tags if present.
    Preserve markdown structure (headers, lists, etc.) as plain text.
    Try UTF-8 first, then detect encoding.
    """
    content = _read_text_with_encoding(file_path)
    content = re.sub(r"<[^>]+>", "", content)
    return content.strip()


def _parse_text(file_path: str) -> str:
    """Read text file with encoding detection.
    Try UTF-8 first, then try common encodings: utf-8-sig, latin-1, gb2312, gbk.
    Raise ValueError if cannot decode.
    """
    return _read_text_with_encoding(file_path).strip()


def _read_text_with_encoding(file_path: str) -> str:
    for encoding in _TEXT_ENCODINGS:
        try:
            return Path(file_path).read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            logger.exception("Failed to read file: %s", file_path)
            raise ValueError(f"Failed to read file: {file_path}") from exc

    raise ValueError(f"Could not decode file with supported encodings: {file_path}")


def validate_file(file_path: str) -> tuple[bool, str]:
    """Validate file exists, has allowed extension, and is within size limit.
    Returns (is_valid, error_message).
    """
    path = Path(file_path)
    if not path.exists():
        return False, f"File does not exist: {file_path}"

    if not path.is_file():
        return False, f"Not a file: {file_path}"

    extension = path.suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        return False, f"Unsupported file extension: {extension}"

    file_size = path.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        size_mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
        return False, f"File exceeds size limit ({size_mb}MB): {file_path}"

    return True, ""
