"""Graphviz CLI helpers for Wielder documentation graphs."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from wielder.wield.visualizer.graph_model import WDocGraph
from wielder.wield.visualizer.render_graphviz import render_dot


def render_graphviz_file(graph: WDocGraph, output_path: str | Path, *, output_format: str = "svg") -> Path:
    dot_bin = shutil.which("dot")
    if not dot_bin:
        raise RuntimeError(
            "Graphviz `dot` is not available on PATH. "
            "Run Wielder/wielder/scripts/install_visualizer_wsl_ubuntu.sh."
        )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [dot_bin, f"-T{output_format}", "-o", output.as_posix()],
        input=render_dot(graph),
        text=True,
        check=True,
    )
    return output
