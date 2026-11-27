from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Ontology:
    entity_types: list[dict[str, Any]] = field(default_factory=list)
    relationship_types: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_types": self.entity_types,
            "relationship_types": self.relationship_types,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Ontology":
        return cls(
            entity_types=list(data.get("entity_types", [])),
            relationship_types=list(data.get("relationship_types", [])),
        )


@dataclass
class GraphNode:
    uuid: str
    name: str
    labels: list[str] = field(default_factory=list)
    summary: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphNode":
        return cls(
            uuid=data["uuid"],
            name=data.get("name", ""),
            labels=list(data.get("labels", [])),
            summary=data.get("summary", ""),
            attributes=dict(data.get("attributes", {})),
        )


@dataclass
class GraphEdge:
    uuid: str
    name: str
    fact: str
    source_node_uuid: str
    target_node_uuid: str
    valid_at: str | None = None
    invalid_at: str | None = None
    expired_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "fact": self.fact,
            "source_node_uuid": self.source_node_uuid,
            "target_node_uuid": self.target_node_uuid,
            "valid_at": self.valid_at,
            "invalid_at": self.invalid_at,
            "expired_at": self.expired_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphEdge":
        return cls(
            uuid=data["uuid"],
            name=data.get("name", ""),
            fact=data.get("fact", ""),
            source_node_uuid=data["source_node_uuid"],
            target_node_uuid=data["target_node_uuid"],
            valid_at=data.get("valid_at"),
            invalid_at=data.get("invalid_at"),
            expired_at=data.get("expired_at"),
        )


@dataclass
class KnowledgeGraph:
    graph_id: str
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    ontology: Ontology = field(default_factory=Ontology)

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.uuid] = node

    def add_edge(self, edge: GraphEdge) -> None:
        if edge.source_node_uuid not in self.nodes:
            raise ValueError(f"Source node not found: {edge.source_node_uuid}")
        if edge.target_node_uuid not in self.nodes:
            raise ValueError(f"Target node not found: {edge.target_node_uuid}")
        self.edges.append(edge)

    def get_node_by_name(self, name: str) -> GraphNode | None:
        lookup = name.strip().casefold()
        for node in self.nodes.values():
            if node.name.strip().casefold() == lookup:
                return node
        return None

    def get_node_by_uuid(self, node_uuid: str) -> GraphNode | None:
        return self.nodes.get(node_uuid)

    def get_edges_for_node(self, node_uuid: str) -> list[GraphEdge]:
        return [
            edge
            for edge in self.edges
            if edge.source_node_uuid == node_uuid or edge.target_node_uuid == node_uuid
        ]

    def get_neighbors(self, node_uuid: str) -> list[GraphNode]:
        neighbors: dict[str, GraphNode] = {}
        for edge in self.get_edges_for_node(node_uuid):
            if edge.source_node_uuid == node_uuid:
                neighbor_uuid = edge.target_node_uuid
            else:
                neighbor_uuid = edge.source_node_uuid

            neighbor = self.get_node_by_uuid(neighbor_uuid)
            if neighbor is not None:
                neighbors[neighbor.uuid] = neighbor

        return list(neighbors.values())

    def search_facts(self, query: str) -> list[GraphEdge]:
        normalized = query.strip().casefold()
        if not normalized:
            return []

        keywords = [token for token in normalized.split() if token]
        matched_edges: list[GraphEdge] = []
        for edge in self.edges:
            fact = edge.fact.casefold()
            if all(keyword in fact for keyword in keywords):
                matched_edges.append(edge)

        return matched_edges

    def get_stats(self) -> dict[str, int]:
        return {
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "entity_type_count": len(self.ontology.entity_types),
            "relationship_type_count": len(self.ontology.relationship_types),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "nodes": {node_uuid: node.to_dict() for node_uuid, node in self.nodes.items()},
            "edges": [edge.to_dict() for edge in self.edges],
            "ontology": self.ontology.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeGraph":
        nodes_raw = dict(data.get("nodes", {}))
        edges_raw = list(data.get("edges", []))

        nodes = {node_uuid: GraphNode.from_dict(node_data) for node_uuid, node_data in nodes_raw.items()}
        edges = [GraphEdge.from_dict(edge_data) for edge_data in edges_raw]
        ontology = Ontology.from_dict(dict(data.get("ontology", {})))

        return cls(
            graph_id=data["graph_id"],
            nodes=nodes,
            edges=edges,
            ontology=ontology,
        )
