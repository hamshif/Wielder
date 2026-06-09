import sys
import json
from pathlib import Path

def py_to_ipynb(py_path: Path, ipynb_path: Path):
    """Converts a python script separated by `# %%` markers into a Jupyter Notebook."""
    with open(py_path, 'r') as f:
        content = f.read()
        
    cells_raw = content.split('# %%')
    notebook_cells = []
    
    all_imports = []
    processed_chunks = []
    
    in_main_block = False
    
    # Pre-parse the file to isolate explicit structural targets (Rule 1 & Rule 2)
    for chunk in cells_raw:
        lines = chunk.split('\n')
        cleaned_lines = []
        in_multiline_import = False
        
        for line in lines:
            # Rule 1: Automated Top-Level Import Hoisting
            if in_multiline_import:
                all_imports.append(line)
                if ')' in line:
                    in_multiline_import = False
                continue
                
            if (line.startswith('import ') or line.startswith('from ')) and not in_main_block:
                all_imports.append(line)
                if '(' in line and ')' not in line:
                    in_multiline_import = True
                continue
                
            # Rule 3: Secure Interactive Jupyter Plane
            if "matplotlib.use('Agg')" in line:
                continue # Strip the headless rendering engine from interactive topologies
                
            # Rule 4: Strip and Un-Indent main execution scopes for flat Notebook traversal
            if line.startswith('if __name__ == "__main__":') or line.startswith("if __name__ == '__main__':"):
                in_main_block = True
                continue
                
            if in_main_block:
                if line.startswith('    '):
                    cleaned_lines.append(line[4:])
                elif line.strip() == '':
                    cleaned_lines.append(line)
                elif not line.startswith(' ') and not line.startswith('#'):
                    in_main_block = False
                    cleaned_lines.append(line)
                else: 
                    cleaned_lines.append(line)
            else:
                cleaned_lines.append(line)
                
        processed_chunks.append('\n'.join(cleaned_lines))

    # Re-assemble structural cell blocks    
    if all_imports:
        import_source = [line + '\n' for line in all_imports]
        import_source[-1] = import_source[-1].rstrip('\n')
        notebook_cells.append({
            "cell_type": "code",
            "metadata": {},
            "source": import_source,
            "outputs": [], 
            "execution_count": None
        })

    for chunk in processed_chunks:
        lines = chunk.split('\n')
        if not lines:
            continue
            
        header = lines[0].strip().lower()
        if header.startswith('[markdown]'):
            cell_type = 'markdown'
            raw_lines = chunk[len(lines[0])+1:].strip('\n').split('\n')
            source_lines = []
            for l in raw_lines:
                if l.startswith('# '):
                    source_lines.append(l[2:])
                elif l.startswith('#'):
                    source_lines.append(l[1:])
                else:
                    source_lines.append(l)
        else:
            cell_type = 'code'
            source_lines = chunk.strip('\n').split('\n')
            
        if not any(l.strip() for l in source_lines):
            continue
            
        source_formatted = [line + '\n' for line in source_lines[:-1]]
        if source_lines:
            source_formatted.append(source_lines[-1]) 
            
        notebook_cells.append({
            "cell_type": cell_type,
            "metadata": {},
            "source": source_formatted,
            **({"outputs": [], "execution_count": None} if cell_type == "code" else {})
        })
        
    notebook = {
        "cells": notebook_cells,
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 4
    }
    
    with open(ipynb_path, 'w') as f:
        json.dump(notebook, f, indent=1)
    print(f"Successfully converted {py_path.name} to {ipynb_path.name}")


def ipynb_to_py(ipynb_path: Path, py_path: Path):
    """Converts a Jupyter Notebook into a Python script with `# %%` cell markers."""
    with open(ipynb_path, 'r') as f:
        notebook = json.load(f)
        
    py_lines = []
    for cell in notebook.get('cells', []):
        cell_type = cell.get('cell_type', 'code')
        source = cell.get('source', [])
        
        if cell_type == 'markdown':
            py_lines.append('# %% [markdown]')
            for line in source:
                py_lines.append('# ' + line.rstrip('\n'))
        else:
            py_lines.append('# %%')
            for line in source:
                py_lines.append(line.rstrip('\n'))
            
        py_lines.append('\n')
        
    with open(py_path, 'w') as f:
        f.write('\n'.join(py_lines))
    print(f"Successfully converted {ipynb_path.name} to {py_path.name}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m wielder.util.notebook_converter <file.py | file.ipynb>")
        sys.exit(1)
        
    target = Path(sys.argv[1])
    if not target.exists():
        print(f"Target file {target} does not exist.")
        sys.exit(1)
        
    if target.suffix == '.py':
        py_to_ipynb(target, target.with_suffix('.ipynb'))
    elif target.suffix == '.ipynb':
        ipynb_to_py(target, target.with_suffix('.py'))
    else:
        print("File must be .py or .ipynb")
        sys.exit(1)
