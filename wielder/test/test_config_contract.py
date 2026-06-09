import pytest
import os
from pathlib import Path
from pyhocon import ConfigFactory
from wielder.wield.wield_conf import get_wield_project_conf, get_agent_id

def test_ecosystem_contract(tmp_path: Path):
    """
    Establish the Contract of Inhabitation.
    Ensures that any project using Wielder has a valid project.conf 
    and deterministic identity.
    Tests against a dynamically generated, pristine filesystem mock.
    """
    # 1. Setup Isolated Mock Environment
    project_root = tmp_path
    conf_root = project_root / "conf"
    conf_root.mkdir(parents=True)
    context_root = project_root.parent / "context_conf" / "default_conf"
    context_root.mkdir(parents=True, exist_ok=True)
    
    # Base Project Config
    project_conf_path = conf_root / "project.conf"
    project_conf_path.write_text(
        'project.name = "mock_wield_project"\n'
        'ecosystem = "mock_surface"\n'
        'stage_tier = "dev"\n'
        'security = "standard"\n'
        'destroy = "standard"\n'
        'canary = "standard"\n'
    )
    
    # Mock Identity Override
    dev_conf_path = context_root / "developer.conf"
    dev_conf_path.write_text(
        'agent_id = "mock_agent"\n'
        'ecosystem = "mock_surface"\n'
        'stage_tier = "dev"\n'
        'security = "standard"\n'
        'destroy = "standard"\n'
        'canary = "standard"\n'
        'resolution_tier_1 = "context_conf"\n'
    )

    # 2. Load Config from isolated environment
    try:
        conf = get_wield_project_conf(project_root.as_posix(), conf_root.as_posix())
    except Exception as e:
        pytest.fail(f"Configuration load failed for {project_root}: {e}. Check Wielder core.")

    # 3. Verify Mandatory Wielder Structure Merges
    assert hasattr(conf, 'project_root'), "Missing project_root injection"
    assert hasattr(conf, 'super_repo_root'), "Missing super_repo_root injection"
    
    # 4. Verify the Project Config was Actually Yielded
    assert hasattr(conf, 'project') or hasattr(conf, 'project_name'), \
        "Failed to load the base project.conf correctly into the ConfigTree"
    assert str(conf.project.name) == "mock_wield_project", "Project name failed to load"

    # 5. Verify Global Identity Contract
    assert hasattr(conf, 'agent_id'), "agent_id not parsed or missing from overrides"
    assert str(conf.agent_id) == "mock_agent", "Agent ID override not correctly applied"
    
    print(f"\n[CONTRACT PASSED] Configuration engine is ecosystem-compliant for isolated mock.")


def test_wield_project_conf_accepts_stage_root_env_override(tmp_path: Path, monkeypatch):
    project_root = tmp_path / "project"
    conf_root = project_root / "conf"
    conf_root.mkdir(parents=True)
    context_root = project_root.parent / "context_conf" / "default_conf"
    context_root.mkdir(parents=True, exist_ok=True)
    stage_root = tmp_path / "runtime-stage" / "culture"

    (conf_root / "project.conf").write_text(
        'project.name = "mock_wield_project"\n'
        'ecosystem = "mock_surface"\n'
        'stage_tier = "dev"\n'
        'security = "standard"\n'
        'destroy = "standard"\n'
        'canary = "standard"\n'
    )
    (context_root / "developer.conf").write_text(
        'agent_id = "mock_agent"\n'
        'ecosystem = "mock_surface"\n'
        'stage_tier = "dev"\n'
        'security = "standard"\n'
        'destroy = "standard"\n'
        'canary = "standard"\n'
    )
    monkeypatch.setenv("WIELDER_STAGE_ROOT", stage_root.as_posix())

    conf = get_wield_project_conf(project_root.as_posix(), conf_root.as_posix())

    assert conf.stage_root == stage_root.as_posix()
    assert stage_root.exists()


def test_wield_project_conf_can_skip_live_git_snapshot(tmp_path: Path, monkeypatch):
    project_root = tmp_path / "project"
    conf_root = project_root / "conf"
    conf_root.mkdir(parents=True)
    context_root = project_root.parent / "context_conf" / "default_conf"
    context_root.mkdir(parents=True, exist_ok=True)

    (conf_root / "project.conf").write_text(
        'project.name = "mock_wield_project"\n'
        'ecosystem = "mock_surface"\n'
        'stage_tier = "dev"\n'
        'security = "standard"\n'
        'destroy = "standard"\n'
        'canary = "standard"\n'
    )
    (context_root / "developer.conf").write_text(
        'agent_id = "mock_agent"\n'
        'ecosystem = "mock_surface"\n'
        'stage_tier = "dev"\n'
        'security = "standard"\n'
        'destroy = "standard"\n'
        'canary = "standard"\n'
    )
    monkeypatch.setenv("WIELDER_SKIP_GIT_SNAPSHOT", "true")
    monkeypatch.setenv("WIELDER_GIT_COMMIT", "1111111111111111111111111111111111111111")
    monkeypatch.setenv("WIELDER_GIT_BRANCH", "packaged-runtime")

    conf = get_wield_project_conf(project_root.as_posix(), conf_root.as_posix())

    assert conf.git.commit == "1111111111111111111111111111111111111111"
    assert conf.git.short_commit == "11111111"
    assert conf.git.branch == "packaged-runtime"
    assert conf.git.subs == {}
    assert conf.git.branches == {}
