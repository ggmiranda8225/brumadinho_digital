from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click

from mirofish.config import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_MAX_ROUNDS,
    PROJECTS_DIR,
)
from mirofish.models.platform import RedditPlatform, SocialPlatform, TwitterPlatform
from mirofish.models.project import Project, ProjectStatus
from mirofish.models.simulation import SimulationState, SimulationStatus
from mirofish.prompts.ontology import (
    ENTITY_EXTRACTION_PROMPT,
    ONTOLOGY_SYSTEM_PROMPT,
    ONTOLOGY_USER_PROMPT_TEMPLATE,
)
from mirofish.prompts.simulation import (
    AGENT_DECISION_SYSTEM_PROMPT,
    build_batch_agent_prompt,
    build_seed_post_prompt,
)
from mirofish.services.graph_builder import GraphBuilder
from mirofish.services.graph_search import GraphSearchService
from mirofish.services.persona_generator import PersonaGenerator
from mirofish.services.seed_processor import SeedProcessor
from mirofish.store.json_store import JsonStore


def _emit(payload: dict[str, Any]) -> None:
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


def _error(message: str) -> None:
    _emit({"error": message})


def _run(handler: Any) -> None:
    try:
        result = handler()
        _emit(result if isinstance(result, dict) else {"result": result})
    except Exception as exc:  # noqa: BLE001
        _error(str(exc))


def _project_path(project_id: str) -> Path:
    return JsonStore.project_path(project_id)


def _load_project(project_id: str) -> Project:
    payload = JsonStore.load(JsonStore.project_path(project_id, "project.json"))
    if not payload:
        raise ValueError(f"Project not found: {project_id}")
    return Project.from_dict(payload)


def _save_project(project: Project) -> None:
    project.updated_at = datetime.now(timezone.utc)
    JsonStore.save(
        JsonStore.project_path(project.project_id, "project.json"), project.to_dict()
    )


def _set_project_status(project_id: str, status: ProjectStatus) -> None:
    project = _load_project(project_id)
    project.update_status(status)
    _save_project(project)


def _parse_json_string(raw: str, label: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON for {label}: {exc}") from exc


def _sim_dir(project_id: str) -> Path:
    path = JsonStore.project_path(project_id, "simulation")
    JsonStore.ensure_dir(path)
    return path


def _load_sim_state(project_id: str) -> SimulationState:
    payload = JsonStore.load(
        JsonStore.project_path(project_id, "simulation", "state.json")
    )
    if not payload:
        raise ValueError(f"Simulation not initialized for project: {project_id}")
    return SimulationState.from_dict(payload)


def _save_sim_state(state: SimulationState) -> None:
    JsonStore.save(
        JsonStore.project_path(state.project_id, "simulation", "state.json"),
        state.to_dict(),
    )


def _load_platform(project_id: str, platform: str) -> SocialPlatform:
    path = JsonStore.project_path(project_id, "simulation", f"{platform}.json")
    payload = JsonStore.load(path)
    if payload:
        return SocialPlatform.from_dict(payload)
    return TwitterPlatform() if platform == "twitter" else RedditPlatform()


def _save_platform(project_id: str, platform: str, instance: SocialPlatform) -> None:
    JsonStore.save(
        JsonStore.project_path(project_id, "simulation", f"{platform}.json"),
        instance.to_dict(),
    )


def _load_outline(project_id: str) -> dict[str, Any]:
    return JsonStore.load(JsonStore.project_path(project_id, "report", "outline.json"))


@click.group()
@click.version_option(version="0.1.0")
def cli() -> None:
    """MiroFish-CC: Multi-agent swarm intelligence prediction engine for Claude Code."""


# ── Project Management ──
@cli.group()
def project() -> None:
    """Manage prediction projects."""


@project.command("create")
@click.argument("name")
@click.option("--description", "-d", default="", help="Project description")
@click.option(
    "--requirement", "-r", required=True, help="Prediction requirement/question"
)
def project_create(name: str, description: str, requirement: str) -> None:
    """Create a new prediction project."""

    def _handler() -> dict[str, Any]:
        project_id = f"proj_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        project_obj = Project(
            project_id=project_id,
            name=name.strip(),
            description=description.strip(),
            simulation_requirement=requirement.strip(),
        )
        base = _project_path(project_id)
        for folder in ["seed", "graph", "agents", "simulation", "report", "chat"]:
            JsonStore.ensure_dir(base / folder)
        _save_project(project_obj)
        return {
            "project_id": project_id,
            "name": project_obj.name,
            "status": project_obj.status.value,
        }

    _run(_handler)


