from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EntityType(str, Enum):
    INDIVIDUAL = "INDIVIDUAL"
    GROUP = "GROUP"


INDIVIDUAL_TYPES = {
    "Person",
    "Student",
    "Teacher",
    "Journalist",
    "Politician",
    "PublicFigure",
    "Expert",
    "Activist",
    "Citizen",
    "Worker",
}

GROUP_TYPES = {
    "Organization",
    "Company",
    "Government",
    "Media",
    "University",
    "NGO",
    "Institution",
    "Party",
    "Agency",
}


def classify_entity_type(type_name: str) -> EntityType:
    normalized = type_name.strip().casefold()

    individual_norm = {value.casefold() for value in INDIVIDUAL_TYPES}
    group_norm = {value.casefold() for value in GROUP_TYPES}

    if normalized in individual_norm:
        return EntityType.INDIVIDUAL
    if normalized in group_norm:
        return EntityType.GROUP
    return EntityType.INDIVIDUAL


@dataclass
class AgentProfile:
    agent_id: str
    name: str
    bio: str
    persona: str
    age: int
    gender: str
    mbti: str
    country: str
    profession: str
    interested_topics: list[str] = field(default_factory=list)
    source_entity_uuid: str = ""
    source_entity_type: str = ""
    entity_classification: EntityType = EntityType.INDIVIDUAL
    platform_profiles: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "age": self.age,
            "gender": self.gender,
            "mbti": self.mbti,
            "country": self.country,
            "profession": self.profession,
            "interested_topics": self.interested_topics,
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "entity_classification": self.entity_classification.value,
            "platform_profiles": self.platform_profiles,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentProfile":
        classification_raw = data.get("entity_classification")
        if isinstance(classification_raw, str):
            classification = EntityType(classification_raw)
        else:
            classification = classify_entity_type(data.get("source_entity_type", ""))

        return cls(
            agent_id=data["agent_id"],
            name=data.get("name", ""),
            bio=data.get("bio", ""),
            persona=data.get("persona", ""),
            age=int(data.get("age", 0)),
            gender=data.get("gender", ""),
            mbti=data.get("mbti", ""),
            country=data.get("country", ""),
            profession=data.get("profession", ""),
            interested_topics=list(data.get("interested_topics", [])),
            source_entity_uuid=data.get("source_entity_uuid", ""),
            source_entity_type=data.get("source_entity_type", ""),
            entity_classification=classification,
            platform_profiles=dict(data.get("platform_profiles", {})),
        )
