from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class SimulationStatus(str, Enum):
    INITIALIZED = "INITIALIZED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class AgentAction:
    round_num: int
    timestamp: datetime
    platform: str
    agent_id: str
    agent_name: str
    action_type: str
    action_args: dict[str, Any] = field(default_factory=dict)
    result: str | None = None
    success: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_num": self.round_num,
            "timestamp": self.timestamp.isoformat(),
            "platform": self.platform,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "action_type": self.action_type,
            "action_args": self.action_args,
            "result": self.result,
            "success": self.success,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentAction":
        timestamp_raw = data.get("timestamp")
        timestamp = (
            datetime.fromisoformat(timestamp_raw)
            if isinstance(timestamp_raw, str)
            else datetime.now(timezone.utc)
        )

        return cls(
            round_num=int(data.get("round_num", 0)),
            timestamp=timestamp,
            platform=data.get("platform", ""),
            agent_id=data.get("agent_id", ""),
            agent_name=data.get("agent_name", ""),
            action_type=data.get("action_type", ""),
            action_args=dict(data.get("action_args", {})),
            result=data.get("result"),
            success=bool(data.get("success", True)),
        )


@dataclass
class RoundSummary:
    round_num: int
    twitter_actions: int
    reddit_actions: int
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_num": self.round_num,
            "twitter_actions": self.twitter_actions,
            "reddit_actions": self.reddit_actions,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RoundSummary":
        timestamp_raw = data.get("timestamp")
        timestamp = (
            datetime.fromisoformat(timestamp_raw)
            if isinstance(timestamp_raw, str)
            else datetime.now(timezone.utc)
        )

        return cls(
            round_num=int(data.get("round_num", 0)),
            twitter_actions=int(data.get("twitter_actions", 0)),
            reddit_actions=int(data.get("reddit_actions", 0)),
            timestamp=timestamp,
        )


@dataclass
class SimulationState:
    simulation_id: str
    project_id: str
    status: SimulationStatus
    current_round: int
    total_rounds: int
    batch_size: int = 6
    round_summaries: list[RoundSummary] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "status": self.status.value,
            "current_round": self.current_round,
            "total_rounds": self.total_rounds,
            "batch_size": self.batch_size,
            "round_summaries": [summary.to_dict() for summary in self.round_summaries],
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SimulationState":
        started_raw = data.get("started_at")
        completed_raw = data.get("completed_at")

        started_at = (
            datetime.fromisoformat(started_raw)
            if isinstance(started_raw, str)
            else datetime.now(timezone.utc)
        )
        completed_at = datetime.fromisoformat(completed_raw) if isinstance(completed_raw, str) else None

        return cls(
            simulation_id=data["simulation_id"],
            project_id=data["project_id"],
            status=SimulationStatus(data.get("status", SimulationStatus.INITIALIZED.value)),
            current_round=int(data.get("current_round", 0)),
            total_rounds=int(data.get("total_rounds", 0)),
            batch_size=int(data.get("batch_size", 6)),
            round_summaries=[RoundSummary.from_dict(item) for item in data.get("round_summaries", [])],
            started_at=started_at,
            completed_at=completed_at,
        )
