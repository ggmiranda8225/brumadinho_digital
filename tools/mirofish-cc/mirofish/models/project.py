from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ProjectStatus(str, Enum):
    CREATED = "CREATED"
    SEED_PROCESSED = "SEED_PROCESSED"
    ONTOLOGY_GENERATED = "ONTOLOGY_GENERATED"
    GRAPH_BUILT = "GRAPH_BUILT"
    PERSONAS_GENERATED = "PERSONAS_GENERATED"
    SIMULATION_READY = "SIMULATION_READY"
    SIMULATION_RUNNING = "SIMULATION_RUNNING"
    SIMULATION_COMPLETE = "SIMULATION_COMPLETE"
    REPORT_GENERATED = "REPORT_GENERATED"


@dataclass
class Project:
    project_id: str
    name: str
    description: str
    status: ProjectStatus = ProjectStatus.CREATED
    seed_files: list[str] = field(default_factory=list)
    simulation_requirement: str = ""
    chunk_size: int = 500
    chunk_overlap: int = 50
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def update_status(self, new_status: ProjectStatus) -> None:
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "seed_files": self.seed_files,
            "simulation_requirement": self.simulation_requirement,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Project":
        now = datetime.now(timezone.utc)
        created_raw = data.get("created_at")
        updated_raw = data.get("updated_at")

        created_at = datetime.fromisoformat(created_raw) if isinstance(created_raw, str) else now
        updated_at = datetime.fromisoformat(updated_raw) if isinstance(updated_raw, str) else now

        return cls(
            project_id=data["project_id"],
            name=data["name"],
            description=data.get("description", ""),
            status=ProjectStatus(data.get("status", ProjectStatus.CREATED.value)),
            seed_files=list(data.get("seed_files", [])),
            simulation_requirement=data.get("simulation_requirement", ""),
            chunk_size=int(data.get("chunk_size", 500)),
            chunk_overlap=int(data.get("chunk_overlap", 50)),
            created_at=created_at,
            updated_at=updated_at,
        )
