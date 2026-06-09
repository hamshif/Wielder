from wielder.wield.visualizer import WDocGraph, render_dot, render_html_report, render_mermaid_flowchart


def _sample_graph() -> tuple[WDocGraph, dict]:
    board = {
        "id": "123",
        "name": "Empiric Data Ingestion",
        "workspace": {"id": "w1", "name": "Engineering"},
        "groups": [{"id": "topics", "title": "Topics"}],
        "columns": [
            {"id": "status", "title": "Status", "type": "status"},
            {"id": "person", "title": "Owner", "type": "people"},
        ],
        "items_page": {
            "items": [
                {
                    "id": "i1",
                    "name": "Visualize Monday board",
                    "group": {"id": "topics", "title": "Topics"},
                    "column_values": [
                        {"id": "status", "text": "In Progress", "type": "status"},
                        {"id": "person", "text": "Gideon", "type": "people"},
                    ],
                    "subitems": [{"id": "s1", "name": "HTML report"}],
                }
            ]
        },
    }
    graph = WDocGraph(id="sample", label="Sample")
    workspace = graph.add_node("workspace:w1", label="Engineering", kind="monday.workspace")
    board_node = graph.add_node("board:123", label="Empiric Data Ingestion", kind="monday.board")
    item = graph.add_node("item:i1", label="Visualize Monday board", kind="monday.item")
    graph.add_edge(workspace, board_node, label="contains board")
    graph.add_edge(board_node, item, label="contains item")
    return graph, board


def test_visualizer_renders_text_and_html_reports():
    graph, board = _sample_graph()

    mermaid = render_mermaid_flowchart(graph)
    dot = render_dot(graph)
    html = render_html_report(graph, source_payload=board, json_path="/tmp/sample.json")

    assert "flowchart TD" in mermaid
    assert "digraph WDocGraph" in dot
    assert "Monday Board Report" not in html
    assert "Empiric Data Ingestion" in html
    assert "Visualize Monday board" in html
    assert "Board Graph" in html
    assert "Mermaid Graph" in html
    assert "Open raw JSON" not in html
    assert "Board Payload" not in html
    assert "Mermaid Source" not in html
