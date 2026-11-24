from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from mirofish.config import PROJECTS_DIR
from mirofish.store.json_store import JsonStore
from mirofish.utils.file_parser import parse_file, validate_file
from mirofish.utils.text_chunker import chunk_text


class SeedProcessor:
    @staticmethod
    def process(
        project_id: str,
        file_paths: List[str],
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> Dict[str, Any]:
        """Process seed materials for a project.

        1. Validate all files
        2. Parse each file to text
        3. Concatenate with file headers
        4. Chunk combined text
        5. Save extracted_text.txt, chunks.json, and seed_meta.json
        6. Return metadata
        """
        if not file_paths:
            raise ValueError("At least one seed file is required")

        seed_dir = PROJECTS_DIR / project_id / "seed"
        seed_dir.mkdir(parents=True, exist_ok=True)

        sections: List[str] = []
        file_names: List[str] = []

        for file_path in file_paths:
            is_valid, error = validate_file(file_path)
            if not is_valid:
                raise ValueError(error)

            path_obj = Path(file_path)
            file_names.append(path_obj.name)
            content = parse_file(file_path).strip()
            sections.append(f"=== File: {path_obj.name} ===\n{content}\n")

        combined_text = "\n".join(sections).strip()
        chunks = chunk_text(combined_text, chunk_size=chunk_size, overlap=chunk_overlap)

        extracted_text_path = seed_dir / "extracted_text.txt"
        chunks_path = seed_dir / "chunks.json"
        seed_meta_path = seed_dir / "seed_meta.json"

        extracted_text_path.write_text(combined_text, encoding="utf-8")
        chunks_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        metadata: Dict[str, Any] = {
            "project_id": project_id,
            "processed_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "file_count": len(file_names),
            "total_chars": len(combined_text),
            "num_chunks": len(chunks),
            "file_names": file_names,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }
        JsonStore.save(seed_meta_path, metadata)
        return metadata

    @staticmethod
    def get_chunks(project_id: str, batch_index: int = 0, batch_size: int = 5) -> Dict[str, Any]:
        """Get a batch of chunks for entity extraction."""
        if batch_index < 0:
            raise ValueError("batch_index must be >= 0")
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")

        chunks_path = PROJECTS_DIR / project_id / "seed" / "chunks.json"
        if not chunks_path.exists():
            return {
                "batch_index": batch_index,
                "batch_size": batch_size,
                "total_chunks": 0,
                "chunks": [],
                "has_more": False,
            }

        raw_chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
        if not isinstance(raw_chunks, list):
            raise ValueError("chunks.json must contain a list")

        total_chunks = len(raw_chunks)
        start = batch_index * batch_size
        end = start + batch_size
        selected = raw_chunks[start:end]

        return {
            "batch_index": batch_index,
            "batch_size": batch_size,
            "total_chunks": total_chunks,
            "chunks": [str(item.get("text", "")) for item in selected if isinstance(item, dict)],
            "has_more": end < total_chunks,
        }

    @staticmethod
    def get_text_preview(project_id: str, max_chars: int = 3000) -> str:
        """Get first max_chars of extracted text for ontology generation."""
        if max_chars <= 0:
            raise ValueError("max_chars must be > 0")

        text_path = PROJECTS_DIR / project_id / "seed" / "extracted_text.txt"
        text = text_path.read_text(encoding="utf-8") if text_path.exists() else ""
        preview = text[:max_chars]
        return f"{preview}\n\n[total_chars={len(text)}]"

    @staticmethod
    def get_stats(project_id: str) -> Dict[str, Any]:
        """Return seed processing statistics."""
        meta_path = PROJECTS_DIR / project_id / "seed" / "seed_meta.json"
        return JsonStore.load(meta_path)
