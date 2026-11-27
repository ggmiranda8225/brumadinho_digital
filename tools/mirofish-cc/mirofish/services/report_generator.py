from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from mirofish.config import (
    PROJECTS_DIR,
    REPORT_MAX_REFLECTION_ROUNDS,
    REPORT_MAX_TOOL_CALLS,
)
from mirofish.models.project import Project, ProjectStatus
from mirofish.services.graph_search import GraphSearchService
from mirofish.store.json_store import JsonStore


class ReportGenerator:
    @staticmethod
    def get_planning_context(project_id: str) -> Dict[str, Any]:
        """Gather context for report outline planning."""
        search_context: Dict[str, Any] = {}
        try:
            search_context = GraphSearchService(project_id).get_search_context()
        except Exception:  # noqa: BLE001
            search_context = {}

        simulation_summary = ReportGenerator._build_simulation_summary(project_id)
        sample_facts = ReportGenerator._normalize_sample_facts(
            search_context.get("sample_facts", [])
        )
        key_entities = ReportGenerator._normalize_key_entities(
            search_context.get("key_entities", [])
        )

        return {
            "simulation_requirement": ReportGenerator._load_simulation_requirement(project_id),
            "graph_stats": search_context.get("graph_stats", {}),
            "simulation_summary": simulation_summary,
            "sample_facts": sample_facts[:10],
            "key_entities": key_entities[:10],
            "ontology_summary": search_context.get(
                "ontology_summary",
                {"entity_types": [], "relationship_types": []},
            ),
            "react_limits": {
                "max_tool_calls": REPORT_MAX_TOOL_CALLS,
                "max_reflection_rounds": REPORT_MAX_REFLECTION_ROUNDS,
            },
        }

    @staticmethod
    def get_section_context(
        project_id: str,
        section_title: str,
        section_description: str,
        search_queries: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """Get search results and relevant simulation context for one section."""
        service = GraphSearchService(project_id)
        queries = search_queries or ReportGenerator._build_auto_queries(
            section_title=section_title,
            section_description=section_description,
        )

        search_results: List[Dict[str, Any]] = []
        related_rounds: set[int] = set()

        for query_item in queries:
            search_type = str(query_item.get("type", "quick")).strip().casefold()
            query = str(query_item.get("query", "")).strip()
            if not query:
                continue

            if search_type == "panorama":
                result = service.panorama_search(query)
            elif search_type == "insight":
                result = service.insight_search(query)
            else:
                search_type = "quick"
                result = service.quick_search(query)

            related_rounds.update(ReportGenerator._extract_rounds_from_search_result(result))
            search_results.append(
                {
                    "query": query,
                    "type": search_type,
                    "results": result,
                }
            )

        relevant_posts = ReportGenerator._find_relevant_posts(
            project_id=project_id,
            section_title=section_title,
            section_description=section_description,
            search_results=search_results,
        )
        related_rounds.update(
            {
                int(post.get("round", 0))
                for post in relevant_posts
                if isinstance(post.get("round"), int)
            }
        )

        simulation_summary_text = ReportGenerator._format_section_simulation_summary(
            project_id=project_id,
            related_rounds=sorted(value for value in related_rounds if value >= 0),
        )

        return {
            "section_title": section_title,
            "section_description": section_description,
            "search_results": search_results,
            "relevant_posts": [
                {
                    "author": post.get("author", ""),
                    "content": post.get("content", ""),
                    "platform": post.get("platform", ""),
                    "engagement": post.get("engagement", 0),
                }
                for post in relevant_posts
            ],
            "simulation_summary": simulation_summary_text,
        }

    @staticmethod
    def save_outline(project_id: str, outline: Dict[str, Any]) -> Dict[str, Any]:
        """Save report outline (title, summary, sections)."""
        title = str(outline.get("title", "")).strip()
        summary = str(outline.get("summary", "")).strip()
        sections = outline.get("sections", [])

        if not title:
            raise ValueError("Outline title is required")
        if not summary:
            raise ValueError("Outline summary is required")
        if not isinstance(sections, list) or not sections:
            raise ValueError("Outline sections must be a non-empty list")

        normalized_sections: List[Dict[str, str]] = []
        for section in sections:
            if not isinstance(section, dict):
                raise ValueError("Each section must be an object")
            section_title = str(section.get("title", "")).strip()
            section_description = str(section.get("description", "")).strip()
            if not section_title or not section_description:
                raise ValueError("Each section must include title and description")
            normalized_sections.append(
                {
                    "title": section_title,
                    "description": section_description,
                }
            )

        payload = {
            "title": title,
            "summary": summary,
            "sections": normalized_sections,
            "saved_at": ReportGenerator._utc_now(),
        }

        JsonStore.save(ReportGenerator._outline_path(project_id), payload)
        return {"saved": True, "section_count": len(normalized_sections)}

    @staticmethod
    def save_section(project_id: str, section_index: int, content: str) -> Dict[str, Any]:
        """Save a written section markdown file."""
        if section_index < 0:
            raise ValueError("section_index must be >= 0")

        text = str(content).strip()
        section_path = ReportGenerator._reports_dir(project_id) / f"section_{section_index}.md"
        JsonStore.ensure_dir(section_path)
        section_path.write_text(text + "\n", encoding="utf-8")

        return {
            "saved": True,
            "section_index": section_index,
            "word_count": ReportGenerator._word_count(text),
        }

    @staticmethod
    def assemble_report(project_id: str) -> Dict[str, Any]:
        """Assemble final report markdown from outline + section files."""
        outline = JsonStore.load(ReportGenerator._outline_path(project_id))
        if not outline:
            raise ValueError("Report outline not found")

        title = str(outline.get("title", "")).strip()
        summary = str(outline.get("summary", "")).strip()
        sections = outline.get("sections", [])
        if not title or not summary or not isinstance(sections, list) or not sections:
            raise ValueError("Invalid report outline structure")

        lines: List[str] = [f"# {title}", "", f"> {summary}", ""]
        assembled_sections: List[Dict[str, Any]] = []

        for index, section in enumerate(sections):
            section_title = str(section.get("title", f"Section {index + 1}")).strip()
            section_path = ReportGenerator._reports_dir(project_id) / f"section_{index}.md"
            section_content = section_path.read_text(encoding="utf-8").strip() if section_path.exists() else ""

            lines.extend([f"## {section_title}", section_content, ""])
            assembled_sections.append(
                {
                    "index": index,
                    "title": section_title,
                    "word_count": ReportGenerator._word_count(section_content),
                    "path": str(section_path),
                }
            )

        simulation_summary = ReportGenerator._build_simulation_summary(project_id)
        project_payload = JsonStore.load(JsonStore.project_path(project_id, "project.json"))

        metadata = {
            "project_id": project_id,
            "generated_at": ReportGenerator._utc_now(),
            "rounds": simulation_summary.get("total_rounds", 0),
            "agent_count": simulation_summary.get("agent_count", 0),
            "section_count": len(sections),
            "title": title,
            "summary": summary,
            "project_name": str(project_payload.get("name", "")).strip(),
            "sections": assembled_sections,
        }

        lines.extend(
            [
                "---",
                "",
                f"Generated at: {metadata['generated_at']}",
                f"Project ID: {project_id}",
                f"Rounds: {metadata['rounds']}",
                f"Agent count: {metadata['agent_count']}",
            ]
        )

        report_text = "\n".join(lines).strip() + "\n"
        report_path = ReportGenerator._reports_dir(project_id) / "report.md"
        report_path.write_text(report_text, encoding="utf-8")
        JsonStore.save(ReportGenerator._reports_dir(project_id) / "report_meta.json", metadata)

        ReportGenerator._set_project_status(project_id, ProjectStatus.REPORT_GENERATED)

        return {
            "report_path": str(report_path),
            "word_count": ReportGenerator._word_count(report_text),
            "section_count": len(sections),
        }

    @staticmethod
    def get_report(project_id: str) -> Dict[str, Any]:
        """Load and return the full saved report."""
        outline = JsonStore.load(ReportGenerator._outline_path(project_id))
        metadata = JsonStore.load(ReportGenerator._reports_dir(project_id) / "report_meta.json")
        report_path = ReportGenerator._reports_dir(project_id) / "report.md"
        content = report_path.read_text(encoding="utf-8") if report_path.exists() else ""

        section_payloads: List[Dict[str, str]] = []
        for index, section in enumerate(outline.get("sections", [])):
            section_title = str(section.get("title", f"Section {index + 1}")).strip()
            section_file = ReportGenerator._reports_dir(project_id) / f"section_{index}.md"
            section_content = section_file.read_text(encoding="utf-8").strip() if section_file.exists() else ""
            section_payloads.append({"title": section_title, "content": section_content})

        return {
            "title": str(outline.get("title", "")).strip(),
            "summary": str(outline.get("summary", "")).strip(),
            "content": content,
            "metadata": metadata,
            "sections": section_payloads,
        }

    @staticmethod
    def get_report_status(project_id: str) -> Dict[str, Any]:
        """Check report generation progress for a project."""
        outline = JsonStore.load(ReportGenerator._outline_path(project_id))
        sections = outline.get("sections", []) if isinstance(outline.get("sections"), list) else []

        written_count = 0
        for index in range(len(sections)):
            path = ReportGenerator._reports_dir(project_id) / f"section_{index}.md"
            if path.exists() and path.read_text(encoding="utf-8").strip():
                written_count += 1

        total_sections = len(sections)
        has_outline = bool(outline)
        is_complete = bool(has_outline and total_sections > 0 and written_count >= total_sections)

        return {
            "has_outline": has_outline,
            "sections_written": written_count,
            "total_sections": total_sections,
            "is_complete": is_complete,
        }

    @staticmethod
    def _build_auto_queries(section_title: str, section_description: str) -> List[Dict[str, str]]:
        base = f"{section_title}. {section_description}".strip()
        title = section_title.strip() or "section analysis"
        desc = section_description.strip() or title
        return [
            {"type": "quick", "query": title},
            {"type": "panorama", "query": desc},
            {"type": "insight", "query": base},
        ]

    @staticmethod
    def _find_relevant_posts(
        project_id: str,
        section_title: str,
        section_description: str,
        search_results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        posts = ReportGenerator._load_all_platform_posts(project_id)
        if not posts:
            return []

        keywords = ReportGenerator._keywords(
            " ".join(
                [
                    section_title,
                    section_description,
                    " ".join(str(item.get("query", "")) for item in search_results),
                ]
            )
        )

        if not keywords:
            posts.sort(key=lambda item: item.get("engagement", 0), reverse=True)
            return posts[:10]

        scored: List[tuple[int, Dict[str, Any]]] = []
        for post in posts:
            body = f"{post.get('content', '')} {post.get('author', '')}".casefold()
            score = sum(1 for keyword in keywords if keyword in body)
            if score > 0:
                scored.append((score + int(post.get("engagement", 0)), post))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:12]]

    @staticmethod
    def _load_all_platform_posts(project_id: str) -> List[Dict[str, Any]]:
        posts: List[Dict[str, Any]] = []
        simulation_dir = JsonStore.project_path(project_id, "simulation")

        for platform_name in ("twitter", "reddit"):
            platform_path = simulation_dir / f"{platform_name}_platform.json"
            payload = JsonStore.load(platform_path)
            raw_posts = payload.get("posts", {})
            if not isinstance(raw_posts, dict):
                continue

            for post_id, post in raw_posts.items():
                if not isinstance(post, dict):
                    continue
                likes = post.get("likes", [])
                reposts = post.get("reposts", [])
                replies = post.get("reply_ids", [])
                engagement = len(likes) + (2 * len(reposts)) + len(replies)
                posts.append(
                    {
                        "post_id": str(post_id),
                        "author": str(post.get("author_name", "")).strip(),
                        "author_id": str(post.get("author_id", "")).strip(),
                        "content": str(post.get("content", "")).strip(),
                        "platform": str(post.get("platform", platform_name)).strip() or platform_name,
                        "round": int(post.get("round_created", 0)),
                        "engagement": engagement,
                    }
                )

        posts.sort(key=lambda item: item.get("engagement", 0), reverse=True)
        return posts

    @staticmethod
    def _extract_rounds_from_search_result(result: Dict[str, Any]) -> set[int]:
        rounds: set[int] = set()
        serialized = json.dumps(result, ensure_ascii=False)
        for match in re.findall(r"(?:round|round_num|round_created)\D{0,4}(\d+)", serialized, flags=re.IGNORECASE):
            value = int(match)
            if value >= 0:
                rounds.add(value)
        return rounds

    @staticmethod
    def _format_section_simulation_summary(project_id: str, related_rounds: List[int]) -> str:
        summary = ReportGenerator._build_simulation_summary(project_id)
        rounds_text = ", ".join(str(value) for value in sorted(set(related_rounds))) if related_rounds else "none"
        action_breakdown = summary.get("action_type_counts", {})

        return (
            f"total_rounds={summary.get('total_rounds', 0)}, "
            f"agent_count={summary.get('agent_count', 0)}, "
            f"total_actions={summary.get('total_actions', 0)}, "
            f"platforms={summary.get('platform_counts', {})}, "
            f"related_rounds={rounds_text}, "
            f"action_breakdown={action_breakdown}"
        )

    @staticmethod
    def _build_simulation_summary(project_id: str) -> Dict[str, Any]:
        actions = JsonStore.read_jsonl(JsonStore.project_path(project_id, "simulation", "actions.jsonl"))
        rounds: set[int] = set()
        agents: set[str] = set()
        platform_counts: Dict[str, int] = {}
        action_type_counts: Dict[str, int] = {}

        for action in actions:
            round_num = action.get("round_num", action.get("round"))
            if isinstance(round_num, int):
                rounds.add(round_num)

            agent_id = str(action.get("agent_id", "")).strip()
            if agent_id:
                agents.add(agent_id)

            platform = str(action.get("platform", "")).strip().lower()
            if platform:
                platform_counts[platform] = platform_counts.get(platform, 0) + 1

            action_type = str(action.get("action_type", action.get("action", ""))).strip()
            if action_type:
                action_type_counts[action_type] = action_type_counts.get(action_type, 0) + 1

        return {
            "total_rounds": max(rounds) if rounds else 0,
            "agent_count": len(agents),
            "total_actions": len(actions),
            "platform_counts": platform_counts,
            "action_type_counts": action_type_counts,
        }

    @staticmethod
    def _normalize_sample_facts(raw_facts: Any) -> List[str]:
        if not isinstance(raw_facts, list):
            return []

        facts: List[str] = []
        for item in raw_facts:
            if isinstance(item, str):
                value = item.strip()
                if value:
                    facts.append(value)
                continue

            if not isinstance(item, dict):
                continue
            source = str(item.get("source", "")).strip()
            target = str(item.get("target", "")).strip()
            rel_type = str(item.get("relationship_type", item.get("type", ""))).strip()
            fact = str(item.get("fact", "")).strip()
            line = f"{source} --{rel_type}--> {target}: {fact}".strip()
            if line:
                facts.append(line)

        return facts

    @staticmethod
    def _normalize_key_entities(raw_entities: Any) -> List[Dict[str, Any]]:
        if not isinstance(raw_entities, list):
            return []

        entities: List[Dict[str, Any]] = []
        for item in raw_entities:
            if not isinstance(item, dict):
                continue
            entities.append(
                {
                    "name": str(item.get("name", "")).strip(),
                    "type": str(item.get("type", "Unknown")).strip() or "Unknown",
                    "edge_count": int(item.get("edge_count", 0)),
                }
            )
        return entities

    @staticmethod
    def _set_project_status(project_id: str, status: ProjectStatus) -> None:
        path = JsonStore.project_path(project_id, "project.json")
        payload = JsonStore.load(path)
        if not payload:
            return

        project = Project.from_dict(payload)
        project.update_status(status)
        JsonStore.save(path, project.to_dict())

    @staticmethod
    def _load_simulation_requirement(project_id: str) -> str:
        project_path = JsonStore.project_path(project_id, "project.json")
        project_payload = JsonStore.load(project_path)
        return str(project_payload.get("simulation_requirement", "")).strip()

    @staticmethod
    def _keywords(text: str) -> List[str]:
        tokens = re.findall(r"[a-zA-Z0-9]{3,}", text.casefold())
        seen: set[str] = set()
        keywords: List[str] = []
        for token in tokens:
            if token in seen:
                continue
            seen.add(token)
            keywords.append(token)
        return keywords

    @staticmethod
    def _word_count(text: str) -> int:
        return len([value for value in text.split() if value.strip()])

    @staticmethod
    def _utc_now() -> str:
        return datetime.utcnow().isoformat(timespec="seconds") + "Z"

    @staticmethod
    def _outline_path(project_id: str) -> Path:
        return ReportGenerator._reports_dir(project_id) / "outline.json"

    @staticmethod
    def _reports_dir(project_id: str) -> Path:
        path = PROJECTS_DIR / project_id / "reports"
        JsonStore.ensure_dir(path)
        return path