@project.command("status")
@click.argument("project_id")
def project_status(project_id: str) -> None:
    """Show project status and progress."""

    def _handler() -> dict[str, Any]:
        project_obj = _load_project(project_id)
        seed_meta = SeedProcessor.get_stats(project_id)
        graph_stats = GraphBuilder.get_stats(project_id)
        persona_status_data = PersonaGenerator.get_status(project_id)
        report_status_data = report_status_handler(project_id)
        sim_status_data = sim_status_handler(project_id)
        return {
            "project": project_obj.to_dict(),
            "seed": seed_meta,
            "graph": graph_stats,
            "personas": persona_status_data,
            "simulation": sim_status_data,
            "report": report_status_data,
        }

    _run(_handler)


@project.command("list")
def project_list() -> None:
    """List all projects."""

    def _handler() -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        if PROJECTS_DIR.exists():
            for path in sorted(PROJECTS_DIR.glob("*/project.json")):
                data = JsonStore.load(path)
                if data:
                    items.append(data)
        return {"projects": items, "count": len(items)}

    _run(_handler)


# ── Seed Processing ──
@cli.group()
def seed() -> None:
    """Process seed materials."""


@seed.command("process")
@click.argument("files", nargs=-1, required=True)
@click.option("--project", "-p", required=True, help="Project ID")
@click.option(
    "--chunk-size", default=DEFAULT_CHUNK_SIZE, help="Chunk size in characters"
)
@click.option(
    "--chunk-overlap", default=DEFAULT_CHUNK_OVERLAP, help="Overlap between chunks"
)
def seed_process(
    files: tuple[str, ...], project: str, chunk_size: int, chunk_overlap: int
) -> None:
    """Process seed files (PDF, MD, TXT) for a project."""

    def _handler() -> dict[str, Any]:
        metadata = SeedProcessor.process(
            project, list(files), chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        proj = _load_project(project)
        proj.seed_files = [str(Path(value)) for value in files]
        proj.chunk_size = chunk_size
        proj.chunk_overlap = chunk_overlap
        proj.update_status(ProjectStatus.SEED_PROCESSED)
        _save_project(proj)
        return metadata

    _run(_handler)


@seed.command("preview")
@click.option("--project", "-p", required=True)
@click.option("--max-chars", default=3000)
def seed_preview(project: str, max_chars: int) -> None:
    """Preview extracted text (for ontology generation)."""

    _run(
        lambda: {
            "project_id": project,
            "preview": SeedProcessor.get_text_preview(project, max_chars=max_chars),
        }
    )


# ── Ontology ──
@cli.group()
def ontology() -> None:
    """Manage ontology."""


@ontology.command("prompt")
@click.option("--project", "-p", required=True)
def ontology_prompt(project: str) -> None:
    """Print the ontology generation prompt with seed text preview."""

    def _handler() -> dict[str, Any]:
        preview = SeedProcessor.get_text_preview(project, max_chars=3000)
        user_prompt = ONTOLOGY_USER_PROMPT_TEMPLATE.format(seed_text_preview=preview)
        return {
            "project_id": project,
            "system_prompt": ONTOLOGY_SYSTEM_PROMPT,
            "user_prompt": user_prompt,
            "seed_preview": preview,
        }

    _run(_handler)


@ontology.command("save")
@click.option("--project", "-p", required=True)
@click.option("--data", required=True, help="Ontology JSON string")
def ontology_save(project: str, data: str) -> None:
    """Save generated ontology."""

    def _handler() -> dict[str, Any]:
        ontology_data = _parse_json_string(data, "ontology")
        if not isinstance(ontology_data, dict):
            raise ValueError("Ontology data must be a JSON object")
        result = GraphBuilder.save_ontology(project, ontology_data)
        _set_project_status(project, ProjectStatus.ONTOLOGY_GENERATED)
        return result

    _run(_handler)


# ── Graph ──
@cli.group()
def graph() -> None:
    """Build knowledge graph."""


@graph.command("get-batch")
@click.option("--project", "-p", required=True)
@click.option("--batch", "-b", type=int, default=0)
@click.option("--batch-size", default=5)
def graph_get_batch(project: str, batch: int, batch_size: int) -> None:
    """Get a batch of text chunks for entity extraction."""

    def _handler() -> dict[str, Any]:
        chunks_data = SeedProcessor.get_chunks(
            project, batch_index=batch, batch_size=batch_size
        )
        ontology_data = JsonStore.load(
            JsonStore.project_path(project, "graph", "ontology.json")
        )
        return {
            **chunks_data,
            "ontology": ontology_data,
            "extraction_system_prompt": ENTITY_EXTRACTION_PROMPT,
            "extraction_user_template": "Use ontology + chunk text and return strict JSON with entities and relationships.",
        }

    _run(_handler)


@graph.command("add")
@click.option("--project", "-p", required=True)
@click.option("--data", required=True, help="Extracted entities/relationships JSON")
def graph_add(project: str, data: str) -> None:
    """Add extracted entities and relationships to graph."""

    def _handler() -> dict[str, Any]:
        payload = _parse_json_string(data, "graph extraction data")
        if not isinstance(payload, dict):
            raise ValueError("Graph extracted data must be a JSON object")
        entities = payload.get("entities", [])
        relationships = payload.get("relationships", [])
        if not isinstance(entities, list) or not isinstance(relationships, list):
            raise ValueError("'entities' and 'relationships' must be arrays")
        return GraphBuilder.add_extracted_data(project, entities, relationships)

    _run(_handler)


@graph.command("finalize")
@click.option("--project", "-p", required=True)
def graph_finalize(project: str) -> None:
    """Finalize graph construction."""

    def _handler() -> dict[str, Any]:
        result = GraphBuilder.finalize(project)
        _set_project_status(project, ProjectStatus.GRAPH_BUILT)
        return result

    _run(_handler)


@graph.command("stats")
@click.option("--project", "-p", required=True)
def graph_stats(project: str) -> None:
    """Show graph statistics."""

    _run(lambda: GraphBuilder.get_stats(project))


# ── Persona ──
@cli.group()
def persona() -> None:
    """Generate agent personas."""


@persona.command("list")
@click.option("--project", "-p", required=True)
def persona_list(project: str) -> None:
    """List entities needing persona generation."""

    _run(lambda: PersonaGenerator.list_entities_for_personas(project))


@persona.command("save")
@click.option("--project", "-p", required=True)
@click.option("--data", required=True, help="Agent profile JSON")
def persona_save(project: str, data: str) -> None:
    """Save a generated agent profile."""

    def _handler() -> dict[str, Any]:
        payload = _parse_json_string(data, "agent profile")
        if not isinstance(payload, dict):
            raise ValueError("Profile data must be a JSON object")
        result = PersonaGenerator.save_profile(project, payload)
        status_data = PersonaGenerator.get_status(project)
        if status_data.get("is_complete"):
            _set_project_status(project, ProjectStatus.PERSONAS_GENERATED)
        return {**result, "persona_status": status_data}

    _run(_handler)


@persona.command("save-batch")
@click.option("--project", "-p", required=True)
@click.option("--data", required=True, help="Array of agent profiles JSON")
def persona_save_batch(project: str, data: str) -> None:
    """Save multiple agent profiles at once."""

    def _handler() -> dict[str, Any]:
        payload = _parse_json_string(data, "agent profiles")
        if not isinstance(payload, list):
            raise ValueError("Batch profile data must be a JSON array")
        result = PersonaGenerator.save_batch_profiles(project, payload)
        status_data = PersonaGenerator.get_status(project)
        if status_data.get("is_complete"):
            _set_project_status(project, ProjectStatus.PERSONAS_GENERATED)
        return {**result, "persona_status": status_data}

    _run(_handler)


@persona.command("status")
@click.option("--project", "-p", required=True)
def persona_status(project: str) -> None:
    """Show persona generation progress."""

    _run(lambda: PersonaGenerator.get_status(project))


# ── Simulation ──
@cli.group()
def sim() -> None:
    """Run multi-agent simulation."""


@sim.command("init")
@click.option("--project", "-p", required=True)
@click.option("--rounds", default=DEFAULT_MAX_ROUNDS, help="Total simulation rounds")
@click.option("--batch-size", default=DEFAULT_BATCH_SIZE, help="Agents per batch (5-8)")
def sim_init(project: str, rounds: int, batch_size: int) -> None:
    """Initialize simulation."""

    def _handler() -> dict[str, Any]:
        profiles = PersonaGenerator.list_profiles(project)
        if not profiles:
            raise ValueError(
                "No personas found. Generate personas before initializing simulation."
            )
        state = SimulationState(
            simulation_id=f"sim_{uuid.uuid4().hex[:8]}",
            project_id=project,
            status=SimulationStatus.INITIALIZED,
            current_round=0,
            total_rounds=max(1, rounds),
            batch_size=max(1, batch_size),
        )
        twitter = TwitterPlatform()
        reddit = RedditPlatform()
        for profile in profiles:
            twitter.register_user(profile["agent_id"], profile["name"])
            reddit.register_user(profile["agent_id"], profile["name"])
        _save_sim_state(state)
        _save_platform(project, "twitter", twitter)
        _save_platform(project, "reddit", reddit)
        JsonStore.save(_sim_dir(project) / "memories.json", {"rounds": {}})
        _set_project_status(project, ProjectStatus.SIMULATION_READY)
        return {"simulation": state.to_dict(), "agent_count": len(profiles)}

    _run(_handler)


@sim.command("seed-context")
@click.option("--project", "-p", required=True)
def sim_seed_context(project: str) -> None:
    """Get context for generating seed posts."""

    def _handler() -> dict[str, Any]:
        state = _load_sim_state(project)
        requirement = _load_project(project).simulation_requirement
        return {
            "simulation": state.to_dict(),
            "system_prompt": AGENT_DECISION_SYSTEM_PROMPT,
            "twitter_seed_prompt": build_seed_post_prompt(
                platform="twitter", simulation_requirement=requirement, count=3
            ),
            "reddit_seed_prompt": build_seed_post_prompt(
                platform="reddit", simulation_requirement=requirement, count=3
            ),
        }

    _run(_handler)


@sim.command("apply-seeds")
@click.option("--project", "-p", required=True)
@click.option("--data", required=True, help="Seed posts JSON")
def sim_apply_seeds(project: str, data: str) -> None:
    """Apply seed posts to platforms."""

    def _handler() -> dict[str, Any]:
        payload = _parse_json_string(data, "seed posts")
        if not isinstance(payload, dict):
            raise ValueError(
                "Seed posts must be JSON object with 'twitter' and/or 'reddit' arrays"
            )
        twitter = _load_platform(project, "twitter")
        reddit = _load_platform(project, "reddit")
        created = {"twitter": 0, "reddit": 0}
        for platform_name, platform_obj in [("twitter", twitter), ("reddit", reddit)]:
            for post in payload.get(platform_name, []):
                if not isinstance(post, dict):
                    continue
                agent_id = str(post.get("agent_id", "")).strip()
                content = str(post.get("content", "")).strip()
                if not agent_id or not content:
                    continue
                platform_obj.create_post(agent_id, content)
                created[platform_name] += 1
        _save_platform(project, "twitter", twitter)
        _save_platform(project, "reddit", reddit)
        return {"created_seed_posts": created}

    _run(_handler)


@sim.command("get-round")
@click.option("--project", "-p", required=True)
def sim_get_round(project: str) -> None:
    """Get next round data for agent decisions."""

    def _handler() -> dict[str, Any]:
        state = _load_sim_state(project)
        if state.current_round >= state.total_rounds:
            return {"completed": True, "simulation": state.to_dict()}
        next_round = state.current_round + 1
        requirement = _load_project(project).simulation_requirement
        profiles = {
            item["agent_id"]: item for item in PersonaGenerator.list_profiles(project)
        }
        batches: list[dict[str, Any]] = []
        for platform_name in ["twitter", "reddit"]:
            platform_obj = _load_platform(project, platform_name)
            agent_ids = sorted(platform_obj.users.keys())
            for index in range(0, len(agent_ids), state.batch_size):
                selected_ids = agent_ids[index : index + state.batch_size]
                agents_payload: list[dict[str, Any]] = []
                for agent_id in selected_ids:
                    user = platform_obj.users[agent_id]
                    profile = profiles.get(agent_id, {})
                    feed = [
                        item.to_dict()
                        for item in platform_obj.get_feed(agent_id, limit=5)
                    ]
                    agents_payload.append(
                        {
                            "agent_id": agent_id,
                            "name": user.agent_name,
                            "profession": profile.get("profession", "Unknown"),
                            "persona_summary": str(profile.get("persona", ""))[:300],
                            "recent_actions": [],
                            "feed": feed,
                            "available_actions": getattr(
                                platform_obj, "AVAILABLE_ACTIONS", []
                            ),
                        }
                    )
                batches.append(
                    {
                        "platform": platform_name,
                        "round": next_round,
                        "batch_index": index // state.batch_size,
                        "agents": agents_payload,
                        "prompt": build_batch_agent_prompt(
                            round_num=next_round,
                            total_rounds=state.total_rounds,
                            platform=platform_name,
                            simulation_requirement=requirement,
                            agents=agents_payload,
                        ),
                    }
                )
        return {
            "completed": False,
            "round": next_round,
            "total_rounds": state.total_rounds,
            "system_prompt": AGENT_DECISION_SYSTEM_PROMPT,
            "batches": batches,
        }

    _run(_handler)


@sim.command("apply")
@click.option("--project", "-p", required=True)
@click.option("--round", "round_num", type=int, required=True)
@click.option("--data", required=True, help="Agent actions JSON")
def sim_apply(project: str, round_num: int, data: str) -> None:
    """Apply agent decisions for a round."""

    def _handler() -> dict[str, Any]:
        payload = _parse_json_string(data, "agent actions")
        if not isinstance(payload, list):
            raise ValueError("Agent actions must be a JSON array")
        state = _load_sim_state(project)
        twitter = _load_platform(project, "twitter")
        reddit = _load_platform(project, "reddit")
        twitter.current_round = round_num
        reddit.current_round = round_num
        outcomes: list[dict[str, Any]] = []
        actions_path = JsonStore.project_path(project, "simulation", "actions.jsonl")
        for action in payload:
            if not isinstance(action, dict):
                continue
            agent_id = str(action.get("agent_id", "")).strip()
            action_type = str(action.get("action", "")).strip()
            args = dict(action.get("args", {}))
            platform_name = (
                str(action.get("platform", "twitter")).strip().casefold() or "twitter"
            )
            platform_obj = reddit if platform_name == "reddit" else twitter
            result = platform_obj.execute_action(
                agent_id=agent_id, action_type=action_type, args=args
            )
            record = {
                "round": round_num,
                "platform": platform_name,
                "agent_id": agent_id,
                "agent": platform_obj.users.get(agent_id).agent_name
                if agent_id in platform_obj.users
                else agent_id,
                "action": action_type,
                "args": args,
                "success": bool(result.get("success")),
                "result": result.get("result"),
                "error": result.get("error"),
            }
            outcomes.append(record)
            JsonStore.append_jsonl(actions_path, record)
        state.current_round = max(state.current_round, round_num)
        state.status = (
            SimulationStatus.COMPLETED
            if state.current_round >= state.total_rounds
            else SimulationStatus.RUNNING
        )
        if state.status == SimulationStatus.COMPLETED:
            state.completed_at = datetime.now(timezone.utc)
            _set_project_status(project, ProjectStatus.SIMULATION_COMPLETE)
        else:
            _set_project_status(project, ProjectStatus.SIMULATION_RUNNING)
        _save_sim_state(state)
        _save_platform(project, "twitter", twitter)
        _save_platform(project, "reddit", reddit)
        return {
            "round": round_num,
            "applied": len(outcomes),
            "outcomes": outcomes,
            "simulation": state.to_dict(),
        }

    _run(_handler)


@sim.command("update-memories")
@click.option("--project", "-p", required=True)
@click.option("--round", "round_num", type=int, required=True)
@click.option("--data", required=True, help="Memory updates JSON")
def sim_update_memories(project: str, round_num: int, data: str) -> None:
    """Save agent memory updates after a round."""

    def _handler() -> dict[str, Any]:
        payload = _parse_json_string(data, "memory updates")
        if not isinstance(payload, list):
            raise ValueError("Memory updates must be a JSON array")
        path = JsonStore.project_path(project, "simulation", "memories.json")
        existing = JsonStore.load(path) or {"rounds": {}}
        existing.setdefault("rounds", {})[str(round_num)] = payload
        JsonStore.save(path, existing)
        return {"round": round_num, "saved_memories": len(payload)}

    _run(_handler)


def sim_status_handler(project: str) -> dict[str, Any]:
    try:
        state = _load_sim_state(project)
    except Exception:
        return {"initialized": False}
    return {
        "initialized": True,
        "simulation": state.to_dict(),
        "remaining_rounds": max(0, state.total_rounds - state.current_round),
    }


@sim.command("status")
@click.option("--project", "-p", required=True)
def sim_status(project: str) -> None:
    """Show simulation progress."""

    _run(lambda: sim_status_handler(project))


@sim.command("round-summary")
@click.option("--project", "-p", required=True)
@click.option("--round", "round_num", type=int, required=True)
def sim_round_summary(project: str, round_num: int) -> None:
    """Show summary of a specific round."""

    def _handler() -> dict[str, Any]:
        actions = JsonStore.read_jsonl(
            JsonStore.project_path(project, "simulation", "actions.jsonl")
        )
        round_actions = [
            item for item in actions if int(item.get("round", -1)) == round_num
        ]
        twitter_count = sum(
            1 for item in round_actions if item.get("platform") == "twitter"
        )
        reddit_count = sum(
            1 for item in round_actions if item.get("platform") == "reddit"
        )
        return {
            "round": round_num,
            "total_actions": len(round_actions),
            "twitter_actions": twitter_count,
            "reddit_actions": reddit_count,
            "actions": round_actions,
        }

    _run(_handler)


# ── Search ──
@cli.group()
def search() -> None:
    """Search knowledge graph."""


@search.command("quick")
@click.option("--project", "-p", required=True)
@click.option("--query", "-q", required=True)
@click.option("--limit", default=10)
def search_quick(project: str, query: str, limit: int) -> None:
    """Fast keyword search."""

    _run(lambda: GraphSearchService(project).quick_search(query, limit=limit))


@search.command("panorama")
@click.option("--project", "-p", required=True)
@click.option("--query", "-q", required=True)
def search_panorama(project: str, query: str) -> None:
    """Broad search with temporal info."""

    _run(lambda: GraphSearchService(project).panorama_search(query))


@search.command("insight")
@click.option("--project", "-p", required=True)
@click.option("--query", "-q", required=True)
@click.option("--sub-queries", default=None, help="Sub-queries JSON array")
def search_insight(project: str, query: str, sub_queries: str | None) -> None:
    """Deep multi-pass search."""

    def _handler() -> dict[str, Any]:
        sub_list: list[str] | None = None
        if sub_queries:
            parsed = _parse_json_string(sub_queries, "sub-queries")
            if not isinstance(parsed, list):
                raise ValueError("sub-queries must be a JSON array")
            sub_list = [str(item) for item in parsed]
        return GraphSearchService(project).insight_search(query, sub_queries=sub_list)

    _run(_handler)


@search.command("context")
@click.option("--project", "-p", required=True)
def search_context(project: str) -> None:
    """Get combined context for report planning."""

    _run(lambda: GraphSearchService(project).get_search_context())


@search.command("posts")
@click.option("--project", "-p", required=True)
@click.option("--platform", default=None)
@click.option("--agent", default=None)
@click.option("--round", "round_num", type=int, default=None)
@click.option("--limit", default=20)
def search_posts(
    project: str,
    platform: str | None,
    agent: str | None,
    round_num: int | None,
    limit: int,
) -> None:
    """Search simulation posts."""

    _run(
        lambda: GraphSearchService(project).get_simulation_posts(
            platform=platform, agent_name=agent, round_num=round_num, limit=limit
        )
    )


# ── Report ──
@cli.group()
def report() -> None:
    """Generate prediction report."""


@report.command("plan-context")
@click.option("--project", "-p", required=True)
def report_plan_context(project: str) -> None:
    """Get context for report outline planning."""

    _run(
        lambda: {
            "project": _load_project(project).to_dict(),
            "graph_context": GraphSearchService(project).get_search_context(),
            "simulation": sim_status_handler(project),
        }
    )


@report.command("save-outline")
@click.option("--project", "-p", required=True)
@click.option("--data", required=True, help="Outline JSON")
def report_save_outline(project: str, data: str) -> None:
    """Save report outline."""

    def _handler() -> dict[str, Any]:
        payload = _parse_json_string(data, "report outline")
        if not isinstance(payload, dict):
            raise ValueError("Outline must be a JSON object")
        sections = payload.get("sections", [])
        if not isinstance(sections, list):
            raise ValueError("Outline sections must be a list")
        JsonStore.save(
            JsonStore.project_path(project, "report", "outline.json"), payload
        )
        return {"saved": True, "section_count": len(sections)}

    _run(_handler)


@report.command("section-context")
@click.option("--project", "-p", required=True)
@click.option("--index", type=int, required=True)
@click.option("--queries", default=None, help="Search queries JSON")
def report_section_context(project: str, index: int, queries: str | None) -> None:
    """Get search results for writing a section."""

    def _handler() -> dict[str, Any]:
        outline = _load_outline(project)
        sections = outline.get("sections", []) if isinstance(outline, dict) else []
        if not isinstance(sections, list) or index < 0 or index >= len(sections):
            raise ValueError("Section index out of range")
        q_values: list[str] = []
        if queries:
            parsed = _parse_json_string(queries, "queries")
            if not isinstance(parsed, list):
                raise ValueError("queries must be a JSON array")
            q_values = [str(item).strip() for item in parsed if str(item).strip()]
        service = GraphSearchService(project)
        search_results = [service.insight_search(item) for item in q_values]
        return {
            "section": sections[index],
            "queries": q_values,
            "search_results": search_results,
        }

    _run(_handler)


@report.command("save-section")
@click.option("--project", "-p", required=True)
@click.option("--index", type=int, required=True)
@click.option("--content", required=True)
def report_save_section(project: str, index: int, content: str) -> None:
    """Save a written section."""

    def _handler() -> dict[str, Any]:
        sections_dir = JsonStore.project_path(project, "report", "sections")
        JsonStore.ensure_dir(sections_dir)
        path = sections_dir / f"{index:03d}.md"
        path.write_text(content, encoding="utf-8")
        return {"saved": True, "index": index, "path": str(path)}

    _run(_handler)


@report.command("assemble")
@click.option("--project", "-p", required=True)
def report_assemble(project: str) -> None:
    """Assemble final report from sections."""

    def _handler() -> dict[str, Any]:
        outline = _load_outline(project)
        title = (
            str(outline.get("title", "Prediction Report"))
            if outline
            else "Prediction Report"
        )
        sections = outline.get("sections", []) if isinstance(outline, dict) else []
        sections_dir = JsonStore.project_path(project, "report", "sections")
        chunks: list[str] = [f"# {title}"]
        for index, section in enumerate(sections):
            section_title = (
                str(section.get("title", f"Section {index + 1}"))
                if isinstance(section, dict)
                else f"Section {index + 1}"
            )
            path = sections_dir / f"{index:03d}.md"
            body = (
                path.read_text(encoding="utf-8").strip()
                if path.exists()
                else "(section not yet written)"
            )
            chunks.append(f"\n## {section_title}\n\n{body}")
        final_text = "\n".join(chunks).strip() + "\n"
        report_path = JsonStore.project_path(project, "report", "report.md")
        report_path.write_text(final_text, encoding="utf-8")
        _set_project_status(project, ProjectStatus.REPORT_GENERATED)
        return {"saved": True, "path": str(report_path), "chars": len(final_text)}

    _run(_handler)


@report.command("view")
@click.option("--project", "-p", required=True)
def report_view(project: str) -> None:
    """View the generated report."""

    def _handler() -> dict[str, Any]:
        path = JsonStore.project_path(project, "report", "report.md")
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        return {"project_id": project, "has_report": bool(content), "report": content}

    _run(_handler)


def report_status_handler(project: str) -> dict[str, Any]:
    outline = _load_outline(project)
    sections = outline.get("sections", []) if isinstance(outline, dict) else []
    sections_dir = JsonStore.project_path(project, "report", "sections")
    written = len(list(sections_dir.glob("*.md"))) if sections_dir.exists() else 0
    report_exists = JsonStore.project_path(project, "report", "report.md").exists()
    return {
        "outline_exists": bool(outline),
        "total_sections": len(sections),
        "written_sections": written,
        "report_exists": report_exists,
    }


@report.command("status")
@click.option("--project", "-p", required=True)
def report_status(project: str) -> None:
    """Check report generation progress."""

    _run(lambda: report_status_handler(project))


# ── Chat ──
@cli.group()
def chat() -> None:
    """Interactive chat with agents."""


@chat.command("list-agents")
@click.option("--project", "-p", required=True)
def chat_list_agents(project: str) -> None:
    """List agents available for interview."""

    _run(lambda: {"agents": PersonaGenerator.list_profiles(project)})


@chat.command("agent-context")
@click.option("--project", "-p", required=True)
@click.option("--agent", "-a", required=True, help="Agent name")
def chat_agent_context(project: str, agent: str) -> None:
    """Get context for interviewing an agent."""

    def _handler() -> dict[str, Any]:
        profiles = PersonaGenerator.list_profiles(project)
        selected = next(
            (
                item
                for item in profiles
                if item.get("name", "").casefold() == agent.casefold()
            ),
            None,
        )
        if not selected:
            raise ValueError(f"Agent not found: {agent}")
        posts = GraphSearchService(project).get_simulation_posts(
            agent_name=selected["name"], limit=20
        )
        return {"agent": selected, "recent_posts": posts.get("posts", [])}

    _run(_handler)


@chat.command("report-context")
@click.option("--project", "-p", required=True)
def chat_report_context(project: str) -> None:
    """Get context for chatting about the report."""

    _run(
        lambda: {
            "project": _load_project(project).to_dict(),
            "report": report_view_handler(project),
            "graph_context": GraphSearchService(project).get_search_context(),
        }
    )


def report_view_handler(project: str) -> dict[str, Any]:
    path = JsonStore.project_path(project, "report", "report.md")
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return {"has_report": bool(content), "report": content}


@chat.command("batch-context")
@click.option("--project", "-p", required=True)
@click.option("--agents", required=True, help="Comma-separated agent names")
@click.option("--topic", "-t", default=None)
def chat_batch_context(project: str, agents: str, topic: str | None) -> None:
    """Get context for batch interviewing agents."""

    def _handler() -> dict[str, Any]:
        names = [name.strip() for name in agents.split(",") if name.strip()]
        profiles = PersonaGenerator.list_profiles(project)
        lookup = {str(item.get("name", "")).casefold(): item for item in profiles}
        selected = [
            lookup[name.casefold()] for name in names if name.casefold() in lookup
        ]
        posts = GraphSearchService(project)
        contexts = []
        for item in selected:
            contexts.append(
                {
                    "agent": item,
                    "posts": posts.get_simulation_posts(
                        agent_name=item["name"], limit=10
                    ).get("posts", []),
                }
            )
        return {"topic": topic, "agents": contexts}

    _run(_handler)


def main() -> None:
    try:
        cli(standalone_mode=False)
    except click.ClickException as exc:
        _error(exc.format_message())
    except SystemExit as exc:
        if exc.code not in (0, None):
            _error(f"Command failed with exit code {exc.code}")
    except Exception as exc:  # noqa: BLE001
        _error(str(exc))


if __name__ == "__main__":
    main()
