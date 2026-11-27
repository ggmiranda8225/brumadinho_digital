from __future__ import annotations

import re
from typing import Any


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[dict[str, Any]]:
    """Split text into overlapping chunks, respecting sentence boundaries.

    Algorithm:
    1. Split text into sentences using regex: [.!?。！？]\s+
    2. Accumulate sentences until chunk_size (characters) is reached
    3. Create chunk, then start next chunk with overlap from end of previous
    4. Each chunk includes metadata: index, start_char, end_char, char_count

    Returns list of dicts: [{text, index, start_char, end_char, char_count}]

    Edge cases:
    - Very long sentences (>chunk_size): split at word boundaries instead
    - Empty text: return empty list
    - Text shorter than chunk_size: return single chunk
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if overlap < 0:
        raise ValueError("overlap must be >= 0")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    normalized_text = text.strip()
    if not normalized_text:
        return []

    if len(normalized_text) <= chunk_size:
        return [
            {
                "text": normalized_text,
                "index": 0,
                "start_char": 0,
                "end_char": len(normalized_text),
                "char_count": len(normalized_text),
            }
        ]

    sentences = _split_sentences(normalized_text)
    fragments: list[str] = []
    for sentence in sentences:
        if len(sentence) <= chunk_size:
            fragments.append(sentence)
            continue

        if re.search(r"\s", sentence):
            parts = re.findall(r"\S+\s*", sentence)
            current = ""
            for part in parts:
                if len(current) + len(part) <= chunk_size:
                    current += part
                else:
                    if current:
                        fragments.append(current)
                    current = part
            if current:
                fragments.append(current)
        else:
            for i in range(0, len(sentence), chunk_size):
                fragments.append(sentence[i : i + chunk_size])

    chunks: list[dict[str, Any]] = []
    current_chunk = ""
    current_start = 0
    consumed = 0

    for fragment in fragments:
        if not current_chunk:
            current_start = consumed

        if len(current_chunk) + len(fragment) <= chunk_size:
            current_chunk += fragment
            consumed += len(fragment)
            continue

        if current_chunk.strip():
            chunks.append(
                {
                    "text": current_chunk,
                    "index": len(chunks),
                    "start_char": current_start,
                    "end_char": consumed,
                    "char_count": len(current_chunk),
                }
            )

        overlap_text = current_chunk[-overlap:] if overlap > 0 else ""
        available_overlap = max(0, chunk_size - len(fragment))
        overlap_text = overlap_text[-available_overlap:] if available_overlap else ""

        current_chunk = overlap_text + fragment
        current_start = max(0, consumed - len(overlap_text))
        consumed += len(fragment)

    if current_chunk.strip():
        chunks.append(
            {
                "text": current_chunk,
                "index": len(chunks),
                "start_char": current_start,
                "end_char": consumed,
                "char_count": len(current_chunk),
            }
        )

    return chunks


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences. Handles English and Chinese punctuation.
    Preserves sentence-ending punctuation.
    """
    pattern = re.compile(r".+?(?:[.!?。！？](?:\s+|$)|$)", flags=re.S)
    return [segment for segment in pattern.findall(text) if segment.strip()]
