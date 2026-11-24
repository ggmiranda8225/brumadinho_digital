from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from mirofish.config import PROJECTS_DIR
from mirofish.store.json_store import JsonStore


class ChatService:
    @staticmethod
    def get_agent_interview_context(project_id: str, agent_name: str) -> Dict[str, Any]:
        """Build full context for role-playing a simulated agent interview."""
        profile = ChatService._find_agent_by_name(project_id, agent_name)
        if profile is None:
            raise ValueError(f"Agent not found: {agent_name}")

        agent_id = str(profile.get("agent_id", "")).strip()
        action_history = ChatService._load_action_history(project_id, agent_id)
        posts_created = ChatService._load_agent_posts(project_id, agent_id)
        memories = ChatService._load_agent_memories(project_id, agent_id)
        graph_facts = ChatService._load_agent_graph_facts(project_id, profile)

        return {
            "agent_profile": {
                "agent_id": agent_id,
                "name": str(profile.get("name", "")).strip(),
                "bio": str(profile.get("bio", "")).strip(),
                "persona": str(profile.get("persona", "")).strip(),
                "profession": str(profile.get("profession", "")).strip(),
                "interests": list(profile.get("interested_topics", [])),
                "entity_classification": str(profile.get("entity_classification", "")).strip(),
                "source_entity_uuid": str(profile.get("source_entity_uuid", "")).strip(),
                "source_entity_type": str(profile.get("source_entity_type", "")).strip(),
            },
            "action_history": action_history,
            "posts_created": posts_created,
            "memories": memories,
            "graph_facts": graph_facts,
            "simulation_requirement": ChatService._load_simulation_requirement(project_id),
        }

    @staticmethod
    def get_report_chat_context(project_id: str) -> Dict[str, Any]:
        """Build context bundle for report-based chat Q&A."""
        report_path = JsonStore.project_path(project_id, "reports", "report.md")
        report_content = report_path.read_text(encoding="utf-8") if report_path.exists() else ""

        graph_stats = ChatService._load_graph_stats(project_id)
        simulation_summary = ChatService._load_simulation_summary(project_id)
        project_payload = JsonStore.load(JsonStore.project_path(project_id, "project.json"))

        return {
            "report_content": report_content,
            "graph_stats": graph_stats,
            "simulation_summary": simulation_summary,
            "project_info": {
                "name": str(project_payload.get("name", "")).strip(),
                "requirement": str(project_payload.get("simulation_requirement", "")).strip(),
            },
        }

    @staticmethod
    def get_batch_interview_context(
        project_id: str,
        agent_names: List[str],
        topic: str | None = None,
    ) -> Dict[str, Any]:
        """Prepare compact interview contexts for multiple agents."""
        agents_payload: List[Dict[str, Any]] = []

        for name in agent_names:
            interview_context = ChatService.get_agent_interview_context(project_id, name)
            profile = interview_context["agent_profile"]
            posts_created = interview_context.get("posts_created", [])

            agents_payload.append(
                {
                    "name": profile.get("name", ""),
                    "profession": profile.get("profession", ""),
                    "persona_summary": ChatService._shorten(
                        str(profile.get("persona", "")),
                        max_chars=320,
                    ),
                    "action_summary": ChatService._get_agent_action_summary(
                        project_id,
                        str(profile.get("agent_id", "")),
                    ),
                    "key_posts": [
                        {
                            "content": str(post.get("content", "")),
                            "platform": str(post.get("platform", "")),
                        }
                        for post in posts_created[:5]
                    ],
                }
            )

        return {
            "topic": str(topic or "").strip(),
            "simulation_requirement": ChatService._load_simulation_requirement(project_id),
            "agents": agents_payload,
        }

    @staticmethod
    def list_available_agents(project_id: str) -> Dict[str, Any]:
        """List all agents available for interview with activity stats."""
        agents_dir = ChatService._agents_dir(project_id)
        action_counts = ChatService._count_actions_by_agent(project_id)

        agents: List[Dict[str, Any]] = []
        for path in sorted(agents_dir.glob("*.json")):
            profile = JsonStore.load(path)
            if not profile:
                continue

            agent_id = str(profile.get("agent_id", "")).strip()
            posts = ChatService._load_agent_posts(project_id, agent_id)
            agents.append(
                {
                    "agent_id": agent_id,
                    "name": str(profile.get("name", "")).strip(),
                    "profession": str(profile.get("profession", "")).strip(),
                    "entity_classification": str(profile.get("entity_classification", "")).strip(),
                    "bio": str(profile.get("bio", "")).strip(),
                    "action_count": action_counts.get(agent_id, 0),
                    "post_count": len(posts),
                }
            )

        return {"agents": agents, "total": len(agents)}

    @staticmethod
    def get_conversation_context(
        project_id: str,
        agent_name: str,
        conversation_history: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """Build context for continuing a specific agent conversation."""
        context = ChatService.get_agent_interview_context(project_id, agent_name)
        context["conversation_history"] = [
            {
                "role": str(item.get("role", "")).strip(),
                "content": str(item.get("content", "")).strip(),
            }
            for item in (conversation_history or [])
            if isinstance(item, dict)
        ]
        return context

    @staticmethod
    def _find_agent_by_name(project_id: str, name: str) -> Optional[Dict[str, Any]]:
        """Find agent profile by display name (case-insensitive)."""
        target = name.strip().casefold()
        if not target:
            return None

        for path in sorted(ChatService._agents_dir(project_id).glob("*.json")):
            profile = JsonStore.load(path)
            if not profile:
                continue

            profile_name = str(profile.get("name", "")).strip()
            if profile_name.casefold() == target:
                return profile

        return None

    @staticmethod
    def _get_agent_action_summary(
        project_id: str,
        agent_id: str,
        max_actions: int = 10,
    ) -> str:
        """Generate a brief summary line for one agent's activity."""
        records = ChatService._load_action_history(project_id, agent_id)
        if not records:
            return "No recorded actions."

        action_counts: Dict[str, int] = {}
        platform_counts: Dict[str, int] = {}

        for item in records:
            action = str(item.get("action", "")).strip() or "UNKNOWN"
            platform = str(item.get("platform", "")).strip() or "unknown"
            action_counts[action] = action_counts.get(action, 0) + 1
            platform_counts[platform] = platform_counts.get(platform, 0) + 1

        top_actions = sorted(action_counts.items(), key=lambda value: value[1], reverse=True)
        top_platforms = sorted(platform_counts.items(), key=lambda value: value[1], reverse=True)

        action_text = ", ".join(f"{count} {action}" for action, count in top_actions[:4])
        platform_text = ", ".join(
            f"{count} on {platform}" for platform, count in top_platforms
        )

        sample = records[:max_actions]
        first_round = min(int(item.get("round", 0)) for item in sample)
        last_round = max(int(item.get("round", 0)) for item in sample)

        return (
            f"{len(records)} total actions from round {first_round} to {last_round}; "
            f"top actions: {action_text}; distribution: {platform_text}."
        )

    @staticmethod
    def _load_agent_posts(project_id: str, agent_id: str) -> List[Dict[str, Any]]:
        """Load posts created by this agent from saved platform state files."""
        posts: List[Dict[str, Any]] = []
        simulation_dir = JsonStore.project_path(project_id, "simulation")

        for platform in ("twitter", "reddit"):
            payload = JsonStore.load(simulation_dir / f"{platform}_platform.json")
            raw_posts = payload.get("posts", {})
            if not isinstance(raw_posts, dict):
                continue

            for post in raw_posts.values():
                if not isinstance(post, dict):
                    continue
                if str(post.get("author_id", "")).strip() != agent_id:
                    continue

                posts.append(
                    {
                        "platform": str(post.get("platform", platform)).strip() or platform,
                        "content": str(post.get("content", "")).strip(),
                        "likes": len(post.get("likes", [])),
                        "reposts": len(post.get("reposts", [])),
                        "replies": len(post.get("reply_ids", [])),
                        "round": int(post.get("round_created", 0)),
                    }
                )

        posts.sort(key=lambda item: item.get("round", 0), reverse=True)
        return posts

    @staticmethod
    def _load_action_history(project_id: str, agent_id: str) -> List[Dict[str, Any]]:
        records = JsonStore.read_jsonl(JsonStore.project_path(project_id, "simulation", "actions.jsonl"))

        history: List[Dict[str, Any]] = []
        for record in records:
            if str(record.get("agent_id", "")).strip() != agent_id:
                continue

            args = record.get("action_args", {})
            content = ""
            if isinstance(args, dict):
                content = str(args.get("content", "")).strip()

            history.append(
                {
                    "round": int(record.get("round_num", record.get("round", 0)) or 0),
                    "platform": str(record.get("platform", "")).strip(),
                    "action": str(record.get("action_type", record.get("action", ""))).strip(),
                    "content": content,
                }
            )

        history.sort(key=lambda item: item.get("round", 0), reverse=True)
        return history

    @staticmethod
    def _load_agent_memories(project_id: str, agent_id: str) -> List[Dict[str, Any]]:
        path = JsonStore.project_path(project_id, "agents", f"{agent_id}_memories.jsonl")
        memories = JsonStore.read_jsonl(path)
        return [
            {
                "round": int(item.get("round", item.get("round_num", 0)) or 0),
                "memory": str(item.get("memory", "")).strip(),
            }
            for item in memories
            if isinstance(item, dict)
        ]

    @staticmethod
    def _load_agent_graph_facts(project_id: str, profile: Dict[str, Any]) -> List[str]:
        graph_path = JsonStore.project_path(project_id, "graph", "graph.json")
        graph = JsonStore.load(graph_path)
        if not graph:
            return []

        target_uuid = str(profile.get("source_entity_uuid", "")).strip()
        target_name = str(profile.get("name", "")).strip().casefold()

        nodes = graph.get("nodes", {})
        node_name_by_uuid: Dict[str, str] = {}

        if isinstance(nodes, dict):
            for node_uuid, node in nodes.items():
                if isinstance(node, dict):
                    node_name_by_uuid[str(node_uuid)] = str(node.get("name", "")).strip()

        edges = graph.get("edges", [])
        facts: List[str] = []

        for edge in edges if isinstance(edges, list) else []:
            if not isinstance(edge, dict):
                continue
            source_uuid = str(edge.get("source_node_uuid", edge.get("source", ""))).strip()
            target_edge_uuid = str(edge.get("target_node_uuid", edge.get("target", ""))).strip()

            source_name = node_name_by_uuid.get(source_uuid, "")
            target_edge_name = node_name_by_uuid.get(target_edge_uuid, "")
            is_related = (
                (target_uuid and (source_uuid == target_uuid or target_edge_uuid == target_uuid))
                or source_name.casefold() == target_name
                or target_edge_name.casefold() == target_name
            )
            if not is_related:
                continue

            fact = str(edge.get("fact", "")).strip()
            relation = str(edge.get("name", edge.get("type", "related_to"))).strip() or "related_to"
            if fact:
                facts.append(f"{source_name or source_uuid} --{relation}--> {target_edge_name or target_edge_uuid}: {fact}")

        return facts[:20]

    @staticmethod
    def _load_graph_stats(project_id: str) -> Dict[str, Any]:
        graph = JsonStore.load(JsonStore.project_path(project_id, "graph", "graph.json"))
        if not graph:
            return {"nodes": 0, "edges": 0, "types": {"entity": {}, "relationship": {}}}

        nodes = graph.get("nodes", {})
        edges = graph.get("edges", [])

        node_iter = nodes.values() if isinstance(nodes, dict) else []
        entity_types: Dict[str, int] = {}
        for node in node_iter:
            if not isinstance(node, dict):
                continue
            labels = node.get("labels", [])
            node_type = str(labels[0]).strip() if isinstance(labels, list) and labels else "Unknown"
            entity_types[node_type] = entity_types.get(node_type, 0) + 1

        relationship_types: Dict[str, int] = {}
        for edge in edges if isinstance(edges, list) else []:
            if not isinstance(edge, dict):
                continue
            rel = str(edge.get("name", edge.get("type", "Unknown"))).strip() or "Unknown"
            relationship_types[rel] = relationship_types.get(rel, 0) + 1

        return {
            "nodes": len(nodes) if isinstance(nodes, dict) else 0,
            "edges": len(edges) if isinstance(edges, list) else 0,
            "types": {
                "entity": entity_types,
                "relationship": relationship_types,
            },
        }

    @staticmethod
    def _load_simulation_summary(project_id: str) -> Dict[str, Any]:
        actions = JsonStore.read_jsonl(JsonStore.project_path(project_id, "simulation", "actions.jsonl"))
        rounds: set[int] = set()
        agents: set[str] = set()
        platforms: Dict[str, int] = {}

        for action in actions:
            round_num = action.get("round_num", action.get("round"))
            if isinstance(round_num, int):
                rounds.add(round_num)

            agent_id = str(action.get("agent_id", "")).strip()
            if agent_id:
                agents.add(agent_id)

            platform = str(action.get("platform", "")).strip().lower()
            if platform:
                platforms[platform] = platforms.get(platform, 0) + 1

        return {
            "rounds": max(rounds) if rounds else 0,
            "agents": len(agents),
            "actions": len(actions),
            "platforms": platforms,
        }

    @staticmethod
    def _count_actions_by_agent(project_id: str) -> Dict[str, int]:
        actions = JsonStore.read_jsonl(JsonStore.project_path(project_id, "simulation", "actions.jsonl"))
        counts: Dict[str, int] = {}

        for action in actions:
            agent_id = str(action.get("agent_id", "")).strip()
            if not agent_id:
                continue
            counts[agent_id] = counts.get(agent_id, 0) + 1

        return counts

    @staticmethod
    def _load_simulation_requirement(project_id: str) -> str:
        project = JsonStore.load(JsonStore.project_path(project_id, "project.json"))
        return str(project.get("simulation_requirement", "")).strip()

    @staticmethod
    def _agents_dir(project_id: str) -> Path:
        path = PROJECTS_DIR / project_id / "agents"
        JsonStore.ensure_dir(path)
        return path

    @staticmethod
    def _shorten(text: str, max_chars: int) -> str:
        value = text.strip()
        if len(value) <= max_chars:
            return value
        if max_chars <= 3:
            return value[:max_chars]
        return value[: max_chars - 3].rstrip() + "..."
