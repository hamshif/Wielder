from __future__ import annotations

from typing import Any, Optional
import math
import uuid

import io
import os
import sys
import json
import subprocess
from pathlib import Path
from pprint import pprint

import pandas as pd
from PIL import Image as PILImage
from wielder.util.telemetry import is_wsl

try:
    from IPython import get_ipython
    from IPython.display import HTML, display, clear_output, display_html, Markdown, Image, JSON
    import ipywidgets as widgets  # type: ignore
except ImportError:
    get_ipython = None
    widgets = None


DEFAULT_ROW_HEIGHT_PX = 28
DEFAULT_HEADER_HEIGHT_PX = 36


def _render_scrollable_html(
    df: pd.DataFrame,
    visible_rows: int,
    max_width: str,
    theme: dict[str, Any],
    freeze_cols: int,
) -> str:
    """
    Internal helper to generate the HTML string for a single dataframe view (page).
    """
    resolved_theme = {
        "outer_border": "#d0d7de",
        "header_background": "#f6f8fa",
        "header_color": "#0b1526",
        "row_border": "#eaeef2",
        "row_background": "#ffffff",
        "row_alt_background": "#f9fbfd",
        "font_family": (
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', "
            "system-ui, sans-serif"
        ),
        "font_size": "13px",
        **(theme or {}),
    }

    max_height = DEFAULT_HEADER_HEIGHT_PX + visible_rows * DEFAULT_ROW_HEIGHT_PX
    # Create unique ID for both table and container to strict scope CSS
    unique_id = uuid.uuid4().hex
    table_id = f"scrollable_table_{unique_id}"
    container_id = f"scrollable_container_{unique_id}"
    
    # notebook=False ensures we get a raw HTML table without pandas environment overrides
    html_table = df.to_html(
        classes=f"scrollable-dataframe-table {table_id}", 
        border=0, 
        notebook=False
    )

    n_index_levels = df.index.nlevels
    total_frozen = n_index_levels + freeze_cols
    
    js_script = ""
    if total_frozen > 0:
        js_script = f"""
        <script>
        (function() {{
            const tableId = '{table_id}';
            
            function run() {{
                const table = document.getElementsByClassName(tableId)[0];
                if (!table) return;

                function applyStickyCSS() {{
                    const firstBodyRow = table.querySelector('tbody tr');
                    if (!firstBodyRow) return;
                    
                    const cells = firstBodyRow.children;
                    if (!cells.length) return;

                    let currentLeft = 0;
                    let cssRules = [];
                    
                    const totalFrozen = {total_frozen};
                    const limit = Math.min(totalFrozen, cells.length);

                    for (let i = 0; i < limit; i++) {{
                        const cell = cells[i];
                        const width = cell.offsetWidth;
                        const nth = i + 1;
                        
                        // TH Rule (Header)
                        cssRules.push(`
                            .{table_id} thead tr > *:nth-child(${{nth}}) {{
                                position: sticky;
                                left: ${{currentLeft}}px;
                                z-index: 5 !important;
                            }}
                        `);

                        // TD Rule (Body)
                        cssRules.push(`
                            .{table_id} tbody tr > *:nth-child(${{nth}}) {{
                                position: sticky;
                                left: ${{currentLeft}}px;
                                z-index: 3;
                                background: {resolved_theme["row_background"]};
                            }}
                        `);
                        
                        // Alternating row background fix for sticky columns
                        cssRules.push(`
                            .{table_id} tbody tr:nth-child(even) > *:nth-child(${{nth}}) {{
                                background: {resolved_theme["row_alt_background"]};
                            }}
                        `);
                        
                        currentLeft += width;
                    }}
                    
                    const style = document.createElement('style');
                    style.innerHTML = cssRules.join('\\n');
                    document.head.appendChild(style);
                }}

                requestAnimationFrame(() => {{
                   setTimeout(applyStickyCSS, 50);
                }});
            }}
            
            if (document.readyState === 'loading') {{
                document.addEventListener('DOMContentLoaded', run);
            }} else {{
                run();
            }}
        }})();
        </script>
        """

    # We scope CSS to the specific container ID to avoid global collisions
    html = f"""
    <style>
      #{container_id} {{
        border: 1px solid {resolved_theme["outer_border"]};
        border-radius: 6px;
        overflow-x: auto;
        overflow-y: auto;
        max-width: {max_width};
        max-height: {max_height}px;
        box-sizing: border-box;
        background: {resolved_theme["row_background"]};
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
      }}

      #{container_id} .scrollable-dataframe-table {{
        border-collapse: collapse;
        width: max-content;
        min-width: 100%;
        font-family: {resolved_theme["font_family"]};
        font-size: {resolved_theme["font_size"]};
        color: {resolved_theme["header_color"]};
      }}

      #{container_id} .scrollable-dataframe-table thead {{
        background: {resolved_theme["header_background"]};
        z-index: 1;
      }}

      #{container_id} .scrollable-dataframe-table thead th {{
        position: sticky;
        top: 0;
        padding: 8px 12px;
        border-bottom: 1px solid {resolved_theme["outer_border"]};
        background: {resolved_theme["header_background"]};
        text-align: left;
        z-index: 1; 
      }}

      #{container_id} .scrollable-dataframe-table tbody td {{
        padding: 6px 12px;
        border-bottom: 1px solid {resolved_theme["row_border"]};
        background: {resolved_theme["row_background"]};
        text-align: left;
        direction: ltr;
      }}

      #{container_id} .scrollable-dataframe-table tbody tr:nth-child(even) td {{
        background: {resolved_theme["row_alt_background"]};
      }}

      #{container_id} .scrollable-dataframe-table tbody tr:hover td {{
        background: rgba(148, 163, 184, 0.14);
      }}

      #{container_id} .scrollable-dataframe-table caption {{
        caption-side: bottom;
        padding: 8px 12px;
        text-align: left;
        color: rgba(15, 23, 42, 0.6);
      }}
    </style>
    <div id="{container_id}" class="scrollable-dataframe-container">
      {html_table}
    </div>
    {js_script}
    """
    return html


