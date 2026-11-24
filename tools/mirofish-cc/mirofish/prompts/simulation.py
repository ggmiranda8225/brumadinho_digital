from __future__ import annotations

from typing import Any, Iterable

AGENT_DECISION_SYSTEM_PROMPT = """
You are simulating social media behavior for multiple AI agents in a swarm intelligence prediction simulation.

Each agent has a distinct personality, background, and goals. For each agent, you must:
1. Read their persona and current feed
2. Consider their personality traits, interests, and the prediction topic
3. Choose ONE action that this specific agent would most likely take
4. Generate appropriate content if the action requires it (CREATE_POST, QUOTE_POST, CREATE_COMMENT)

Rules:
- Each agent acts INDEPENDENTLY based on their own personality
- Content must reflect the agent's unique voice and perspective
- DO_NOTHING is valid when nothing relevant appears in the feed
- Posts should be realistic social media content (not formal essays)
- Agents may disagree with each other — this creates realistic discourse
- Content language should match the seed material language (Chinese/English/etc.)

Decision quality requirements:
- Use only the feed and persona provided for each agent
- Prefer specific, concrete reactions over generic filler text
- Do not force engagement when the feed is irrelevant to the agent
- Keep style aligned with platform norms and character limits
- Avoid repeating nearly identical text across different agents
- Preserve each agent's worldview, confidence level, and bias profile

Action selection guidance:
- CREATE_POST: agent starts a fresh opinion or information thread
- QUOTE_POST: agent reacts to an existing post with commentary
- CREATE_COMMENT: agent replies under a post with a focused response
- LIKE/REPOST/FOLLOW/MUTE/etc.: choose when low-friction behavior is more realistic
- DO_NOTHING: choose when there is no compelling reason to act now

Output contract:
- Return valid JSON only (no markdown, no explanations)
- Return exactly one action object per input agent
- Include only fields that are relevant for the selected action
- Preserve provided IDs exactly when targeting posts/users/comments
""".strip()


BATCH_AGENT_PROMPT_TEMPLATE = """
## Round {round_num} / {total_rounds} — {platform} Platform

**Prediction Topic**: {simulation_requirement}

Process these {n_agents} agents. For each, return exactly ONE action.

{agent_blocks}

Return a JSON array of actions:
[
  {{
    "agent_id": "...",
    "action": "ACTION_TYPE",
    "args": {{
      "content": "post text (if creating post/comment/quote)",
      "target_post_id": "post_id (if liking/reposting/commenting)",
      "target_user_id": "agent_id (if following/muting)",
      "target_comment_id": "comment_id (if liking/disliking comment)",
      "parent_comment_id": "comment_id (if replying to comment)"
    }}
  }}
]
""".strip()


SINGLE_AGENT_BLOCK_TEMPLATE = """
### Agent: {name} ({profession})
**Persona**: {persona_summary}
**Recent activity**: {recent_actions_summary}
**Current feed** (top {feed_size} items):
{feed_items}
**Available actions**: {actions_list}
""".strip()


SEED_POST_PROMPT_TEMPLATE = """
Generate {count} seed posts for the {platform} platform to kickstart discussion about: {simulation_requirement}

These posts should represent diverse initial perspectives on the topic.
Output JSON array: [{{"agent_id": "...", "content": "..."}}]
""".strip()


MEMORY_UPDATE_PROMPT_TEMPLATE = """
Based on what happened in Round {round_num}, generate a brief memory update for each active agent.
{round_summary}
For each agent, summarize what they did, what they observed, and how it might affect their future behavior.
Output JSON: [{{"agent_id": "...", "memory": "..."}}]
""".strip()


def _truncate(text: str, max_chars: int) -> str:
    value = text.strip()
    if len(value) <= max_chars:
        return value
    if max_chars <= 3:
        return value[:max_chars]
    return value[: max_chars - 3].rstrip() + "..."


