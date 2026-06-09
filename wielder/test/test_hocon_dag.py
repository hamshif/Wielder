from pathlib import Path

from wielder.visual.hocon_dag import hocon_graph_to_dot, render_hocon_graph_to_sink


def test_hocon_graph_to_dot_contains_nodes_and_edges():
    conf_text = """
    graph {
      name = "simple_test"
      rankdir = "TB"
      nodes = [
        { id: "A", label: "Start" }
        { id: "B", label: "Finish" }
      ]
      edges = [
        { source: "A", target: "B", label: "go" }
      ]
    }
    """
    dot = hocon_graph_to_dot(conf_text)
    assert "digraph simple_test" in dot
    assert "A -> B" in dot
    assert 'label="go"' in dot


def test_render_hocon_graph_to_dot_sink(tmp_path: Path):
    conf_text = """
    graph {
      name = "sink_test"
      nodes = [
        { id: "N1", label: "Node 1" }
      ]
      edges = []
    }
    """
    sink = tmp_path / "dag_schema.dot"
    output_path = render_hocon_graph_to_sink(conf_text, sink)
    assert output_path == sink
    assert sink.exists()
    assert "digraph sink_test" in sink.read_text(encoding="utf-8")
