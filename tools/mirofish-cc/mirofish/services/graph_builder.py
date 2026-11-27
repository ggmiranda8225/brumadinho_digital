from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from mirofish.config import PROJECTS_DIR
from mirofish.models.graph import GraphEdge, GraphNode, KnowledgeGraph, Ontology
from mirofish.store.json_store import JsonStore


class GraphBuilder:
    @staticmethod
    def save_ontology(project_id: str, ontology_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and save ontology JSON."""
        entity_types = ontology_data.get("entity_types")
        relationship_types = ontology_data.get("relationship_types")

        if not isinstance(entity_types, list):
            raise ValueError("entity_types must be a list")
        if not isinstance(relationship_types, list):
            raise ValueError("relationship_types must be a list")

        for item in entity_types:
            if not isinstance(item, dict):
                raise ValueError("Each entity type must be an object")
            if not item.get("name"):
                raise ValueError("Each entity type must include 'name'")
            attributes = item.get("attributes", [])
            if not isinstance(attributes, list):
                raise ValueError("Entity type attributes must be a list")

        for item in relationship_types:
            if not isinstance(item, dict):
                raise ValueError("Each relationship type must be an object")
            if not item.get("name"):
                raise ValueError("Each relationship type must include 'name'")

        graph_dir = GraphBuilder._graph_dir(project_id)
        graph_dir.mkdir(parents=True, exist_ok=True)

        JsonStore.save(graph_dir / "ontology.json", ontology_data)

        graph = KnowledgeGraph(
            graph_id=project_id,
            nodes={},
            edges=[],
            ontology=Ontology.from_dict(ontology_data),
        )
        JsonStore.save(graph_dir / "graph.json", graph.to_dict())

        return {
            "entity_type_count": len(entity_types),
            "relationship_type_count": len(relationship_types),
        }

    @staticmethod
    def add_extracted_data(
        project_id: str,
        entities: List[Dict],
        relationships: List[Dict],
    ) -> Dict[str, Any]:
        """Add Claude-extracted entities and relationships to the graph."""
        graph = GraphBuilder.get_graph(project_id)

        new_entities = 0
        merged_entities = 0
        new_edges = 0
        skipped_edges = 0

        for entity in entities:
            name = str(entity.get("name", "")).strip()
            entity_type = str(entity.get("type", "")).strip()
            if not name:
                continue

            node_uuid = GraphBuilder._resolve_entity_name(graph, name)
            if node_uuid is not None:
                existing = graph.nodes[node_uuid]
                graph.nodes[node_uuid] = GraphBuilder._deduplicate_entity(existing, entity)
                merged_entities += 1
                continue

            labels: List[str] = []
            if entity_type:
                labels.append(entity_type)

            node = GraphNode(
                uuid=str(uuid.uuid4()),
                name=name,
                labels=labels,
                summary=str(entity.get("summary", "")).strip(),
                attributes=dict(entity.get("attributes", {}) or {}),
            )
            graph.add_node(node)
            new_entities += 1

        for relationship in relationships:
            source_name = str(relationship.get("source", "")).strip()
            target_name = str(relationship.get("target", "")).strip()
            rel_type = str(relationship.get("type", "")).strip()
            fact = str(relationship.get("fact", "")).strip()
            valid_at_raw = relationship.get("valid_at")
            valid_at = str(valid_at_raw).strip() if valid_at_raw not in (None, "") else None

            if not source_name or not target_name or not rel_type:
                skipped_edges += 1
                continue

            source_uuid = GraphBuilder._resolve_entity_name(graph, source_name)
            target_uuid = GraphBuilder._resolve_entity_name(graph, target_name)

            if source_uuid is None or target_uuid is None:
                skipped_edges += 1
                continue

            edge = GraphEdge(
                uuid=str(uuid.uuid4()),
                name=rel_type,
                fact=fact,
                source_node_uuid=source_uuid,
                target_node_uuid=target_uuid,
                valid_at=valid_at,
            )
            graph.add_edge(edge)
            new_edges += 1

        JsonStore.save(GraphBuilder._graph_path(project_id), graph.to_dict())

        return {
            "new_entities": new_entities,
            "merged_entities": merged_entities,
            "new_edges": new_edges,
            "skipped_edges": skipped_edges,
        }

    @staticmethod
    def finalize(project_id: str) -> Dict[str, Any]:
        """Finalize graph construction."""
        graph = GraphBuilder.get_graph(project_id)

        for node in graph.nodes.values():
            connected_edges = graph.get_edges_for_node(node.uuid)
            if not connected_edges:
                continue

            unique_facts: List[str] = []
            seen: set[str] = set()
            for edge in connected_edges:
                fact = edge.fact.strip()
                if not fact:
                    continue
                key = fact.casefold()
                if key in seen:
                    continue
                seen.add(key)
                unique_facts.append(fact)

            stitched = "; ".join(unique_facts[:5])
            if not stitched:
                continue

            existing = node.summary.strip()
            if not existing:
                node.summary = stitched
            elif stitched.casefold() not in existing.casefold():
                node.summary = f"{existing}; {stitched}".strip("; ")

        JsonStore.save(GraphBuilder._graph_path(project_id), graph.to_dict())

        return GraphBuilder._compute_stats_from_graph(graph)

    @staticmethod
    def get_stats(project_id: str) -> Dict[str, Any]:
        """Return graph statistics without loading full graph."""
        payload = JsonStore.load(GraphBuilder._graph_path(project_id))
        if not payload:
            return {
                "total_nodes": 0,
                "total_edges": 0,
                "entity_type_distribution": {},
                "relationship_type_distribution": {},
            }

        nodes_raw = payload.get("nodes", {})
        edges_raw = payload.get("edges", [])

        entity_type_distribution: Dict[str, int] = {}
        if isinstance(nodes_raw, dict):
            node_values = nodes_raw.values()
        else:
            node_values = []

        for node_data in node_values:
            if not isinstance(node_data, dict):
                continue
            labels = node_data.get("labels", [])
            node_type = str(labels[0]).strip() if isinstance(labels, list) and labels else "Unknown"
            entity_type_distribution[node_type] = entity_type_distribution.get(node_type, 0) + 1

        relationship_type_distribution: Dict[str, int] = {}
        if isinstance(edges_raw, list):
            for edge_data in edges_raw:
                if not isinstance(edge_data, dict):
                    continue
                edge_type = str(edge_data.get("name", "Unknown")).strip() or "Unknown"
                relationship_type_distribution[edge_type] = relationship_type_distribution.get(edge_type, 0) + 1

        return {
            "total_nodes": len(nodes_raw) if isinstance(nodes_raw, dict) else 0,
            "total_edges": len(edges_raw) if isinstance(edges_raw, list) else 0,
            "entity_type_distribution": entity_type_distribution,
            "relationship_type_distribution": relationship_type_distribution,
        }

    @staticmethod
    def get_graph(project_id: str) -> KnowledgeGraph:
        """Load and return the full knowledge graph."""
        payload = JsonStore.load(GraphBuilder._graph_path(project_id))
        if not payload:
            ontology_payload = JsonStore.load(GraphBuilder._graph_dir(project_id) / "ontology.json")
            return KnowledgeGraph(
                graph_id=project_id,
                nodes={},
                edges=[],
                ontology=Ontology.from_dict(ontology_payload),
            )
        return KnowledgeGraph.from_dict(payload)

    @staticmethod
    def _deduplicate_entity(existing: GraphNode, new_data: Dict) -> GraphNode:
        """Merge new entity data into existing node."""
        labels = list(existing.labels)
        incoming_type = str(new_data.get("type", "")).strip()
        if incoming_type and incoming_type not in labels:
            labels.append(incoming_type)

        merged_attributes = dict(existing.attributes)
        incoming_attributes = dict(new_data.get("attributes", {}) or {})
        for key, value in incoming_attributes.items():
            if value not in (None, "", [], {}):
                merged_attributes[key] = value

        summary = existing.summary.strip()
        incoming_summary = str(new_data.get("summary", "")).strip()
        if incoming_summary and incoming_summary.casefold() not in summary.casefold():
            summary = f"{summary}; {incoming_summary}".strip("; ") if summary else incoming_summary

        return GraphNode(
            uuid=existing.uuid,
            name=existing.name,
            labels=labels,
            summary=summary,
            attributes=merged_attributes,
        )

    @staticmethod
    def _resolve_entity_name(graph: KnowledgeGraph, name: str) -> Optional[str]:
        """Find node UUID by name (case-insensitive, fuzzy)."""
        lookup = name.strip()
        if not lookup:
            return None

        for node_uuid, node in graph.nodes.items():
            if node.name.strip() == lookup:
                return node_uuid

        lookup_folded = lookup.casefold()
        for node_uuid, node in graph.nodes.items():
            if node.name.strip().casefold() == lookup_folded:
                return node_uuid

        for node_uuid, node in graph.nodes.items():
            candidate = node.name.strip().casefold()
            if lookup_folded in candidate or candidate in lookup_folded:
                return node_uuid

        return None

    @staticmethod
    def _compute_stats_from_graph(graph: KnowledgeGraph) -> Dict[str, Any]:
        entity_type_distribution: Dict[str, int] = {}
        for node in graph.nodes.values():
            node_type = node.labels[0] if node.labels else "Unknown"
            entity_type_distribution[node_type] = entity_type_distribution.get(node_type, 0) + 1

        relationship_type_distribution: Dict[str, int] = {}
        for edge in graph.edges:
            rel_type = edge.name.strip() or "Unknown"
            relationship_type_distribution[rel_type] = relationship_type_distribution.get(rel_type, 0) + 1

        return {
            "total_nodes": len(graph.nodes),
            "total_edges": len(graph.edges),
            "entity_type_distribution": entity_type_distribution,
            "relationship_type_distribution": relationship_type_distribution,
        }

    @staticmethod
    def _graph_dir(project_id: str):
        return PROJECTS_DIR / project_id / "graph"

    @staticmethod
    def _graph_path(project_id: str):
        return GraphBuilder._graph_dir(project_id) / "graph.json"