def _format_feed_item(index: int, item: dict[str, Any]) -> str:
    post_id = str(item.get("post_id") or item.get("id") or "unknown")
    author = str(item.get("author") or item.get("author_name") or item.get("agent_name") or "unknown")
    content = _truncate(str(item.get("content") or ""), 280)

    stats_parts: list[str] = []
    likes = item.get("like_count")
    reposts = item.get("repost_count")
    comments = item.get("comment_count")

    if isinstance(likes, int):
        stats_parts.append(f"likes={likes}")
    if isinstance(reposts, int):
        stats_parts.append(f"reposts={reposts}")
    if isinstance(comments, int):
        stats_parts.append(f"comments={comments}")

    stats_line = f" ({', '.join(stats_parts)})" if stats_parts else ""
    return f"- [{index}] post_id={post_id} by {author}{stats_line}: {content}"


def format_feed_items(feed: Iterable[dict[str, Any]]) -> str:
    feed_list = list(feed)
    if not feed_list:
        return "- (empty feed)"

    lines: list[str] = []
    for index, item in enumerate(feed_list, start=1):
        lines.append(_format_feed_item(index=index, item=item))
    return "\n".join(lines)


def format_recent_actions(actions: Iterable[str]) -> str:
    cleaned = [str(action).strip() for action in actions if str(action).strip()]
    if not cleaned:
        return "No recent actions"
    return " | ".join(cleaned[:3])


def build_single_agent_block(agent: dict[str, Any], feed_size: int = 5) -> str:
    persona_summary = _truncate(str(agent.get("persona_summary") or ""), 240)
    recent_actions_summary = format_recent_actions(agent.get("recent_actions", []))
    feed = list(agent.get("feed", []))[:feed_size]
    feed_items = format_feed_items(feed)

    actions = [str(action).strip() for action in agent.get("available_actions", []) if str(action).strip()]
    actions_list = ", ".join(actions) if actions else "DO_NOTHING"

    return SINGLE_AGENT_BLOCK_TEMPLATE.format(
        name=str(agent.get("name") or "Unknown Agent"),
        profession=str(agent.get("profession") or "Unknown"),
        persona_summary=persona_summary or "No persona provided",
        recent_actions_summary=recent_actions_summary,
        feed_size=feed_size,
        feed_items=feed_items,
        actions_list=actions_list,
    )


def build_batch_agent_prompt(
    *,
    round_num: int,
    total_rounds: int,
    platform: str,
    simulation_requirement: str,
    agents: list[dict[str, Any]],
) -> str:
    blocks = [build_single_agent_block(agent=agent) for agent in agents]
    return BATCH_AGENT_PROMPT_TEMPLATE.format(
        round_num=round_num,
        total_rounds=total_rounds,
        platform=platform,
        simulation_requirement=simulation_requirement,
        n_agents=len(agents),
        agent_blocks="\n\n".join(blocks),
    )


def build_seed_post_prompt(*, platform: str, simulation_requirement: str, count: int) -> str:
    return SEED_POST_PROMPT_TEMPLATE.format(
        count=count,
        platform=platform,
        simulation_requirement=simulation_requirement,
    )


def build_memory_update_prompt(*, round_num: int, round_summary: str) -> str:
    return MEMORY_UPDATE_PROMPT_TEMPLATE.format(
        round_num=round_num,
        round_summary=round_summary,
    )


__all__ = [
    "AGENT_DECISION_SYSTEM_PROMPT",
    "BATCH_AGENT_PROMPT_TEMPLATE",
    "SINGLE_AGENT_BLOCK_TEMPLATE",
    "SEED_POST_PROMPT_TEMPLATE",
    "MEMORY_UPDATE_PROMPT_TEMPLATE",
    "format_feed_items",
    "format_recent_actions",
    "build_single_agent_block",
    "build_batch_agent_prompt",
    "build_seed_post_prompt",
    "build_memory_update_prompt",
]
