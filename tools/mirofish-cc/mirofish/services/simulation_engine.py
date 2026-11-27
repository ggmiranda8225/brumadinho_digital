from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mirofish.config import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_ROUNDS,
    PROJECTS_DIR,
    REDDIT_ACTIONS,
    TWITTER_ACTIONS,
)
from mirofish.models.agent import AgentProfile
from mirofish.models.graph import GraphEdge, GraphNode, KnowledgeGraph
from mirofish.models.platform import RedditPlatform, SocialPlatform, TwitterPlatform
from mirofish.models.project import Project, ProjectStatus
from mirofish.models.simulation import (
    AgentAction,
    RoundSummary,
    SimulationState,
    SimulationStatus,
)
from mirofish.store.json_store import JsonStore


class SimulationEngine:
    @staticmethod
    def init_simulation(
        project_id: str,
        total_rounds: Optional[int] = None,
        batch_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Initialize a new simulation.
        1. Load all agent profiles from agents/ directory
        2. Create TwitterPlatform and RedditPlatform instances
        3. Register all agents on both platforms
        4. Set up initial follow relationships based on knowledge graph edges
        5. Create and save SimulationState + platform states
        6. Update project status to SIMULATION_READY
        """
        project_path = JsonStore.project_path(project_id, "project.json")
        project_payload = JsonStore.load(project_path)
        if not project_payload:
            raise ValueError(f"Project not found: {project_id}")

        total_rounds = int(total_rounds or DEFAULT_MAX_ROUNDS)
        batch_size = int(batch_size or DEFAULT_BATCH_SIZE)
        if total_rounds <= 0:
            raise ValueError("total_rounds must be > 0")
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")

        agents = SimulationEngine._load_all_agents(project_id)
        if not agents:
            raise ValueError(
                "No agent profiles found. Generate personas before simulation."
            )

        twitter = SimulationEngine._create_platform_instance(TwitterPlatform, "twitter")
        reddit = SimulationEngine._create_platform_instance(RedditPlatform, "reddit")

        for profile in agents:
            SimulationEngine._register_agent_on_platform(twitter, profile)
            SimulationEngine._register_agent_on_platform(reddit, profile)

        follows = SimulationEngine._build_initial_follows(project_id, twitter, reddit)

        simulation_dir = SimulationEngine._simulation_dir(project_id)
        JsonStore.ensure_dir(simulation_dir)

        state = SimulationState(
            simulation_id=str(uuid.uuid4()),
            project_id=project_id,
            status=SimulationStatus.INITIALIZED,
            current_round=1,
            total_rounds=total_rounds,
            batch_size=batch_size,
            round_summaries=[],
            started_at=datetime.now(timezone.utc),
            completed_at=None,
        )
        JsonStore.save(simulation_dir / "state.json", state.to_dict())
        SimulationEngine._save_platforms(project_id, twitter, reddit)

        project = Project.from_dict(project_payload)
        project.update_status(ProjectStatus.SIMULATION_READY)
        JsonStore.save(project_path, project.to_dict())

        return {
            "simulation_id": state.simulation_id,
            "total_rounds": state.total_rounds,
            "batch_size": state.batch_size,
            "agent_count": len(agents),
            "twitter_follows": follows.get("twitter_follows", 0),
            "reddit_follows": follows.get("reddit_follows", 0),
        }

    @staticmethod
    def get_seed_post_context(project_id: str) -> Dict[str, Any]:
        """Get context for generating seed posts."""
        project_payload = JsonStore.load(
            JsonStore.project_path(project_id, "project.json")
        )
        simulation_requirement = str(
            project_payload.get("simulation_requirement", "")
        ).strip()

        agent_summaries: List[Dict[str, str]] = []
        agents = SimulationEngine._load_all_agents(project_id)
        for profile in agents:
            agent_summaries.append(
                {
                    "agent_id": profile.agent_id,
                    "name": profile.name,
                    "persona_summary": SimulationEngine._truncate(profile.persona, 180),
                }
            )

        suggested_seed_count = 2 if len(agent_summaries) < 8 else 3

        return {
            "simulation_requirement": simulation_requirement,
            "agent_summaries": agent_summaries,
            "platforms": ["twitter", "reddit"],
            "suggested_seed_count": suggested_seed_count,
        }

    @staticmethod
    def apply_seed_posts(project_id: str, seed_posts: List[Dict]) -> Dict[str, Any]:
        """Apply seed posts to platforms.

        Input: [{agent_id, platform, content}]
        Returns: {twitter_posts, reddit_posts}
        """
        if not isinstance(seed_posts, list):
            raise ValueError("seed_posts must be a list")

        twitter, reddit = SimulationEngine._load_platforms(project_id)

        twitter_posts = 0
        reddit_posts = 0
        for post in seed_posts:
            agent_id = str(post.get("agent_id", "")).strip()
            platform = str(post.get("platform", "")).strip().lower()
            content = str(post.get("content", "")).strip()

            if not agent_id or not content:
                continue

            if platform == "twitter":
                ok, _ = SimulationEngine._execute_platform_action(
                    twitter,
                    agent_id=agent_id,
                    action_type="CREATE_POST",
                    args={"content": content},
                )
                if ok:
                    twitter_posts += 1
            elif platform == "reddit":
                ok, _ = SimulationEngine._execute_platform_action(
                    reddit,
                    agent_id=agent_id,
                    action_type="CREATE_POST",
                    args={"content": content},
                )
                if ok:
                    reddit_posts += 1

        SimulationEngine._save_platforms(project_id, twitter, reddit)
        return {"twitter_posts": twitter_posts, "reddit_posts": reddit_posts}

    @staticmethod
    def get_round_data(project_id: str) -> Dict[str, Any]:
        """Prepare data for the next simulation round."""
        state = SimulationEngine._load_state(project_id)
        agents = SimulationEngine._load_all_agents(project_id)
        twitter, reddit = SimulationEngine._load_platforms(project_id)

        simulation_requirement = SimulationEngine._load_simulation_requirement(
            project_id
        )

        twitter_batches = SimulationEngine._build_platform_batches(
            project_id=project_id,
            state=state,
            platform_name="twitter",
            platform=twitter,
            agents=agents,
            action_space=TWITTER_ACTIONS,
        )
        reddit_batches = SimulationEngine._build_platform_batches(
            project_id=project_id,
            state=state,
            platform_name="reddit",
            platform=reddit,
            agents=agents,
            action_space=REDDIT_ACTIONS,
        )

        return {
            "round": state.current_round,
            "total_rounds": state.total_rounds,
            "simulation_requirement": simulation_requirement,
            "twitter_batches": twitter_batches,
            "reddit_batches": reddit_batches,
        }

    @staticmethod
    def apply_actions(
        project_id: str,
        round_num: int,
        actions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Execute decided actions on platforms and update round state."""
        state = SimulationEngine._load_state(project_id)
        if state.status == SimulationStatus.COMPLETED:
            raise ValueError("Simulation is already completed")
        if state.status == SimulationStatus.PAUSED:
            raise ValueError("Simulation is paused. Resume before applying actions.")

        round_num = int(round_num)
        if round_num <= 0:
            raise ValueError("round_num must be > 0")

        twitter, reddit = SimulationEngine._load_platforms(project_id)
        profile_by_id = {
            profile.agent_id: profile
            for profile in SimulationEngine._load_all_agents(project_id)
        }

        twitter_actions = 0
        reddit_actions = 0

        for raw_action in actions:
            platform_name = str(raw_action.get("platform", "")).strip().lower()
            agent_id = str(raw_action.get("agent_id", "")).strip()
            action_type = str(raw_action.get("action", "")).strip().upper()
            args = dict(raw_action.get("args", {}) or {})

            if not agent_id or not action_type:
                continue

            platform_name = SimulationEngine._resolve_action_platform(
                platform_name, action_type
            )
            platform = twitter if platform_name == "twitter" else reddit

            ok, result = SimulationEngine._execute_platform_action(
                platform,
                agent_id=agent_id,
                action_type=action_type,
                args=args,
            )

            if action_type != "DO_NOTHING":
                if platform_name == "twitter":
                    twitter_actions += 1
                else:
                    reddit_actions += 1

            profile = profile_by_id.get(agent_id)
            action_record = AgentAction(
                round_num=round_num,
                timestamp=datetime.now(timezone.utc),
                platform=platform_name,
                agent_id=agent_id,
                agent_name=profile.name if profile else agent_id,
                action_type=action_type,
                action_args=args,
                result=SimulationEngine._safe_json_string(result),
                success=ok,
            )
            JsonStore.append_jsonl(
                JsonStore.project_path(project_id, "simulation", "actions.jsonl"),
                action_record.to_dict(),
            )

        SimulationEngine._advance_platform_round(twitter)
        SimulationEngine._advance_platform_round(reddit)

        state.round_summaries.append(
            RoundSummary(
                round_num=round_num,
                twitter_actions=twitter_actions,
                reddit_actions=reddit_actions,
                timestamp=datetime.now(timezone.utc),
            )
        )

        is_final_round = round_num >= state.total_rounds
        if is_final_round:
            state.current_round = state.total_rounds
            state.status = SimulationStatus.COMPLETED
            state.completed_at = datetime.now(timezone.utc)
        else:
            state.current_round = round_num + 1
            state.status = SimulationStatus.RUNNING

        SimulationEngine._save_state(project_id, state)
        SimulationEngine._save_platforms(project_id, twitter, reddit)
        SimulationEngine._update_project_after_round(project_id, state)

        return {
            "round_num": round_num,
            "twitter_actions": twitter_actions,
            "reddit_actions": reddit_actions,
            "is_final_round": is_final_round,
            "status": state.status.value,
        }

    @staticmethod
    def update_agent_memories(
        project_id: str,
        round_num: int,
        memories: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Save memory updates for agents after a round.

        Input: [{agent_id, memory}]
        Append to agents/{agent_id}_memories.jsonl
        """
        updated_count = 0
        now = datetime.now(timezone.utc).isoformat()

        for item in memories:
            agent_id = str(item.get("agent_id", "")).strip()
            memory = str(item.get("memory", "")).strip()
            if not agent_id or not memory:
                continue

            record = {
                "round": int(round_num),
                "timestamp": now,
                "memory": memory,
            }
            JsonStore.append_jsonl(
                JsonStore.project_path(
                    project_id, "agents", f"{agent_id}_memories.jsonl"
                ),
                record,
            )
            updated_count += 1

        return {"updated_count": updated_count}

    @staticmethod
    def get_status(project_id: str) -> Dict[str, Any]:
        """Get simulation progress and platform stats."""
        state = SimulationEngine._load_state(project_id)
        twitter, reddit = SimulationEngine._load_platforms(project_id)

        twitter_stats = SimulationEngine._extract_platform_stats(twitter, "twitter")
        reddit_stats = SimulationEngine._extract_platform_stats(reddit, "reddit")

        agents_count = len(SimulationEngine._load_all_agents(project_id))

        now = datetime.now(timezone.utc)
        elapsed_seconds = int((now - state.started_at).total_seconds())
        progress_pct = SimulationEngine._progress_percent(state)

        return {
            "status": state.status.value,
            "current_round": state.current_round,
            "total_rounds": state.total_rounds,
            "progress_pct": progress_pct,
            "twitter_stats": twitter_stats,
            "reddit_stats": reddit_stats,
            "agents_count": agents_count,
            "started_at": state.started_at.isoformat(),
            "elapsed_time": elapsed_seconds,
        }

    @staticmethod
    def get_agent_context(project_id: str, agent_name: str) -> Dict[str, Any]:
        """Get full context for an agent interview."""
        profile = SimulationEngine._find_agent_profile(project_id, agent_name)
        if profile is None:
            raise ValueError(f"Agent not found: {agent_name}")

        action_history_records = JsonStore.read_jsonl(
            JsonStore.project_path(project_id, "simulation", "actions.jsonl")
        )
        action_history: List[Dict[str, Any]] = []
        posts_created: List[Dict[str, Any]] = []

        for row in action_history_records:
            if str(row.get("agent_id", "")).strip() != profile.agent_id:
                continue
            action_history.append(
                {
                    "round": int(row.get("round_num", 0)),
                    "platform": str(row.get("platform", "")),
                    "action": str(row.get("action_type", "")),
                    "content": SimulationEngine._extract_content_from_args(
                        row.get("action_args", {})
                    ),
                }
            )

            action_type = str(row.get("action_type", "")).upper()
            if action_type in {"CREATE_POST", "QUOTE_POST", "CREATE_COMMENT"}:
                posts_created.append(
                    {
                        "round": int(row.get("round_num", 0)),
                        "platform": str(row.get("platform", "")),
                        "content": SimulationEngine._extract_content_from_args(
                            row.get("action_args", {})
                        ),
                        "engagement": {},
                    }
                )

        memories = JsonStore.read_jsonl(
            JsonStore.project_path(
                project_id, "agents", f"{profile.agent_id}_memories.jsonl"
            )
        )

        graph = SimulationEngine._load_graph(project_id)
        graph_facts = SimulationEngine._collect_graph_facts(
            graph, profile.source_entity_uuid
        )

        # Fill engagement from current platform snapshots, best-effort.
        twitter, reddit = SimulationEngine._load_platforms(project_id)
        created_posts = SimulationEngine._collect_agent_posts_with_engagement(
            profile.agent_id,
            twitter=twitter,
            reddit=reddit,
        )
        if created_posts:
            posts_created = created_posts

        return {
            "profile": profile.to_dict(),
            "action_history": action_history,
            "posts_created": posts_created,
            "memories": [
                {
                    "round": int(item.get("round", 0)),
                    "memory": str(item.get("memory", "")),
                }
                for item in memories
            ],
            "graph_facts": graph_facts,
        }

    @staticmethod
    def get_round_summary(project_id: str, round_num: int) -> Dict[str, Any]:
        """Get summary of what happened in a specific round."""
        round_num = int(round_num)
        actions_log = JsonStore.read_jsonl(
            JsonStore.project_path(project_id, "simulation", "actions.jsonl")
        )

        actions: List[Dict[str, Any]] = []
        new_posts: List[Dict[str, Any]] = []

        for row in actions_log:
            if int(row.get("round_num", 0)) != round_num:
                continue
            action_type = str(row.get("action_type", "")).upper()
            action_item = {
                "agent_name": str(row.get("agent_name", "")),
                "platform": str(row.get("platform", "")),
                "action": action_type,
                "content": SimulationEngine._extract_content_from_args(
                    row.get("action_args", {})
                ),
            }
            actions.append(action_item)

            if action_type in {"CREATE_POST", "QUOTE_POST"}:
                action_args = dict(row.get("action_args", {}) or {})
                new_posts.append(
                    {
                        "post_id": str(
                            action_args.get("post_id")
                            or action_args.get("target_post_id")
                            or ""
                        ),
                        "author": str(row.get("agent_name", "")),
                        "content": str(action_args.get("content", "")).strip(),
                        "platform": str(row.get("platform", "")),
                    }
                )

        twitter, reddit = SimulationEngine._load_platforms(project_id)
        engagement = SimulationEngine._collect_global_engagement(twitter, reddit)

        return {
            "round_num": round_num,
            "actions": actions,
            "new_posts": new_posts,
            "engagement": engagement,
        }

    @staticmethod
    def pause_simulation(project_id: str) -> Dict[str, Any]:
        """Pause a running simulation. Sets status to PAUSED."""
        state = SimulationEngine._load_state(project_id)
        if state.status == SimulationStatus.COMPLETED:
            raise ValueError("Cannot pause a completed simulation")

        state.status = SimulationStatus.PAUSED
        SimulationEngine._save_state(project_id, state)
        return {
            "status": state.status.value,
            "current_round": state.current_round,
            "total_rounds": state.total_rounds,
        }

    @staticmethod
    def resume_simulation(project_id: str) -> Dict[str, Any]:
        """Resume a paused simulation. Sets status to RUNNING."""
        state = SimulationEngine._load_state(project_id)
        if state.status == SimulationStatus.COMPLETED:
            raise ValueError("Cannot resume a completed simulation")

        state.status = SimulationStatus.RUNNING
        SimulationEngine._save_state(project_id, state)
        return {
            "status": state.status.value,
            "current_round": state.current_round,
            "total_rounds": state.total_rounds,
        }

    @staticmethod
    def _load_platforms(project_id: str) -> tuple[Any, Any]:
        """Load Twitter and Reddit platform states from JSON."""
        simulation_dir = SimulationEngine._simulation_dir(project_id)
        twitter_path = simulation_dir / "twitter_platform.json"
        reddit_path = simulation_dir / "reddit_platform.json"

        twitter_payload = JsonStore.load(twitter_path)
        reddit_payload = JsonStore.load(reddit_path)

        twitter = SimulationEngine._deserialize_platform(
            TwitterPlatform, "twitter", twitter_payload
        )
        reddit = SimulationEngine._deserialize_platform(
            RedditPlatform, "reddit", reddit_payload
        )

        return twitter, reddit

    @staticmethod
    def _save_platforms(
        project_id: str,
        twitter: Any,
        reddit: Any,
    ) -> None:
        """Save both platform states to JSON."""
        simulation_dir = SimulationEngine._simulation_dir(project_id)
        JsonStore.ensure_dir(simulation_dir)

        JsonStore.save(
            simulation_dir / "twitter_platform.json",
            SimulationEngine._serialize_platform(twitter),
        )
        JsonStore.save(
            simulation_dir / "reddit_platform.json",
            SimulationEngine._serialize_platform(reddit),
        )

    @staticmethod
    def _get_recent_actions(
        project_id: str, agent_id: str, limit: int = 3
    ) -> List[str]:
        """Get agent's recent actions from JSONL log."""
        records = JsonStore.read_jsonl(
            JsonStore.project_path(project_id, "simulation", "actions.jsonl")
        )

        matched: List[str] = []
        for row in reversed(records):
            if str(row.get("agent_id", "")).strip() != agent_id:
                continue

            action_type = str(row.get("action_type", "")).strip().upper()
            platform = str(row.get("platform", "")).strip().lower()
            content = SimulationEngine._extract_content_from_args(
                row.get("action_args", {})
            )
            if content:
                matched.append(
                    f"{platform}:{action_type} - {SimulationEngine._truncate(content, 72)}"
                )
            else:
                matched.append(f"{platform}:{action_type}")

            if len(matched) >= limit:
                break

        return matched

    @staticmethod
    def _build_initial_follows(
        project_id: str,
        twitter: Any,
        reddit: Any,
    ) -> Dict[str, int]:
        """Create follow relationships from knowledge graph edges."""
        graph = SimulationEngine._load_graph(project_id)
        if not graph.edges:
            return {"twitter_follows": 0, "reddit_follows": 0}

        agents = SimulationEngine._load_all_agents(project_id)
        by_entity_uuid: Dict[str, List[AgentProfile]] = {}
        for profile in agents:
            key = profile.source_entity_uuid.strip()
            if not key:
                continue
            by_entity_uuid.setdefault(key, []).append(profile)

        twitter_count = 0
        reddit_count = 0
        seen_pairs: set[tuple[str, str]] = set()

        for edge in graph.edges:
            source_agents = by_entity_uuid.get(edge.source_node_uuid, [])
            target_agents = by_entity_uuid.get(edge.target_node_uuid, [])
            for source_profile in source_agents:
                for target_profile in target_agents:
                    if source_profile.agent_id == target_profile.agent_id:
                        continue

                    forward = (source_profile.agent_id, target_profile.agent_id)
                    reverse = (target_profile.agent_id, source_profile.agent_id)
                    for follower_id, followee_id in (forward, reverse):
                        pair_key = (follower_id, followee_id)
                        if pair_key in seen_pairs:
                            continue
                        seen_pairs.add(pair_key)

                        if SimulationEngine._follow_on_platform(
                            twitter, follower_id, followee_id
                        ):
                            twitter_count += 1
                        if SimulationEngine._follow_on_platform(
                            reddit, follower_id, followee_id
                        ):
                            reddit_count += 1

        return {
            "twitter_follows": twitter_count,
            "reddit_follows": reddit_count,
        }

    @staticmethod
    def _build_platform_batches(
        project_id: str,
        state: SimulationState,
        platform_name: str,
        platform: SocialPlatform,
        agents: List[AgentProfile],
        action_space: List[str],
    ) -> List[Dict[str, Any]]:
        batches: List[Dict[str, Any]] = []
        chunk_size = state.batch_size

        for batch_index, start in enumerate(range(0, len(agents), chunk_size)):
            chunk = agents[start : start + chunk_size]
            batch_agents: List[Dict[str, Any]] = []

            for profile in chunk:
                feed_raw = SimulationEngine._get_platform_feed(
                    platform, profile.agent_id, limit=5
                )
                feed = [
                    SimulationEngine._summarize_feed_item(item) for item in feed_raw[:5]
                ]

                batch_agents.append(
                    {
                        "agent_id": profile.agent_id,
                        "name": profile.name,
                        "profession": profile.profession,
                        "persona_summary": SimulationEngine._truncate(
                            profile.persona, 200
                        ),
                        "recent_actions": SimulationEngine._get_recent_actions(
                            project_id,
                            profile.agent_id,
                            limit=3,
                        ),
                        "feed": feed,
                        "available_actions": list(action_space),
                    }
                )

            batches.append(
                {
                    "batch_index": batch_index,
                    "platform": platform_name,
                    "agents": batch_agents,
                }
            )

        return batches

    @staticmethod
    def _create_platform_instance(
        platform_cls: type[SocialPlatform],
        platform_name: str,
    ) -> SocialPlatform:
        constructors = [
            lambda: platform_cls(),
            lambda: platform_cls(platform_name),
            lambda: platform_cls(name=platform_name),
            lambda: platform_cls(platform=platform_name),
        ]
        for constructor in constructors:
            try:
                instance = constructor()
                return instance
            except TypeError:
                continue
        raise ValueError(f"Could not initialize platform class for {platform_name}")

    @staticmethod
    def _deserialize_platform(
        platform_cls: type[SocialPlatform],
        platform_name: str,
        payload: Dict[str, Any],
    ) -> SocialPlatform:
        if payload:
            if hasattr(platform_cls, "from_dict"):
                return platform_cls.from_dict(payload)
            if hasattr(platform_cls, "model_validate"):
                return platform_cls.model_validate(payload)

            instance = SimulationEngine._create_platform_instance(
                platform_cls, platform_name
            )
            if hasattr(instance, "load_state"):
                instance.load_state(payload)
                return instance
            if hasattr(instance, "from_state"):
                return instance.from_state(payload)
            if hasattr(instance, "__dict__"):
                for key, value in payload.items():
                    setattr(instance, key, value)
            return instance

        return SimulationEngine._create_platform_instance(platform_cls, platform_name)

    @staticmethod
    def _serialize_platform(platform: SocialPlatform) -> Dict[str, Any]:
        if hasattr(platform, "to_dict"):
            data = platform.to_dict()
            if isinstance(data, dict):
                return data

        if hasattr(platform, "model_dump"):
            data = platform.model_dump()
            if isinstance(data, dict):
                return data

        if hasattr(platform, "dump_state"):
            data = platform.dump_state()
            if isinstance(data, dict):
                return data

        if hasattr(platform, "__dict__"):
            output: Dict[str, Any] = {}
            for key, value in platform.__dict__.items():
                output[key] = SimulationEngine._to_jsonable(value)
            return output

        return {}

    @staticmethod
    def _register_agent_on_platform(
        platform: SocialPlatform, profile: AgentProfile
    ) -> None:
        register_methods = [
            "register_agent",
            "add_agent",
            "register_user",
            "create_user",
            "ensure_user",
        ]

        payload = {
            "agent_id": profile.agent_id,
            "name": profile.name,
            "bio": profile.bio,
            "profession": profile.profession,
            "platform_profiles": profile.platform_profiles,
        }

        for method_name in register_methods:
            method = getattr(platform, method_name, None)
            if method is None:
                continue

            calls = [
                lambda: method(payload),
                lambda: method(profile.agent_id, profile.name),
                lambda: method(
                    agent_id=profile.agent_id, name=profile.name, profile=payload
                ),
                lambda: method(agent_id=profile.agent_id, profile=payload),
            ]
            for call in calls:
                try:
                    call()
                    return
                except TypeError:
                    continue

        # Some platform implementations may not require explicit registration.

    @staticmethod
    def _follow_on_platform(
        platform: SocialPlatform, follower_id: str, target_id: str
    ) -> bool:
        follow_methods = ["follow", "add_follow", "follow_user"]
        for method_name in follow_methods:
            method = getattr(platform, method_name, None)
            if method is None:
                continue

            calls = [
                lambda: method(follower_id, target_id),
                lambda: method(follower_id=follower_id, target_id=target_id),
                lambda: method(source_user_id=follower_id, target_user_id=target_id),
            ]
            for call in calls:
                try:
                    call()
                    return True
                except TypeError:
                    continue

        ok, _ = SimulationEngine._execute_platform_action(
            platform,
            agent_id=follower_id,
            action_type="FOLLOW",
            args={"target_user_id": target_id},
        )
        return ok

    @staticmethod
    def _execute_platform_action(
        platform: SocialPlatform,
        agent_id: str,
        action_type: str,
        args: Dict[str, Any],
    ) -> Tuple[bool, Any]:
        methods = ["execute_action", "apply_action", "act"]
        for method_name in methods:
            method = getattr(platform, method_name, None)
            if method is None:
                continue

            calls = [
                lambda: method(agent_id, action_type, args),
                lambda: method(agent_id=agent_id, action_type=action_type, args=args),
                lambda: method(agent_id=agent_id, action=action_type, args=args),
                lambda: method(user_id=agent_id, action_type=action_type, payload=args),
            ]

            for call in calls:
                try:
                    result = call()
                    if isinstance(result, tuple) and len(result) == 2:
                        return bool(result[0]), result[1]
                    return True, result
                except TypeError:
                    continue
                except Exception as exc:  # noqa: BLE001
                    return False, str(exc)

        return False, f"No action method found for {action_type}"

    @staticmethod
    def _advance_platform_round(platform: SocialPlatform) -> None:
        methods = ["advance_round", "next_round", "increment_round", "tick"]
        for method_name in methods:
            method = getattr(platform, method_name, None)
            if method is None:
                continue
            try:
                method()
                return
            except TypeError:
                continue

    @staticmethod
    def _get_platform_feed(
        platform: SocialPlatform, agent_id: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        methods = ["get_feed", "fetch_feed", "timeline_for", "get_timeline", "feed_for"]
        for method_name in methods:
            method = getattr(platform, method_name, None)
            if method is None:
                continue

            calls = [
                lambda: method(agent_id, limit=limit),
                lambda: method(agent_id),
                lambda: method(agent_id=agent_id, limit=limit),
                lambda: method(user_id=agent_id, limit=limit),
            ]
            for call in calls:
                try:
                    result = call()
                    if isinstance(result, list):
                        return [
                            SimulationEngine._to_jsonable_dict(item) for item in result
                        ]
                except TypeError:
                    continue
                except Exception:
                    return []

        return []

    @staticmethod
    def _summarize_feed_item(item: Dict[str, Any]) -> Dict[str, Any]:
        content = str(item.get("content", "")).strip()
        return {
            "post_id": str(item.get("post_id") or item.get("id") or ""),
            "author": str(
                item.get("author") or item.get("author_name") or item.get("user") or ""
            ),
            "content": SimulationEngine._truncate(content, 220),
            "created_at": item.get("created_at") or item.get("timestamp"),
            "like_count": int(item.get("like_count", item.get("likes", 0)) or 0),
            "repost_count": int(item.get("repost_count", item.get("reposts", 0)) or 0),
            "comment_count": int(
                item.get("comment_count", item.get("comments", 0)) or 0
            ),
        }

    @staticmethod
    def _extract_platform_stats(
        platform: SocialPlatform, platform_name: str
    ) -> Dict[str, int]:
        if hasattr(platform, "get_stats"):
            try:
                stats = platform.get_stats()
                if isinstance(stats, dict):
                    total_posts = int(
                        stats.get("total_posts", stats.get("posts", 0)) or 0
                    )
                    total_actions = int(
                        stats.get("total_actions", stats.get("actions", 0)) or 0
                    )
                    total_likes = int(
                        stats.get("total_likes", stats.get("likes", 0)) or 0
                    )
                    total_comments = int(
                        stats.get("total_comments", stats.get("comments", 0)) or 0
                    )
                    if platform_name == "twitter":
                        return {
                            "total_posts": total_posts,
                            "total_likes": total_likes,
                            "total_actions": total_actions,
                        }
                    return {
                        "total_posts": total_posts,
                        "total_comments": total_comments,
                        "total_actions": total_actions,
                    }
            except Exception:  # noqa: BLE001
                pass

        payload = SimulationEngine._serialize_platform(platform)
        posts = SimulationEngine._extract_posts_from_platform_payload(payload)
        total_posts = len(posts)
        total_likes = sum(int(item.get("like_count", 0) or 0) for item in posts)
        total_comments = sum(int(item.get("comment_count", 0) or 0) for item in posts)

        action_count = 0
        for key in ("actions", "action_log", "history"):
            value = payload.get(key)
            if isinstance(value, list):
                action_count = max(action_count, len(value))

        if platform_name == "twitter":
            return {
                "total_posts": total_posts,
                "total_likes": total_likes,
                "total_actions": action_count,
            }

        return {
            "total_posts": total_posts,
            "total_comments": total_comments,
            "total_actions": action_count,
        }

    @staticmethod
    def _extract_posts_from_platform_payload(
        payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        for key in ("posts", "timeline", "feed", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [SimulationEngine._to_jsonable_dict(item) for item in value]
            if isinstance(value, dict):
                return [SimulationEngine._to_jsonable_dict(v) for v in value.values()]
        return []

    @staticmethod
    def _collect_agent_posts_with_engagement(
        agent_id: str,
        twitter: SocialPlatform,
        reddit: SocialPlatform,
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for platform_name, platform in (("twitter", twitter), ("reddit", reddit)):
            payload = SimulationEngine._serialize_platform(platform)
            posts = SimulationEngine._extract_posts_from_platform_payload(payload)
            for post in posts:
                author_id = str(
                    post.get("agent_id")
                    or post.get("author_id")
                    or post.get("user_id")
                    or ""
                )
                if author_id != agent_id:
                    continue
                out.append(
                    {
                        "post_id": str(post.get("post_id") or post.get("id") or ""),
                        "platform": platform_name,
                        "content": str(post.get("content", "")).strip(),
                        "engagement": {
                            "likes": int(
                                post.get("like_count", post.get("likes", 0)) or 0
                            ),
                            "reposts": int(
                                post.get("repost_count", post.get("reposts", 0)) or 0
                            ),
                            "comments": int(
                                post.get("comment_count", post.get("comments", 0)) or 0
                            ),
                        },
                    }
                )
        return out

    @staticmethod
    def _collect_global_engagement(
        twitter: SocialPlatform, reddit: SocialPlatform
    ) -> Dict[str, int]:
        totals = {
            "total_likes": 0,
            "total_reposts": 0,
            "total_comments": 0,
        }
        for platform in (twitter, reddit):
            payload = SimulationEngine._serialize_platform(platform)
            posts = SimulationEngine._extract_posts_from_platform_payload(payload)
            for post in posts:
                totals["total_likes"] += int(
                    post.get("like_count", post.get("likes", 0)) or 0
                )
                totals["total_reposts"] += int(
                    post.get("repost_count", post.get("reposts", 0)) or 0
                )
                totals["total_comments"] += int(
                    post.get("comment_count", post.get("comments", 0)) or 0
                )
        return totals

    @staticmethod
    def _find_agent_profile(project_id: str, agent_name: str) -> Optional[AgentProfile]:
        lookup = agent_name.strip().casefold()
        if not lookup:
            return None

        for profile in SimulationEngine._load_all_agents(project_id):
            if profile.name.strip().casefold() == lookup:
                return profile
            if profile.agent_id.strip().casefold() == lookup:
                return profile

        return None

    @staticmethod
    def _collect_graph_facts(
        graph: KnowledgeGraph, entity_uuid: str
    ) -> List[Dict[str, str]]:
        if not entity_uuid:
            return []

        facts: List[Dict[str, str]] = []
        for edge in graph.get_edges_for_node(entity_uuid):
            source = graph.get_node_by_uuid(edge.source_node_uuid)
            target = graph.get_node_by_uuid(edge.target_node_uuid)
            facts.append(
                {
                    "relationship": edge.name,
                    "fact": edge.fact,
                    "source": source.name if source else edge.source_node_uuid,
                    "target": target.name if target else edge.target_node_uuid,
                }
            )
        return facts

    @staticmethod
    def _resolve_action_platform(platform_hint: str, action_type: str) -> str:
        if platform_hint in {"twitter", "reddit"}:
            return platform_hint

        if action_type in {"REPOST", "QUOTE_POST"}:
            return "twitter"
        if action_type in {
            "DISLIKE_POST",
            "DISLIKE_COMMENT",
            "MUTE",
            "LIKE_COMMENT",
            "CREATE_COMMENT",
        }:
            return "reddit"

        return "twitter"

    @staticmethod
    def _load_state(project_id: str) -> SimulationState:
        state_path = JsonStore.project_path(project_id, "simulation", "state.json")
        payload = JsonStore.load(state_path)
        if not payload:
            raise ValueError("Simulation not initialized. Run init_simulation first.")
        return SimulationState.from_dict(payload)

    @staticmethod
    def _save_state(project_id: str, state: SimulationState) -> None:
        JsonStore.save(
            JsonStore.project_path(project_id, "simulation", "state.json"),
            state.to_dict(),
        )

    @staticmethod
    def _update_project_after_round(project_id: str, state: SimulationState) -> None:
        project_path = JsonStore.project_path(project_id, "project.json")
        payload = JsonStore.load(project_path)
        if not payload:
            return

        project = Project.from_dict(payload)
        if state.status == SimulationStatus.COMPLETED:
            project.update_status(ProjectStatus.SIMULATION_COMPLETE)
        else:
            project.update_status(ProjectStatus.SIMULATION_RUNNING)
        JsonStore.save(project_path, project.to_dict())

    @staticmethod
    def _load_all_agents(project_id: str) -> List[AgentProfile]:
        agents_dir = JsonStore.project_path(project_id, "agents")
        if not agents_dir.exists():
            return []

        profiles: List[AgentProfile] = []
        for path in sorted(agents_dir.glob("*.json")):
            if path.name.endswith("_memories.json"):
                continue
            payload = JsonStore.load(path)
            if not payload:
                continue
            try:
                profiles.append(AgentProfile.from_dict(payload))
            except Exception:  # noqa: BLE001
                continue

        return profiles

    @staticmethod
    def _load_graph(project_id: str) -> KnowledgeGraph:
        path = JsonStore.project_path(project_id, "graph", "graph.json")
        payload = JsonStore.load(path)

        if not payload:
            return KnowledgeGraph(graph_id=f"{project_id}-graph")

        # Handle both dict-node and list-node payloads.
        nodes_raw = payload.get("nodes", {})
        if isinstance(nodes_raw, list):
            normalized_nodes = {
                str(item.get("uuid", "")).strip(): item
                for item in nodes_raw
                if str(item.get("uuid", "")).strip()
            }
            payload = dict(payload)
            payload["nodes"] = normalized_nodes

        edges_raw = payload.get("edges", [])
        normalized_edges: List[Dict[str, Any]] = []
        for edge in edges_raw:
            if not isinstance(edge, dict):
                continue
            edge_payload = dict(edge)
            if "source_node_uuid" not in edge_payload:
                edge_payload["source_node_uuid"] = edge_payload.get(
                    "source_uuid"
                ) or edge_payload.get("source")
            if "target_node_uuid" not in edge_payload:
                edge_payload["target_node_uuid"] = edge_payload.get(
                    "target_uuid"
                ) or edge_payload.get("target")
            if "uuid" not in edge_payload:
                edge_payload["uuid"] = str(uuid.uuid4())
            normalized_edges.append(edge_payload)

        payload = dict(payload)
        payload["edges"] = normalized_edges

        try:
            return KnowledgeGraph.from_dict(payload)
        except Exception:  # noqa: BLE001
            graph = KnowledgeGraph(
                graph_id=str(payload.get("graph_id") or f"{project_id}-graph")
            )
            nodes = dict(payload.get("nodes", {}))
            for node_uuid, node_value in nodes.items():
                if isinstance(node_value, dict):
                    node_payload = dict(node_value)
                    node_payload.setdefault("uuid", node_uuid)
                    try:
                        graph.add_node(GraphNode.from_dict(node_payload))
                    except Exception:
                        pass

            edges = payload.get("edges", [])
            for row in edges:
                try:
                    edge = GraphEdge.from_dict(dict(row))
                    graph.edges.append(edge)
                except Exception:
                    continue
            return graph

    @staticmethod
    def _load_simulation_requirement(project_id: str) -> str:
        project_payload = JsonStore.load(
            JsonStore.project_path(project_id, "project.json")
        )
        return str(project_payload.get("simulation_requirement", "")).strip()

    @staticmethod
    def _simulation_dir(project_id: str) -> Path:
        return PROJECTS_DIR / project_id / "simulation"

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        value = text.strip()
        if len(value) <= max_chars:
            return value
        if max_chars <= 3:
            return value[:max_chars]
        return value[: max_chars - 3].rstrip() + "..."

    @staticmethod
    def _to_jsonable(value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, dict):
            return {str(k): SimulationEngine._to_jsonable(v) for k, v in value.items()}
        if isinstance(value, list):
            return [SimulationEngine._to_jsonable(item) for item in value]
        if isinstance(value, tuple):
            return [SimulationEngine._to_jsonable(item) for item in value]
        if isinstance(value, datetime):
            return value.isoformat()
        if hasattr(value, "to_dict"):
            try:
                data = value.to_dict()
                if isinstance(data, dict):
                    return SimulationEngine._to_jsonable(data)
            except Exception:  # noqa: BLE001
                pass
        if hasattr(value, "model_dump"):
            try:
                return SimulationEngine._to_jsonable(value.model_dump())
            except Exception:  # noqa: BLE001
                pass
        if hasattr(value, "__dict__"):
            return SimulationEngine._to_jsonable(value.__dict__)
        return str(value)

    @staticmethod
    def _to_jsonable_dict(value: Any) -> Dict[str, Any]:
        result = SimulationEngine._to_jsonable(value)
        if isinstance(result, dict):
            return result
        return {"value": result}

    @staticmethod
    def _extract_content_from_args(action_args: Any) -> str:
        if not isinstance(action_args, dict):
            return ""
        return str(action_args.get("content", "")).strip()

    @staticmethod
    def _safe_json_string(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        try:
            import json

            return json.dumps(value, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            return str(value)

    @staticmethod
    def _progress_percent(state: SimulationState) -> float:
        if state.total_rounds <= 0:
            return 0.0
        if state.status == SimulationStatus.COMPLETED:
            return 100.0

        completed = max(0, min(state.total_rounds, state.current_round - 1))
        pct = (completed / state.total_rounds) * 100
        return round(pct, 2)
