from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from mirofish.config import PROJECTS_DIR
from mirofish.models.graph import GraphEdge, GraphNode, KnowledgeGraph
from mirofish.store.json_store import JsonStore


class GraphSearchService:
    """Local knowledge graph search engine replacing Zep Cloud tools."""

    _STOPWORDS = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "no",
        "not",
        "of",
        "on",
        "or",
        "such",
        "that",
        "the",
        "their",
        "then",
        "there",
        "these",
        "they",
        "this",
        "to",
        "was",
        "will",
        "with",
    }

    def __init__(self, project_id: str):
        """Load knowledge graph and simulation data for the project."""
        self.project_id = project_id
        self.graph: KnowledgeGraph
        self._load_graph()

    def quick_search(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """Fast keyword-based search across graph facts and node names."""
        keywords = self._tokenize_query(query)
        if not keywords:
            return {
                "query": query,
                "facts": [],
                "entities": [],
                "total_fact_matches": 0,
                "total_entity_matches": 0,
            }

        fact_hits: List[Dict[str, Any]] = []
        for edge in self.graph.edges:
            score = self._score_text(edge.fact, keywords)
            if score <= 0:
                continue

            source_node = self.graph.get_node_by_uuid(edge.source_node_uuid)
            target_node = self.graph.get_node_by_uuid(edge.target_node_uuid)
            fact_hits.append(
                {
                    "uuid": edge.uuid,
                    "fact": edge.fact,
                    "source_node": source_node.name
                    if source_node
                    else edge.source_node_uuid,
                    "target_node": target_node.name
                    if target_node
                    else edge.target_node_uuid,
                    "relationship_type": edge.name,
                    "score": score,
                }
            )

        entity_hits: List[Dict[str, Any]] = []
        for node in self.graph.nodes.values():
            entity_text = f"{node.name} {node.summary}".strip()
            score = self._score_text(entity_text, keywords)
            if score <= 0:
                continue
            entity_hits.append(
                {
                    "uuid": node.uuid,
                    "name": node.name,
                    "type": self._node_type(node),
                    "summary": node.summary,
                    "score": score,
                }
            )

        fact_hits.sort(key=lambda item: item["score"], reverse=True)
        entity_hits.sort(key=lambda item: item["score"], reverse=True)

        return {
            "query": query,
            "facts": fact_hits[: max(0, limit)],
            "entities": entity_hits[: max(0, limit)],
            "total_fact_matches": len(fact_hits),
            "total_entity_matches": len(entity_hits),
        }

    def panorama_search(
        self, query: str, include_expired: bool = True
    ) -> Dict[str, Any]:
        """Broad search with temporal classification."""
        keywords = self._tokenize_query(query)

        active_hits: List[Dict[str, Any]] = []
        historical_hits: List[Dict[str, Any]] = []
        active_count = 0
        historical_count = 0

        for edge in self.graph.edges:
            source_node = self.graph.get_node_by_uuid(edge.source_node_uuid)
            target_node = self.graph.get_node_by_uuid(edge.target_node_uuid)
            source_name = source_node.name if source_node else edge.source_node_uuid
            target_name = target_node.name if target_node else edge.target_node_uuid

            relevance_text = " ".join(
                [edge.fact, edge.name, source_name, target_name]
            ).strip()
            score = self._score_text(relevance_text, keywords) if keywords else 1
            if score <= 0:
                continue

            payload = {
                "uuid": edge.uuid,
                "fact": edge.fact,
                "source": source_name,
                "target": target_name,
                "type": edge.name,
                "valid_at": edge.valid_at,
                "score": score,
            }

            if edge.expired_at:
                historical_count += 1
                payload["expired_at"] = edge.expired_at
                if include_expired:
                    historical_hits.append(payload)
            else:
                active_count += 1
                active_hits.append(payload)

        active_hits.sort(key=lambda item: item["score"], reverse=True)
        historical_hits.sort(key=lambda item: item["score"], reverse=True)

        all_entities = [
            {
                "name": node.name,
                "type": self._node_type(node),
                "labels": node.labels,
                "summary": node.summary,
            }
            for node in self.graph.nodes.values()
        ]

        return {
            "query": query,
            "active_facts": active_hits,
            "historical_facts": historical_hits,
            "all_entities": all_entities,
            "stats": {
                "total_nodes": len(self.graph.nodes),
                "total_edges": len(self.graph.edges),
                "active_edges": active_count,
                "historical_edges": historical_count,
            },
        }

    def insight_search(
        self, query: str, sub_queries: List[str] | None = None
    ) -> Dict[str, Any]:
        """Deep multi-pass search with sub-question support."""
        search_queries: List[str] = []
        if sub_queries:
            search_queries = [
                value.strip() for value in sub_queries if value and value.strip()
            ]
        if not search_queries:
            keywords = self._tokenize_query(query)
            keyword_variant = " ".join(keywords)
            entity_variant = " ".join([token.title() for token in keywords[:4]])
            candidates = [query.strip(), keyword_variant, entity_variant]
            search_queries = [candidate for candidate in candidates if candidate]

        unique_queries: List[str] = []
        seen_queries: set[str] = set()
        for item in search_queries:
            key = item.casefold()
            if key in seen_queries:
                continue
            seen_queries.add(key)
            unique_queries.append(item)

        matched_edges: Dict[str, Dict[str, Any]] = {}
        for search_query in unique_queries:
            result = self.quick_search(search_query, limit=30)
            for fact in result.get("facts", []):
                edge_uuid = str(fact.get("uuid", ""))
                if not edge_uuid:
                    continue
                existing = matched_edges.get(edge_uuid)
                if existing is None or fact.get("score", 0) > existing.get("score", 0):
                    matched_edges[edge_uuid] = fact

        semantic_facts = [
            {
                "uuid": item["uuid"],
                "fact": item["fact"],
                "score": item["score"],
                "source": item["source_node"],
                "target": item["target_node"],
            }
            for item in matched_edges.values()
        ]
        semantic_facts.sort(key=lambda item: item["score"], reverse=True)

        entity_fact_map: Dict[str, List[Dict[str, Any]]] = {}
        for fact in semantic_facts:
            entity_fact_map.setdefault(fact["source"], []).append(fact)
            entity_fact_map.setdefault(fact["target"], []).append(fact)

        entity_insights: List[Dict[str, Any]] = []
        for entity_name, facts in entity_fact_map.items():
            node = self.graph.get_node_by_name(entity_name)
            top_facts = sorted(
                facts, key=lambda item: item.get("score", 0), reverse=True
            )[:3]
            entity_insights.append(
                {
                    "entity_name": entity_name,
                    "type": self._node_type(node) if node else "Unknown",
                    "related_fact_count": len(facts),
                    "key_facts": [item["fact"] for item in top_facts],
                }
            )
        entity_insights.sort(key=lambda item: item["related_fact_count"], reverse=True)

        relationship_chains: List[Dict[str, Any]] = []
        for insight in entity_insights[:5]:
            relationship_chains.extend(
                self._build_relationship_chain(insight["entity_name"], max_depth=3)
            )

        deduped_chains: List[Dict[str, Any]] = []
        chain_keys: set[tuple[str, ...]] = set()
        for chain in relationship_chains:
            chain_tuple = tuple(chain["chain"])
            if chain_tuple in chain_keys:
                continue
            chain_keys.add(chain_tuple)
            deduped_chains.append(chain)

        return {
            "query": query,
            "sub_queries_used": unique_queries,
            "semantic_facts": semantic_facts,
            "entity_insights": entity_insights,
            "relationship_chains": deduped_chains[:20],
            "total_unique_facts": len(semantic_facts),
        }

    def get_node(self, node_name: str) -> Optional[Dict[str, Any]]:
        """Get a specific entity by name (case-insensitive)."""
        node = self.graph.get_node_by_name(node_name)
        if node is None:
            return None

        node_edges = self.graph.get_edges_for_node(node.uuid)
        neighbors = self.graph.get_neighbors(node.uuid)

        return {
            "uuid": node.uuid,
            "name": node.name,
            "type": self._node_type(node),
            "labels": node.labels,
            "summary": node.summary,
            "attributes": node.attributes,
            "edges": [self._edge_to_dict(edge) for edge in node_edges],
            "neighbors": [
                {
                    "uuid": neighbor.uuid,
                    "name": neighbor.name,
                    "type": self._node_type(neighbor),
                    "labels": neighbor.labels,
                }
                for neighbor in neighbors
            ],
        }

    def get_edge(self, edge_uuid: str) -> Optional[Dict[str, Any]]:
        """Get a specific relationship by UUID."""
        lookup = edge_uuid.strip().casefold()
        for edge in self.graph.edges:
            if edge.uuid.strip().casefold() == lookup:
                return self._edge_to_dict(edge)
        return None

    def get_node_edges(self, node_name: str) -> Dict[str, Any]:
        """Get all relationships for a specific entity."""
        node = self.graph.get_node_by_name(node_name)
        if node is None:
            return {
                "entity_name": node_name,
                "incoming_edges": [],
                "outgoing_edges": [],
                "total_edges": 0,
            }

        incoming: List[Dict[str, Any]] = []
        outgoing: List[Dict[str, Any]] = []
        for edge in self.graph.edges:
            if edge.target_node_uuid == node.uuid:
                incoming.append(self._edge_to_dict(edge))
            if edge.source_node_uuid == node.uuid:
                outgoing.append(self._edge_to_dict(edge))

        return {
            "entity_name": node.name,
            "incoming_edges": incoming,
            "outgoing_edges": outgoing,
            "total_edges": len(incoming) + len(outgoing),
        }

    def get_temporal_edges(self, time_filter: str | None = None) -> Dict[str, Any]:
        """Get edges with temporal information."""
        temporal_edges: List[Dict[str, Any]] = []
        non_temporal_edges: List[Dict[str, Any]] = []

        for edge in self.graph.edges:
            is_temporal = bool(edge.valid_at or edge.invalid_at or edge.expired_at)
            edge_payload = self._edge_to_dict(edge)

            if is_temporal:
                if time_filter and not self._is_edge_valid_at(edge, time_filter):
                    continue
                temporal_edges.append(edge_payload)
            else:
                non_temporal_edges.append(edge_payload)

        return {
            "temporal_edges": temporal_edges,
            "non_temporal_edges": non_temporal_edges,
            "stats": {
                "total_edges": len(self.graph.edges),
                "temporal_edges": len(temporal_edges),
                "non_temporal_edges": len(non_temporal_edges),
                "time_filter": time_filter,
            },
        }

    def get_search_context(self) -> Dict[str, Any]:
        """Combined context for report planning."""
        node_type_distribution: Dict[str, int] = {}
        for node in self.graph.nodes.values():
            node_type = self._node_type(node)
            node_type_distribution[node_type] = (
                node_type_distribution.get(node_type, 0) + 1
            )

        relationship_type_distribution: Dict[str, int] = {}
        for edge in self.graph.edges:
            relationship_type_distribution[edge.name] = (
                relationship_type_distribution.get(edge.name, 0) + 1
            )

        connectivity: Dict[str, int] = {
            node_uuid: 0 for node_uuid in self.graph.nodes.keys()
        }
        for edge in self.graph.edges:
            connectivity[edge.source_node_uuid] = (
                connectivity.get(edge.source_node_uuid, 0) + 1
            )
            connectivity[edge.target_node_uuid] = (
                connectivity.get(edge.target_node_uuid, 0) + 1
            )

        sample_edges = sorted(
            self.graph.edges,
            key=lambda edge: connectivity.get(edge.source_node_uuid, 0)
            + connectivity.get(edge.target_node_uuid, 0),
            reverse=True,
        )[:10]

        sample_facts = []
        for edge in sample_edges:
            source_node = self.graph.get_node_by_uuid(edge.source_node_uuid)
            target_node = self.graph.get_node_by_uuid(edge.target_node_uuid)
            sample_facts.append(
                {
                    "uuid": edge.uuid,
                    "fact": edge.fact,
                    "source": source_node.name
                    if source_node
                    else edge.source_node_uuid,
                    "target": target_node.name
                    if target_node
                    else edge.target_node_uuid,
                    "relationship_type": edge.name,
                }
            )

        key_entities = []
        for node_uuid, node in self.graph.nodes.items():
            key_entities.append(
                {
                    "uuid": node_uuid,
                    "name": node.name,
                    "type": self._node_type(node),
                    "edge_count": connectivity.get(node_uuid, 0),
                }
            )
        key_entities.sort(key=lambda item: item["edge_count"], reverse=True)

        ontology_entity_types = [
            entry.get("name", "")
            for entry in self.graph.ontology.entity_types
            if isinstance(entry, dict)
        ]
        ontology_relationship_types = [
            entry.get("name", "")
            for entry in self.graph.ontology.relationship_types
            if isinstance(entry, dict)
        ]

        return {
            "graph_stats": {
                "total_nodes": len(self.graph.nodes),
                "total_edges": len(self.graph.edges),
                "entity_type_distribution": node_type_distribution,
                "relationship_type_distribution": relationship_type_distribution,
            },
            "sample_facts": sample_facts,
            "key_entities": key_entities[:10],
            "ontology_summary": {
                "entity_types": sorted(
                    {value for value in ontology_entity_types if value}
                ),
                "relationship_types": sorted(
                    {value for value in ontology_relationship_types if value}
                ),
            },
        }

    def get_simulation_posts(
        self,
        platform: str | None = None,
        agent_name: str | None = None,
        round_num: int | None = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Search simulation posts/actions."""
        records = self._load_simulation_log()

        filtered: List[Dict[str, Any]] = []
        for item in records:
            item_platform = str(item.get("platform", ""))
            item_agent = str(item.get("agent", item.get("agent_name", "")))
            item_round = item.get("round", item.get("round_num"))

            if platform and item_platform.casefold() != platform.casefold():
                continue
            if agent_name and item_agent.casefold() != agent_name.casefold():
                continue
            if round_num is not None and item_round != round_num:
                continue

            filtered.append(
                {
                    "round": item_round,
                    "platform": item_platform,
                    "agent": item_agent,
                    "action": item.get("action", item.get("action_type", "")),
                    "content": item.get("content", item.get("text", "")),
                }
            )

        capped = filtered[: max(0, limit)]
        return {"posts": capped, "total": len(filtered)}

    def _load_graph(self) -> None:
        """Load graph.json into self.graph."""
        graph_path = JsonStore.project_path(self.project_id, "graph", "graph.json")
        raw = JsonStore.load(graph_path)
        if not raw:
            raw = {
                "graph_id": self.project_id,
                "nodes": {},
                "edges": [],
                "ontology": {"entity_types": [], "relationship_types": []},
            }
        raw.setdefault("graph_id", self.project_id)
        raw.setdefault("nodes", {})
        raw.setdefault("edges", [])
        raw.setdefault("ontology", {"entity_types": [], "relationship_types": []})
        self.graph = KnowledgeGraph.from_dict(raw)

    def _score_text(self, text: str, keywords: List[str]) -> int:
        """Score text relevance against query keywords."""
        if not text or not keywords:
            return 0

        normalized_text = text.casefold()
        score = 0
        full_phrase = " ".join(keywords).strip()
        if full_phrase and full_phrase in normalized_text:
            score += 100

        for keyword in keywords:
            if keyword and keyword in normalized_text:
                score += 10
        return score

    def _tokenize_query(self, query: str) -> List[str]:
        """Split query into search keywords."""
        tokens = re.findall(r"[a-z0-9]+", query.casefold())
        return [
            token
            for token in tokens
            if len(token) >= 2 and token not in self._STOPWORDS
        ]

    def _build_relationship_chain(
        self, start_node: str, max_depth: int = 3
    ) -> List[Dict[str, Any]]:
        """BFS from start_node to build relationship chains."""
        start = self.graph.get_node_by_name(start_node)
        if start is None:
            return []

        chains: List[Dict[str, Any]] = []
        queue: List[tuple[str, List[str], set[str], int]] = [
            (start.uuid, [start.name], {start.uuid}, 0)
        ]

        while queue:
            current_uuid, current_chain, visited, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            node_edges = self.graph.get_edges_for_node(current_uuid)
            for edge in node_edges:
                if edge.source_node_uuid == current_uuid:
                    next_uuid = edge.target_node_uuid
                    direction = edge.name
                else:
                    next_uuid = edge.source_node_uuid
                    direction = f"reverse:{edge.name}"

                if next_uuid in visited:
                    continue

                next_node = self.graph.get_node_by_uuid(next_uuid)
                if next_node is None:
                    continue

                new_chain = [*current_chain, direction, next_node.name]
                chains.append({"chain": new_chain, "length": (len(new_chain) - 1) // 2})
                queue.append(
                    (next_uuid, new_chain, set(visited) | {next_uuid}, depth + 1)
                )

                if len(chains) >= 20:
                    return chains

        return chains

    def _load_simulation_log(self) -> List[Dict[str, Any]]:
        """Load simulation action log from JSONL file."""
        log_path = PROJECTS_DIR / self.project_id / "simulation" / "actions.jsonl"
        records = JsonStore.read_jsonl(log_path)
        if records:
            return records

        path_obj = Path(log_path)
        if not path_obj.exists():
            return []

        fallback_records: List[Dict[str, Any]] = []
        try:
            with path_obj.open("r", encoding="utf-8") as handle:
                for line in handle:
                    value = line.strip()
                    if not value:
                        continue
                    try:
                        parsed = json.loads(value)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed, dict):
                        fallback_records.append(parsed)
        except OSError:
            return []

        return fallback_records

    def _edge_to_dict(self, edge: GraphEdge) -> Dict[str, Any]:
        source_node = self.graph.get_node_by_uuid(edge.source_node_uuid)
        target_node = self.graph.get_node_by_uuid(edge.target_node_uuid)
        return {
            "uuid": edge.uuid,
            "name": edge.name,
            "fact": edge.fact,
            "source_node": source_node.name if source_node else edge.source_node_uuid,
            "target_node": target_node.name if target_node else edge.target_node_uuid,
            "valid_at": edge.valid_at,
            "invalid_at": edge.invalid_at,
            "expired_at": edge.expired_at,
        }

    def _node_type(self, node: GraphNode | None) -> str:
        if node is None:
            return "Unknown"
        if node.labels:
            return node.labels[0]
        return "Unknown"

    def _is_edge_valid_at(self, edge: GraphEdge, time_filter: str) -> bool:
        time_key = time_filter.strip()
        if not time_key:
            return True

        lower_ok = edge.valid_at is None or edge.valid_at <= time_key

        upper_bound = (
            edge.invalid_at if edge.invalid_at is not None else edge.expired_at
        )
        upper_ok = upper_bound is None or time_key < upper_bound

        return lower_ok and upper_ok
