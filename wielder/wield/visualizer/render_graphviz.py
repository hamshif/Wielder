"""DOT rendering for Wielder documentation graphs."""

from __future__ import annotations

import re

from wielder.wield.visualizer.graph_model import WDocGraph


def _dot_id(value: str) -> str:
    clean = re.sub(r"[^0-9A-Za-z_]", "_", value)
    if not clean:
        return "node"
    if clean[0].isdigit():
        return f"n_{clean}"
    return clean


def _quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def render_dot(graph: WDocGraph) -> str:
    lines = [
        "digraph WDocGraph {",
        "  rankdir=TB;",
        '  graph [fontname="Arial"];',
        '  node [shape=box, style="rounded,filled", fillcolor="#f7f7f7", fontname="Arial"];',
        '  edge [fontname="Arial"];',
    ]
    node_id_map = {node_id: _dot_id(node_id) for node_id in graph.nodes}

    for node in graph.nodes.values():
        label = f"{node.label}\\n{node.kind}"
        lines.append(f'  {node_id_map[node.id]} [label="{_quote(label)}"];')

    for edge in graph.edges:
        edge_label = f' [label="{_quote(edge.label)}"]' if edge.label else ""
        lines.append(f"  {node_id_map[edge.source]} -> {node_id_map[edge.target]}{edge_label};")

    lines.append("}")
    return "\n".join(lines) + "\n"
