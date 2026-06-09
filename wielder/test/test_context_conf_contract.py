from pathlib import Path

from wielder.wield.wield_conf import get_wield_project_conf


def test_context_conf_top_level_scalar_trumps_project(tmp_path: Path):
    project_root = tmp_path
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
        'super_hero = "project_hero"\n'
    )

    (context_root / "developer.conf").write_text(
        'agent_id = "mock_agent"\n'
        'ecosystem = "mock_surface"\n'
        'stage_tier = "dev"\n'
        'security = "standard"\n'
        'destroy = "standard"\n'
        'canary = "standard"\n'
        'super_hero = "buggs"\n'
        'resolution_tier_1 = "context_conf"\n'
    )

    conf = get_wield_project_conf(project_root.as_posix(), conf_root.as_posix())

    assert conf.super_hero == "buggs"


def test_developer_conf_trumps_ephemeral_conf(tmp_path: Path):
    project_root = tmp_path
    conf_root = project_root / "conf"
    conf_root.mkdir(parents=True)
    context_root = conf_root / "context_conf" / "default_conf"
    context_root.mkdir(parents=True, exist_ok=True)

    (conf_root / "project.conf").write_text(
        'project.name = "mock_wield_project"\n'
        'ecosystem = "mock_surface"\n'
        'stage_tier = "dev"\n'
        'security = "standard"\n'
        'destroy = "standard"\n'
        'canary = "standard"\n'
        'operator_intent = "project"\n'
        'generated_state = "project"\n'
    )

    (context_root / "ephemeral.conf").write_text(
        'operator_intent = "ephemeral"\n'
        'generated_state = "ephemeral"\n'
    )

    (context_root / "developer.conf").write_text(
        'agent_id = "mock_agent"\n'
        'operator_intent = "developer"\n'
    )

    conf = get_wield_project_conf(project_root.as_posix(), conf_root.as_posix())

    assert conf.operator_intent == "developer"
    assert conf.generated_state == "ephemeral"
    assert conf.context_conf_root == context_root.as_posix()
    assert conf.ephemeral_conf_path == (context_root / "ephemeral.conf").as_posix()
    assert conf.developer_conf_path == (context_root / "developer.conf").as_posix()
