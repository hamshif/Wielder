from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from pyhocon import ConfigFactory, ConfigTree


def _to_native(value: Any) -> Any:
    if isinstance(value, ConfigTree):
        return {k: _to_native(value[k]) for k in value}
    if isinstance(value, list):
        return [_to_native(item) for item in value]
    return value


def _quote(text: Any) -> str:
    raw = str(text).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{raw}"'


def load_hocon_graph(source: str | Path | ConfigTree, graph_key: str = "graph") -> dict[str, Any]:
    if isinstance(source, ConfigTree):
        conf = source
    else:
        source_text = str(source)
        if "\n" in source_text or "{" in source_text:
            conf = ConfigFactory.parse_string(source_text, resolve=True)
        else:
            conf = ConfigFactory.parse_file(source_text, resolve=True)

    if graph_key not in conf:
        raise AttributeError(f"Missing '{graph_key}' root in graph configuration.")

    graph = _to_native(conf[graph_key])
    if "name" not in graph:
        raise AttributeError("Graph schema requires 'graph.name'.")
    if "nodes" not in graph:
        raise AttributeError("Graph schema requires 'graph.nodes'.")
    if "edges" not in graph:
        raise AttributeError("Graph schema requires 'graph.edges'.")

    return graph


def hocon_graph_to_dot(source: str | Path | ConfigTree, graph_key: str = "graph") -> str:
    graph = load_hocon_graph(source, graph_key=graph_key)
    graph_name = str(graph["name"])
    rankdir = str(graph.get("rankdir", "TB"))
    nodesep = str(graph.get("nodesep", "0.8"))
    ranksep = str(graph.get("ranksep", "1.0"))
    splines = str(graph.get("splines", "ortho"))

    lines: list[str] = [f"digraph {graph_name} {{"]
    lines.append(f"  rankdir={rankdir}")
    lines.append(f"  nodesep={nodesep}")
    lines.append(f"  ranksep={ranksep}")
    lines.append(f"  splines={splines}")
    lines.append("  node [shape=box style=\"rounded,filled\" fillcolor=\"#E3F2FD\"]")

    for node in graph["nodes"]:
        if "id" not in node:
            raise AttributeError("Each graph node requires 'id'.")
        if "label" not in node:
            raise AttributeError(f"Graph node {node['id']} requires 'label'.")
        node_id = node["id"]
        attrs = {"label": node["label"]}
        attrs.update({k: v for k, v in node.items() if k not in {"id"}})
        attrs_text = ", ".join(f"{k}={_quote(v)}" for k, v in attrs.items())
        lines.append(f"  {node_id} [{attrs_text}]")

    for edge in graph["edges"]:
        if "source" not in edge:
            raise AttributeError("Each graph edge requires 'source'.")
        if "target" not in edge:
            raise AttributeError("Each graph edge requires 'target'.")
        source_id = edge["source"]
        target_id = edge["target"]
        attrs = {k: v for k, v in edge.items() if k not in {"source", "target"}}
        if attrs:
            attrs_text = ", ".join(f"{k}={_quote(v)}" for k, v in attrs.items())
            lines.append(f"  {source_id} -> {target_id} [{attrs_text}]")
        else:
            lines.append(f"  {source_id} -> {target_id}")

    lines.append("}")
    return "\n".join(lines) + "\n"


def render_hocon_graph_to_sink(
    source: str | Path | ConfigTree,
    sink: str | Path,
    graph_key: str = "graph",
) -> Path:
    sink_path = Path(sink)
    sink_path.parent.mkdir(parents=True, exist_ok=True)
    dot = hocon_graph_to_dot(source, graph_key=graph_key)

    if sink_path.suffix.lower() in {"", ".dot"}:
        sink_dot = sink_path if sink_path.suffix.lower() == ".dot" else sink_path.with_suffix(".dot")
        sink_dot.write_text(dot, encoding="utf-8")
        return sink_dot

    sink_format = sink_path.suffix.lower().lstrip(".")
    supported_formats = {"png", "svg", "pdf"}
    if sink_format not in supported_formats:
        raise ValueError(f"Unsupported sink format '.{sink_format}'. Use .dot, .png, .svg, or .pdf.")

    dot_input = sink_path.with_suffix(f"{sink_path.suffix}.dot")
    dot_input.write_text(dot, encoding="utf-8")

    try:
        subprocess.run(
            ["dot", f"-T{sink_format}", str(dot_input), "-o", str(sink_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        if dot_input.exists():
            dot_input.unlink()

    return sink_path
