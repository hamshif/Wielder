"""Mermaid rendering for Wielder documentation graphs."""

from __future__ import annotations

import re

from wielder.wield.visualizer.graph_model import WDocGraph


def _mermaid_id(value: str) -> str:
    clean = re.sub(r"[^0-9A-Za-z_]", "_", value)
    if not clean:
        return "node"
    if clean[0].isdigit():
        return f"n_{clean}"
    return clean


def _label(value: str) -> str:
    return value.replace('"', "'").replace("\n", " ")


def render_mermaid_flowchart(graph: WDocGraph, *, direction: str = "TD") -> str:
    lines = [f"flowchart {direction}"]
    node_id_map = {node_id: _mermaid_id(node_id) for node_id in graph.nodes}

    for node in graph.nodes.values():
        lines.append(
            f'  {node_id_map[node.id]}["{_label(node.label)}<br/><small>{_label(node.kind)}</small>"]'
        )

    for edge in graph.edges:
        label = f"|{_label(edge.label)}|" if edge.label else ""
        lines.append(f"  {node_id_map[edge.source]} -->{label} {node_id_map[edge.target]}")

    return "\n".join(lines) + "\n"
