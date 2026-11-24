from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mirofish.config import PROJECTS_DIR


class JsonStore:
    @staticmethod
    def ensure_dir(path: str | Path) -> None:
        path_obj = Path(path)
        target_dir = path_obj if path_obj.suffix == "" else path_obj.parent
        target_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def save(path: str | Path, data: dict[str, Any]) -> None:
        path_obj = Path(path)
        JsonStore.ensure_dir(path_obj)

        tmp_path = path_obj.with_suffix(f"{path_obj.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

        os.replace(tmp_path, path_obj)

    @staticmethod
    def load(path: str | Path) -> dict[str, Any]:
        path_obj = Path(path)
        if not path_obj.exists():
            return {}

        try:
            with path_obj.open("r", encoding="utf-8") as handle:
                content = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {}

        if isinstance(content, dict):
            return content
        return {}

    @staticmethod
    def append_jsonl(path: str | Path, record: dict[str, Any]) -> None:
        path_obj = Path(path)
        JsonStore.ensure_dir(path_obj)
        with path_obj.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")

    @staticmethod
    def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
        path_obj = Path(path)
        if not path_obj.exists():
            return []

        records: list[dict[str, Any]] = []
        with path_obj.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    records.append(value)

        return records

    @staticmethod
    def project_path(project_id: str, *parts: str) -> Path:
        return PROJECTS_DIR / project_id / Path(*parts)
