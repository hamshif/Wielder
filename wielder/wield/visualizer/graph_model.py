"""Provider-neutral documentation graph model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WDocGraphNode:
    id: str
    label: str
    kind: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WDocGraphEdge:
    source: str
    target: str
    label: str = ""


@dataclass
class WDocGraph:
    id: str
    label: str
    nodes: dict[str, WDocGraphNode] = field(default_factory=dict)
    edges: list[WDocGraphEdge] = field(default_factory=list)

    def add_node(
        self,
        node_id: str,
        *,
        label: str,
        kind: str,
        raw: dict[str, Any] | None = None,
    ) -> str:
        self.nodes[node_id] = WDocGraphNode(
            id=node_id,
            label=label,
            kind=kind,
            raw=raw or {},
        )
        return node_id

    def add_edge(self, source: str, target: str, *, label: str = "") -> None:
        if source not in self.nodes:
            raise ValueError(f"Source node [{source}] is not present in graph [{self.id}].")
        if target not in self.nodes:
            raise ValueError(f"Target node [{target}] is not present in graph [{self.id}].")
        self.edges.append(WDocGraphEdge(source=source, target=target, label=label))

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "nodes": [
                {
                    "id": node.id,
                    "label": node.label,
                    "kind": node.kind,
                    "raw": node.raw,
                }
                for node in self.nodes.values()
            ],
            "edges": [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "label": edge.label,
                }
                for edge in self.edges
            ],
        }
