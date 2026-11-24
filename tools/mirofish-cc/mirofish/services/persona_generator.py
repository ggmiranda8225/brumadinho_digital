from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from mirofish.config import PROJECTS_DIR
from mirofish.models.agent import (
    GROUP_TYPES,
    INDIVIDUAL_TYPES,
    AgentProfile,
    EntityType,
    classify_entity_type,
)
from mirofish.models.graph import GraphNode, KnowledgeGraph
from mirofish.store.json_store import JsonStore


class PersonaGenerator:
    @staticmethod
    def list_entities_for_personas(project_id: str) -> Dict[str, Any]:
        """List all entities and whether a persona profile exists for each."""
        graph = PersonaGenerator._load_graph(project_id)
        profiles = PersonaGenerator.list_profiles(project_id)

        by_source_uuid = {
            str(profile.get("source_entity_uuid", "")).strip()
            for profile in profiles
            if str(profile.get("source_entity_uuid", "")).strip()
        }

        entities: List[Dict[str, Any]] = []
        for node in sorted(graph.nodes.values(), key=lambda item: item.name.casefold()):
            entity_type = PersonaGenerator._get_entity_type(node)
            classification = classify_entity_type(entity_type)
            has_profile = node.uuid in by_source_uuid

            context = PersonaGenerator._build_entity_context_from_graph(
                graph=graph,
                node=node,
                simulation_requirement=PersonaGenerator._load_simulation_requirement(
                    project_id
                ),
            )

            entities.append(
                {
                    "entity_uuid": node.uuid,
                    "entity_name": node.name,
                    "entity_type": entity_type,
                    "entity_classification": classification.value.lower(),
                    "has_profile": has_profile,
                    "context": context,
                }
            )

        total_entities = len(entities)
        profiles_generated = sum(1 for item in entities if item["has_profile"])

        return {
            "total_entities": total_entities,
            "profiles_generated": profiles_generated,
            "remaining": max(0, total_entities - profiles_generated),
            "entities": entities,
        }

    @staticmethod
    def build_entity_context(project_id: str, entity_uuid: str) -> Dict[str, Any]:
        """Build rich context for one entity for persona generation."""
        graph = PersonaGenerator._load_graph(project_id)
        node = graph.get_node_by_uuid(entity_uuid)
        if node is None:
            raise ValueError(f"Entity not found in graph: {entity_uuid}")

        simulation_requirement = PersonaGenerator._load_simulation_requirement(
            project_id
        )
        return PersonaGenerator._build_entity_context_from_graph(
            graph=graph,
            node=node,
            simulation_requirement=simulation_requirement,
        )

    @staticmethod
    def save_profile(project_id: str, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and save one agent profile."""
        data = dict(profile_data)

        agent_id = str(data.get("agent_id") or uuid.uuid4())
        data["agent_id"] = agent_id

        name = str(data.get("name", "")).strip()
        if not name:
            raise ValueError("Profile 'name' is required")

        source_entity_type = str(data.get("source_entity_type", "")).strip()
        classification = PersonaGenerator._resolve_entity_classification(data)

        handle_slug = PersonaGenerator._slugify_handle(name)
        platform_profiles = {
            "twitter": {
                "handle": f"@{handle_slug}",
                "display_name": name,
            },
            "reddit": {
                "username": f"u/{handle_slug}",
                "display_name": name,
            },
        }

        profile = AgentProfile(
            agent_id=agent_id,
            name=name,
            bio=str(data.get("bio", "")).strip(),
            persona=str(data.get("persona", "")).strip(),
            age=int(data.get("age", 0)),
            gender=str(data.get("gender", "")).strip(),
            mbti=str(data.get("mbti", "")).strip(),
            country=str(data.get("country", "")).strip(),
            profession=str(data.get("profession", "")).strip(),
            interested_topics=PersonaGenerator._normalize_topics(
                data.get("interested_topics", [])
            ),
            source_entity_uuid=str(data.get("source_entity_uuid", "")).strip(),
            source_entity_type=source_entity_type,
            entity_classification=classification,
            platform_profiles=platform_profiles,
        )

        profile_path = PersonaGenerator._agents_dir(project_id) / f"{agent_id}.json"
        JsonStore.save(profile_path, profile.to_dict())

        return {"agent_id": agent_id, "name": profile.name, "saved": True}

    @staticmethod
    def save_batch_profiles(
        project_id: str, profiles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Save multiple profiles and report aggregate success/failure."""
        saved = 0
        failed = 0
        errors: List[Dict[str, str]] = []

        for index, profile in enumerate(profiles):
            try:
                PersonaGenerator.save_profile(project_id, profile)
                saved += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                profile_name = (
                    str(profile.get("name", "")).strip() or f"profile_{index}"
                )
                errors.append(
                    {
                        "profile": profile_name,
                        "error": str(exc),
                    }
                )

        return {"saved": saved, "failed": failed, "errors": errors}

    @staticmethod
    def get_profile(project_id: str, agent_id: str) -> Optional[Dict[str, Any]]:
        """Load a single saved agent profile by ID."""
        profile_path = PersonaGenerator._agents_dir(project_id) / f"{agent_id}.json"
        profile_data = JsonStore.load(profile_path)
        if not profile_data:
            return None

        try:
            profile = AgentProfile.from_dict(profile_data)
        except Exception:  # noqa: BLE001
            return None

        return profile.to_dict()

    @staticmethod
    def list_profiles(project_id: str) -> List[Dict[str, Any]]:
        """List all saved agent profiles with brief summaries."""
        agents_dir = PersonaGenerator._agents_dir(project_id)
        if not agents_dir.exists():
            return []

        summaries: List[Dict[str, Any]] = []
        for file_path in sorted(agents_dir.glob("*.json")):
            data = JsonStore.load(file_path)
            if not data:
                continue

            try:
                profile = AgentProfile.from_dict(data)
            except Exception:  # noqa: BLE001
                continue

            summaries.append(
                {
                    "agent_id": profile.agent_id,
                    "name": profile.name,
                    "profession": profile.profession,
                    "entity_classification": profile.entity_classification.value.lower(),
                    "bio": profile.bio,
                    "source_entity_uuid": profile.source_entity_uuid,
                }
            )

        return summaries

    @staticmethod
    def get_status(project_id: str) -> Dict[str, Any]:
        """Return persona generation progress for the project."""
        listing = PersonaGenerator.list_entities_for_personas(project_id)
        remaining = int(listing["remaining"])
        return {
            "total_entities": int(listing["total_entities"]),
            "profiles_generated": int(listing["profiles_generated"]),
            "remaining": remaining,
            "is_complete": remaining == 0,
        }

    @staticmethod
    def _build_entity_context_from_graph(
        graph: KnowledgeGraph,
        node: GraphNode,
        simulation_requirement: str,
    ) -> Dict[str, Any]:
        entity_type = PersonaGenerator._get_entity_type(node)
        classification = classify_entity_type(entity_type)

        edges = graph.get_edges_for_node(node.uuid)
        related_facts = [edge.fact.strip() for edge in edges if edge.fact.strip()]

        connected_entities: List[Dict[str, str]] = []
        for edge in edges:
            if edge.source_node_uuid == node.uuid:
                related_uuid = edge.target_node_uuid
                relationship = edge.name or "related_to"
            else:
                related_uuid = edge.source_node_uuid
                relationship = edge.name or "related_to"

            related_node = graph.get_node_by_uuid(related_uuid)
            if related_node is None:
                continue

            connected_entities.append(
                {
                    "name": related_node.name,
                    "type": PersonaGenerator._get_entity_type(related_node),
                    "relationship": relationship,
                }
            )

        return {
            "entity_name": node.name,
            "entity_type": entity_type,
            "entity_classification": classification.value.lower(),
            "entity_summary": node.summary,
            "entity_attributes": dict(node.attributes),
            "related_facts": PersonaGenerator._dedupe_preserve_order(related_facts),
            "connected_entities": PersonaGenerator._dedupe_connections(
                connected_entities
            ),
            "simulation_requirement": simulation_requirement,
        }

    @staticmethod
    def _load_graph(project_id: str) -> KnowledgeGraph:
        graph_path = JsonStore.project_path(project_id, "graph", "graph.json")
        payload = JsonStore.load(graph_path)
        if payload:
            return KnowledgeGraph.from_dict(payload)

        return KnowledgeGraph(graph_id=f"{project_id}-graph")

    @staticmethod
    def _load_simulation_requirement(project_id: str) -> str:
        project_path = JsonStore.project_path(project_id, "project.json")
        project_payload = JsonStore.load(project_path)
        requirement = project_payload.get("simulation_requirement", "")
        return str(requirement).strip()

    @staticmethod
    def _get_entity_type(node: GraphNode) -> str:
        if node.labels:
            return str(node.labels[0]).strip() or "Person"
        return "Person"

    @staticmethod
    def _resolve_entity_classification(profile_data: Dict[str, Any]) -> EntityType:
        raw_value = profile_data.get("entity_classification")
        if isinstance(raw_value, str) and raw_value.strip():
            normalized = raw_value.strip().upper()
            if normalized in {EntityType.INDIVIDUAL.value, EntityType.GROUP.value}:
                return EntityType(normalized)
            if normalized == "INDIVIDUAL":
                return EntityType.INDIVIDUAL
            if normalized == "GROUP":
                return EntityType.GROUP

        source_entity_type = str(profile_data.get("source_entity_type", "")).strip()
        if source_entity_type in GROUP_TYPES:
            return EntityType.GROUP
        if source_entity_type in INDIVIDUAL_TYPES:
            return EntityType.INDIVIDUAL
        return classify_entity_type(source_entity_type)

    @staticmethod
    def _normalize_topics(raw_topics: Any) -> List[str]:
        if isinstance(raw_topics, list):
            values = [str(topic).strip() for topic in raw_topics if str(topic).strip()]
            return values
        return []

    @staticmethod
    def _dedupe_preserve_order(items: List[str]) -> List[str]:
        seen: set[str] = set()
        unique: List[str] = []
        for item in items:
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    @staticmethod
    def _dedupe_connections(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
        seen: set[str] = set()
        unique: List[Dict[str, str]] = []
        for item in items:
            key = json.dumps(item, sort_keys=True, ensure_ascii=False)
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    @staticmethod
    def _slugify_handle(name: str) -> str:
        slug = re.sub(r"[^a-z0-9_]+", "_", name.casefold()).strip("_")
        return slug or f"agent_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _agents_dir(project_id: str) -> Path:
        path = PROJECTS_DIR / project_id / "agents"
        JsonStore.ensure_dir(path)
        return path
