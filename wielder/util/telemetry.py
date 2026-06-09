import platform
import subprocess
import logging
from pathlib import Path

def is_wsl(conf=None) -> bool:
    """Detects if the execution environment is Windows Subsystem for Linux."""
    if conf is not None:
        try:
            return conf.get_bool("conf_evaluation_details.os.is_wsl", False)
        except Exception:
            pass
            
    try:
        with open('/proc/version', 'r') as f:
            version_str = f.read().lower()
            if 'microsoft' in version_str or 'wsl' in version_str:
                return True
    except FileNotFoundError:
        pass
    return False

def get_telemetry(repo_root: str = None) -> dict:
    """
    Scrapes the environment for detailed reproducibility telemetry.
    Returns a dictionary covering OS architecture, python version, and user/git identity.
    Uses WGit to dynamically scrape the entire super-repo and all submodules if present.
    """
    def run_cmd(cmd: str) -> str:
        try:
            result = subprocess.run(cmd.split(), capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except Exception as e:
            logging.debug(f"Telemetry command failed: {cmd} - {e}")
            return "UNKNOWN"

    from wielder.util.wgit import WGit

    # Navigate up to find the master super-repo root (where .gitmodules lives)
    if not repo_root:
        repo_root = str(Path.cwd())
        
    current_dir = Path(repo_root).resolve()
    while current_dir.parent != current_dir:
        if (current_dir / '.gitmodules').exists():
            repo_root = str(current_dir)
            break
        current_dir = current_dir.parent

    git_telemetry = {
        "commit_hash": "UNKNOWN",
        "is_dirty": "UNKNOWN",
        "submodules": {}
    }

    try:
        wgit = WGit(repo_root)
        git_telemetry["commit_hash"] = wgit.commit
        git_telemetry["branch"] = wgit.branch
        
        status_out = subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, capture_output=True, text=True).stdout
        git_telemetry["is_dirty"] = "true" if status_out.strip() else "false"
        
        subs = wgit.get_submodule_names()
        for sub in subs:
            git_telemetry["submodules"][sub] = wgit.get_submodule_commit(sub)
    except Exception as e:
        logging.warning(f"WGit telemetry extraction failed: {e}")

    telemetry = {
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "architecture": platform.machine(),
            "is_wsl": is_wsl()
        },
        "python": {
            "version": platform.python_version()
        },
        "user": {
            "whoami": run_cmd("whoami"),
            "git_name": run_cmd("git config user.name"),
            "git_email": run_cmd("git config user.email")
        },
        "git": git_telemetry
    }
    return telemetry
