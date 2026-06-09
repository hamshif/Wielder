"""HTML report rendering for Wielder documentation graphs."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wielder.wield.visualizer.graph_model import WDocGraph
from wielder.wield.visualizer.render_mermaid import render_mermaid_flowchart


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _items_from_source(source_payload: dict[str, Any]) -> list[dict[str, Any]]:
    items_page = source_payload.get("items_page") or {}
    items = items_page.get("items") or []
    return [dict(item) for item in items]


def _column_value_text(item: dict[str, Any], column_id: str) -> str:
    for column_value in item.get("column_values") or []:
        if column_value.get("id") == column_id:
            return str(column_value.get("text") or "")
    return ""


def render_html_report(
    graph: WDocGraph,
    *,
    source_payload: dict[str, Any],
    title: str | None = None,
    dot_svg_path: str | None = None,
    json_path: str | None = None,
) -> str:
    report_title = title or graph.label
    generated_at = datetime.now(timezone.utc).isoformat()
    mermaid = render_mermaid_flowchart(graph)
    columns = list(source_payload.get("columns") or [])
    groups = list(source_payload.get("groups") or [])
    items = _items_from_source(source_payload)
    workspace = source_payload.get("workspace") or {}

    status_column = next((column for column in columns if column.get("id") == "status"), None)
    owner_column = next((column for column in columns if column.get("id") == "person"), None)

    item_rows = []
    for item in items:
        group = item.get("group") or {}
        subitems = item.get("subitems") or []
        item_rows.append(
            "<tr>"
            f"<td>{_escape(item.get('name') or item.get('id'))}</td>"
            f"<td>{_escape(group.get('title') or group.get('id') or '')}</td>"
            f"<td>{_escape(_column_value_text(item, str(status_column.get('id'))) if status_column else '')}</td>"
            f"<td>{_escape(_column_value_text(item, str(owner_column.get('id'))) if owner_column else '')}</td>"
            f"<td>{len(subitems)}</td>"
            "</tr>"
        )

    column_rows = [
        "<tr>"
        f"<td>{_escape(column.get('title') or column.get('id'))}</td>"
        f"<td>{_escape(column.get('id'))}</td>"
        f"<td>{_escape(column.get('type'))}</td>"
        "</tr>"
        for column in columns
    ]
    group_rows = [
        "<tr>"
        f"<td>{_escape(group.get('title') or group.get('id'))}</td>"
        f"<td>{_escape(group.get('id'))}</td>"
        "</tr>"
        for group in groups
    ]

    svg_panel = (
        f'<div class="graph-box graph-box-svg"><img src="{_escape(Path(dot_svg_path).name)}" alt="Board Graph SVG" /></div>'
        if dot_svg_path
        else '<div class="graph-box graph-box-empty">Graphviz SVG is unavailable. Install Graphviz and rerun the report.</div>'
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_escape(report_title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --text: #17202a;
      --muted: #586575;
      --line: #d8dee8;
      --panel: #f7f9fc;
      --accent: #1f6feb;
    }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      color: var(--text);
      background: white;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 28px;
    }}
    h1, h2 {{
      margin: 0 0 12px;
      letter-spacing: 0;
    }}
    h1 {{
      font-size: 30px;
    }}
    h2 {{
      font-size: 20px;
      margin-top: 28px;
      padding-top: 18px;
      border-top: 1px solid var(--line);
    }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
      margin: 18px 0 8px;
    }}
    .metric {{
      border: 1px solid var(--line);
      background: var(--panel);
      padding: 10px 12px;
      border-radius: 6px;
    }}
    .metric strong {{
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 4px;
      text-transform: uppercase;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 8px;
      font-size: 14px;
    }}
    th, td {{
      text-align: left;
      border-bottom: 1px solid var(--line);
      padding: 8px 10px;
      vertical-align: top;
    }}
    th {{
      background: var(--panel);
      color: #2f3b4a;
    }}
    pre {{
      overflow: auto;
      background: #0f1720;
      color: #e6edf3;
      padding: 16px;
      border-radius: 6px;
    }}
    .mermaid {{
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: white;
      overflow: auto;
    }}
    .graph-box {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: white;
      padding: 14px;
      overflow: auto;
      min-height: 240px;
      max-height: 760px;
    }}
    .graph-box img {{
      display: block;
      max-width: none;
      min-width: 100%;
      height: auto;
    }}
    .graph-box-empty {{
      color: var(--muted);
      background: var(--panel);
    }}
    a {{
      color: var(--accent);
    }}
  </style>
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";
    mermaid.initialize({{ startOnLoad: true, securityLevel: "loose" }});
  </script>
</head>
<body>
<main>
  <h1>{_escape(report_title)}</h1>
  <p>Generated at {_escape(generated_at)} from Monday board structure.</p>

  <section class="meta">
    <div class="metric"><strong>Workspace</strong>{_escape(workspace.get("name") or "Unknown")} ({_escape(workspace.get("id") or "unknown")})</div>
    <div class="metric"><strong>Board</strong>{_escape(source_payload.get("name") or graph.label)} ({_escape(source_payload.get("id") or "unknown")})</div>
    <div class="metric"><strong>Groups</strong>{len(groups)}</div>
    <div class="metric"><strong>Columns</strong>{len(columns)}</div>
    <div class="metric"><strong>Items Sampled</strong>{len(items)}</div>
    <div class="metric"><strong>Graph</strong>{len(graph.nodes)} nodes, {len(graph.edges)} edges</div>
  </section>

  <h2>Board Graph</h2>
  {svg_panel}

  <h2>Mermaid Graph</h2>
  <div class="mermaid">
{_escape(mermaid)}
  </div>

  <h2>Items</h2>
  <table>
    <thead><tr><th>Item</th><th>Group</th><th>Status</th><th>Owner</th><th>Subitems</th></tr></thead>
    <tbody>
      {''.join(item_rows) or '<tr><td colspan="5">No sampled items.</td></tr>'}
    </tbody>
  </table>

  <h2>Groups</h2>
  <table>
    <thead><tr><th>Group</th><th>ID</th></tr></thead>
    <tbody>
      {''.join(group_rows) or '<tr><td colspan="2">No groups.</td></tr>'}
    </tbody>
  </table>

  <h2>Columns</h2>
  <table>
    <thead><tr><th>Column</th><th>ID</th><th>Type</th></tr></thead>
    <tbody>
      {''.join(column_rows) or '<tr><td colspan="3">No columns.</td></tr>'}
    </tbody>
  </table>
</main>
</body>
</html>
"""