def display_scrollable_dataframe(
    df: pd.DataFrame,
    *,
    visible_rows: int = 10,
    max_width: str = "100%",
    theme: Optional[dict[str, Any]] = None,
    freeze_cols: int = 0,
    page_size: int = 100,
) -> None:
    """
    Render a pandas DataFrame inside a scrollable container for Jupyter notebooks.
    
    If the DataFrame has more rows than `page_size`, it is paginated using
    ipywidgets to prevent browser performance issues.

    Args:
        df: The DataFrame to render.
        visible_rows: Approximate number of rows to keep visible without scrolling.
        max_width: CSS width limit for the outer container. Defaults to ``"100%"``.
        theme: Optional mapping of CSS variables to override default styling.
        freeze_cols: Number of columns to freeze from the left (excluding index).
        page_size: Number of rows per page for pagination. Defaults to 100.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("display_scrollable_dataframe expects a pandas DataFrame.")

    if visible_rows <= 0:
        raise ValueError("visible_rows must be a positive integer.")
        
    total_rows = len(df)
    
    # If small enough, just display directly
    if total_rows <= page_size:
        html = _render_scrollable_html(
            df, 
            visible_rows=visible_rows,
            max_width=max_width,
            theme=theme,
            freeze_cols=freeze_cols
        )
        display_html(html, raw=True)
        return

    # Pagination logic
    total_pages = math.ceil(total_rows / page_size)
    
    # Widgets - Use HTML widget directly to avoid Output capture leaks
    html_widget = widgets.HTML()
    
    btn_prev = widgets.Button(
        description="Previous",
        disabled=True,
        icon="arrow-left",
        layout=widgets.Layout(width='100px')
    )
    btn_next = widgets.Button(
        description="Next",
        disabled=False,
        icon="arrow-right",
        layout=widgets.Layout(width='100px')
    )
    lbl_page = widgets.Label(value=f"Page 1 of {total_pages}")
    
    current_page = 0
    
    def render_page(i: int):
        nonlocal current_page
        current_page = i
        
        start = i * page_size
        end = min(start + page_size, total_rows)
        page_df = df.iloc[start:end]
        
        html_content = _render_scrollable_html(
            page_df,
            visible_rows=visible_rows,
            max_width=max_width,
            theme=theme,
            freeze_cols=freeze_cols
        )
        html_widget.value = html_content
            
        # Update controls
        lbl_page.value = f"Page {i + 1} of {total_pages}"
        btn_prev.disabled = (i == 0)
        btn_next.disabled = (i == total_pages - 1)

    def on_prev(_):
        if current_page > 0:
            render_page(current_page - 1)
            
    def on_next(_):
        if current_page < total_pages - 1:
            render_page(current_page + 1)
            
    btn_prev.on_click(on_prev)
    btn_next.on_click(on_next)
    
    # Render initial page
    render_page(0)
    
    # Assembly
    controls = widgets.HBox(
        [btn_prev, lbl_page, btn_next],
        layout=widgets.Layout(justify_content='center', margin='10px 0')
    )
    
    # Ensure no previous output interferes
    display(widgets.VBox([html_widget, controls]))


def is_notebook() -> bool:
    """Detects if the code is executing within a Jupyter/IPython interface."""
    try:
        if get_ipython is None:
            return False
        shell = get_ipython().__class__.__name__
        if shell == 'ZMQInteractiveShell':
            return True   # Jupyter notebook or qtconsole
        elif shell == 'TerminalInteractiveShell':
            return False  # Terminal running IPython
        else:
            return False  # Other type (?)
    except NameError:
        return False
    except ImportError:
        return False

def display_markdown_asset(text: str):
    """Displays markdown natively in a Notebook or logs it in a standard terminal."""
    if is_notebook():
        display(Markdown(text))
    else:
        # Fallback to standard print/logging for terminal viewing
        print(f"\n{text}")

def display_image_asset(image_path: Path, conf=None, max_display_size: int = None, show_popup: bool = False):
    """Dynamically displays an image asset based on the runtime environment (Notebook inline vs OS Viewer). Fails loudly if missing."""
    # Ensure the path fails loudly before trying to open viewers
    if not image_path.exists():
        raise FileNotFoundError(f"[Errno 2] No such file or directory: '{image_path.as_posix()}'")
        
    if is_notebook():
        if image_path.suffix.lower() in ['.tif', '.tiff']:
            img = PILImage.open(image_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            if max_display_size:
                img.thumbnail((max_display_size, max_display_size), PILImage.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            display(Image(data=buf.getvalue(), format='png'))
        else:
            if max_display_size:
                img = PILImage.open(image_path)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.thumbnail((max_display_size, max_display_size), PILImage.Resampling.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format='PNG')
                display(Image(data=buf.getvalue(), format='png'))
            else:
                display(Image(filename=image_path.as_posix()))
    else:
        if is_wsl(conf):
            # Use wslview to hand off image rendering to the host Windows OS, which handles scaling cleanly
            if show_popup:
                subprocess.run(["wslview", image_path.as_posix()], check=False)
        else:
            img = PILImage.open(image_path)
            if max_display_size:
                img.thumbnail((max_display_size, max_display_size), PILImage.Resampling.LANCZOS)
            if show_popup:
                img.show()

def display_json_asset(json_path: Path):
    """Dynamically displays a JSON asset interactively or prints it natively. Fails loudly if missing."""
    with open(json_path, 'r') as f:
        j_data = json.load(f)
        
    if is_notebook():
        # Render as a syntax-highlighted static markdown code block instead of collapsed dropdowns
        pretty_json = json.dumps(j_data, indent=4)
        display(Markdown(f"```json\n{pretty_json}\n```"))
    else:
        pprint(j_data, indent=4)

def display_json_payload(j_data: dict, indent: int = 4):
    """Displays an in-memory JSON dictionary payload safely across GUI boundaries."""
    if is_notebook():
        pretty_json = json.dumps(j_data, indent=indent)
        display(Markdown(f"```json\n{pretty_json}\n```"))
    else:
        pprint(j_data, indent=indent)

def display_pil_image_asset(img: PILImage.Image, max_display_size: int = None, show_popup: bool = False):
    """Dynamically parses and renders raw in-memory Python Image models seamlessly agnostic to the physical file system limits."""
    if img.mode != 'RGB':
        img = img.convert('RGB')
    if max_display_size:
        img.thumbnail((max_display_size, max_display_size), PILImage.Resampling.LANCZOS)
        
    if is_notebook():
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        display(Image(data=buf.getvalue(), format='png'))
    else:
        if show_popup:
            img.show()

def __parse_cloud_uri(uri: str) -> tuple[str, str]:
    if uri.startswith("s3://") or uri.startswith("gs://"):
        parts = uri.split("://")[-1].split("/", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
    raise ValueError(f"Invalid cloud URI format: {uri}")

def display_cloud_json_asset(uri: str, conf, indent: int = 4):
    """Directly extracts and displays a JSON asset exclusively from S3 memory bounds avoiding local IO."""
    if str(uri).startswith("s3://") or str(uri).startswith("gs://"):
        from wielder.util.bucketeer import get_ecosystem_bucketeer
        bucketeer = get_ecosystem_bucketeer(conf)
        bucket, key = __parse_cloud_uri(uri)
        with bucketeer.read_object_stream(bucket, key, None) as stream:
            j_data = json.load(stream)
    else:
        with open(uri, 'r') as f:
            j_data = json.load(f)
    display_json_payload(j_data, indent=indent)

def display_cloud_image_asset(uri: str, conf, max_display_size: int = None, show_popup: bool = False):
    """Directly evaluates and translates image topologies strictly out of S3 arrays bypassing filesystem wrappers natively."""
    if str(uri).startswith("s3://") or str(uri).startswith("gs://"):
        from wielder.util.bucketeer import get_ecosystem_bucketeer
        bucketeer = get_ecosystem_bucketeer(conf)
        bucket, key = __parse_cloud_uri(uri)
        with bucketeer.read_object_stream(bucket, key, None) as stream:
            img = PILImage.open(stream)
            img.load()
    else:
        img = PILImage.open(uri)
        img.load()
    display_pil_image_asset(img, max_display_size, show_popup=show_popup)
    
def display_dataframe_asset(df: pd.DataFrame):
    """Dynamically displays a DataFrame based on the current environment (HTML Table vs Terminal text)."""
    if is_notebook():
        display_scrollable_dataframe(df)
    else:
        # Avoid pandas arbitrarily wrapping/truncating the human view unless configured
        with pd.option_context('display.max_rows', None, 'display.max_columns', None, 'display.width', 1000):
            print(df)

def dispatch_pymol_tensor_viewer(target_geom_path: str) -> None:
    """
    Dynamically spawns a native PyMOL visualization endpoint across WSL/Linux boundaries.
    Abstracts Windows environment escaping from the presentation layers natively.
    """
    import os
    import sys
    import subprocess
    
    print(f"Evaluating OS Environment for PyMOL execution over Tensor: {target_geom_path}...")
    
    if 'WSL_DISTRO_NAME' in os.environ:
        print("WSL environment detected! Bridging to native Windows hardware...")
        try:
            win_path = subprocess.check_output(['wslpath', '-m', target_geom_path]).decode().strip()
            pymol_exe = "%LOCALAPPDATA%/Schrodinger/PyMOL2/Scripts/pymol.exe"
            os.system(f'cmd.exe /c start "" "{pymol_exe}" "{win_path}"')
            print("Dispatched to Windows PyMOL.exe via AppData.")
        except Exception as e:
            print(f"Failed to bridge WSL to Windows PyMOL execution natively: {e}")
    elif sys.platform == "darwin":
        # TODO: Implement native macOS PyMOL app dispatch (e.g., `open -a PyMOL target.pdb`)
        raise NotImplementedError("Native macOS (Darwin) PyMOL dispatch is not yet implemented.")
    elif sys.platform.startswith("linux"):
        print("Native Linux deployment detected. Executing via setsid daemonization...")
        os.system(f"setsid pymol '{target_geom_path}' >/dev/null 2>&1 < /dev/zero &")
    else:
        raise NotImplementedError(f"PyMOL dispatch for unhandled OS architecture '{sys.platform}' is not implemented.")
