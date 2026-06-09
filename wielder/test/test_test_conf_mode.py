from pathlib import Path

from pyhocon import ConfigFactory
from wielder.util.arguer import get_ecosystem_parser, parse_known_args_strict
from wielder.wield.enumerator import WieldAction
from wielder.wield.wield_conf import (
    build_cli_overrides,
    build_cli_overrides_from_conf,
    get_wield_app_conf,
    get_wield_project_conf,
)


def _write_project_conf(conf_root: Path) -> None:
    conf_root.mkdir(parents=True, exist_ok=True)
    (conf_root / "project.conf").write_text(
        'project.name = "mock_wield_project"\n'
        'ecosystem = "mock_surface"\n'
        'stage_tier = "dev"\n'
        'security = "standard"\n'
        'destroy = "standard"\n'
        'canary = "standard"\n'
    )


def test_ecosystem_parser_defaults_to_false_test_mode():
    args, _ = parse_known_args_strict(get_ecosystem_parser(), [])

    assert args.test is False


def test_ecosystem_parser_accepts_explicit_test_modes():
    args, _ = parse_known_args_strict(get_ecosystem_parser(), ["-t", "false"])
    true_args, _ = parse_known_args_strict(get_ecosystem_parser(), ["-t", "true"])
    short_true_args, _ = parse_known_args_strict(get_ecosystem_parser(), ["-t"])
    mixed_args, _ = parse_known_args_strict(get_ecosystem_parser(), ["-t", "-w", "apply"])

    assert args.test is False
    assert true_args.test is True
    assert short_true_args.test is True
    assert mixed_args.test is True
    assert mixed_args.wield.value == "apply"


def test_build_cli_overrides_from_conf_carries_resolved_wielder_modes():
    conf = ConfigFactory.from_dict(
        {
            "ecosystem": "aws_webapps_core",
            "stage_tier": "dev",
            "security": "org",
            "destroy": "standard",
            "canary": "standard",
            "context_conf": "default_conf",
            "test": False,
            "action": "apply",
        }
    )

    overrides = build_cli_overrides_from_conf(conf, action=WieldAction.PLAN)

    assert overrides == {
        "ecosystem": "aws_webapps_core",
        "stage_tier": "dev",
        "security": "org",
        "destroy": "standard",
        "canary": "standard",
        "context_conf": "default_conf",
        "test": False,
        "action": "plan",
    }


def test_legacy_root_test_conf_is_not_loaded_by_default(tmp_path: Path):
    project_root = tmp_path
    conf_root = project_root / "conf"
    _write_project_conf(conf_root)
    (conf_root / "test.conf").write_text(
        'project_test_marker = "loaded"\n'
        'stage_test_marker = ${stage_tier}\n'
    )

    conf = get_wield_project_conf(project_root.as_posix(), conf_root.as_posix())

    assert conf.get("project_test_marker", "missing") == "missing"
    assert conf.test is False


def test_legacy_root_test_conf_is_not_loaded_in_test_mode(tmp_path: Path):
    project_root = tmp_path
    conf_root = project_root / "conf"
    _write_project_conf(conf_root)
    (conf_root / "test.conf").write_text(
        'project_test_marker = "loaded"\n'
        'stage_test_marker = ${stage_tier}\n'
    )

    conf = get_wield_project_conf(
        project_root.as_posix(),
        conf_root.as_posix(),
        cli_overrides=build_cli_overrides(test=True),
    )

    assert conf.get("project_test_marker", "missing") == "missing"
    assert conf.test is True
    assert conf.test_conf_path == ""


def test_project_test_conf_can_be_disabled(tmp_path: Path):
    project_root = tmp_path
    conf_root = project_root / "conf"
    _write_project_conf(conf_root)
    (conf_root / "test.conf").write_text('project_test_marker = "loaded"\n')

    conf = get_wield_project_conf(
        project_root.as_posix(),
        conf_root.as_posix(),
        cli_overrides=build_cli_overrides(test=False),
    )

    assert conf.get("project_test_marker", "missing") == "missing"
    assert conf.test is False


def test_ecosystem_test_conf_trumps_context_in_test_mode(tmp_path: Path):
    project_root = tmp_path
    conf_root = project_root / "conf"
    _write_project_conf(conf_root)

    context_root = conf_root / "context_conf" / "default_conf"
    context_root.mkdir(parents=True)
    (context_root / "ephemeral.conf").write_text(
        'operator_intent = "ephemeral"\n'
        'generated_state = "ephemeral"\n'
    )
    (context_root / "developer.conf").write_text(
        'operator_intent = "developer"\n'
    )

    ecosystem_root = conf_root / "ecosystem" / "mock_domain" / "mock_surface"
    ecosystem_root.mkdir(parents=True)
    (ecosystem_root / "ecosystem_manifest.conf").write_text(
        'operator_intent = "ecosystem"\n'
    )

    test_root = conf_root / "test" / "mock_domain" / "mock_surface"
    test_root.mkdir(parents=True)
    ecosystem_test_conf = test_root / "test.conf"
    ecosystem_test_conf.write_text(
        'operator_intent = "ecosystem_test"\n'
        'test_fixture_marker = "loaded"\n'
    )

    conf = get_wield_project_conf(
        project_root.as_posix(),
        conf_root.as_posix(),
        cli_overrides=build_cli_overrides(test=True),
    )

    assert conf.operator_intent == "ecosystem_test"
    assert conf.generated_state == "ephemeral"
    assert conf.test_fixture_marker == "loaded"
    assert conf.test_conf_path == ecosystem_test_conf.as_posix()


def test_ecosystem_test_conf_is_inactive_without_test_mode(tmp_path: Path):
    project_root = tmp_path
    conf_root = project_root / "conf"
    _write_project_conf(conf_root)

    context_root = conf_root / "context_conf" / "default_conf"
    context_root.mkdir(parents=True)
    (context_root / "ephemeral.conf").write_text('operator_intent = "ephemeral"\n')
    (context_root / "developer.conf").write_text('operator_intent = "developer"\n')

    ecosystem_root = conf_root / "ecosystem" / "mock_domain" / "mock_surface"
    ecosystem_root.mkdir(parents=True)
    (ecosystem_root / "ecosystem_manifest.conf").write_text(
        'operator_intent = "ecosystem"\n'
    )

    test_root = conf_root / "test" / "mock_domain" / "mock_surface"
    test_root.mkdir(parents=True)
    (test_root / "test.conf").write_text('operator_intent = "ecosystem_test"\n')

    conf = get_wield_project_conf(
        project_root.as_posix(),
        conf_root.as_posix(),
        cli_overrides=build_cli_overrides(test=False),
    )

    assert conf.operator_intent == "developer"
    assert conf.test is False


def test_ecosystem_test_conf_does_not_own_action(tmp_path: Path):
    project_root = tmp_path
    conf_root = project_root / "conf"
    _write_project_conf(conf_root)

    ecosystem_root = conf_root / "ecosystem" / "mock_domain" / "mock_surface"
    ecosystem_root.mkdir(parents=True)
    (ecosystem_root / "ecosystem_manifest.conf").write_text(
        'operator_intent = "ecosystem"\n'
    )

    test_root = conf_root / "test" / "mock_domain" / "mock_surface"
    test_root.mkdir(parents=True)
    (test_root / "test.conf").write_text(
        'operator_intent = "ecosystem_test"\n'
        'action = "delete"\n'
    )

    conf = get_wield_project_conf(
        project_root.as_posix(),
        conf_root.as_posix(),
        cli_overrides=build_cli_overrides(test=True, action="apply"),
    )

    assert conf.operator_intent == "ecosystem_test"
    assert conf.action == "apply"


def test_app_test_conf_extends_app_baseline_in_test_mode(tmp_path: Path):
    project_root = tmp_path
    conf_root = project_root / "conf"
    _write_project_conf(conf_root)

    app_root = conf_root / "apps" / "mock_app"
    app_root.mkdir(parents=True)
    (app_root / "app.conf").write_text(
        'mock_app.value = "baseline"\n'
        'mock_app.stage = ${stage_tier}\n'
    )
    (app_root / "test.conf").write_text(
        'mock_app.value = "test"\n'
        'mock_app.test_only = "present"\n'
    )

    conf = get_wield_app_conf(
        project_root.as_posix(),
        conf_root.as_posix(),
        app_name="mock_app",
        cli_overrides=build_cli_overrides(test=True),
    )

    assert conf.mock_app.value == "test"
    assert conf.mock_app.stage == "dev"
    assert conf.mock_app.test_only == "present"


def test_app_test_conf_can_be_disabled(tmp_path: Path):
    project_root = tmp_path
    conf_root = project_root / "conf"
    _write_project_conf(conf_root)

    app_root = conf_root / "apps" / "mock_app"
    app_root.mkdir(parents=True)
    (app_root / "app.conf").write_text('mock_app.value = "baseline"\n')
    (app_root / "test.conf").write_text(
        'mock_app.value = "test"\n'
        'mock_app.test_only = "present"\n'
    )

    conf = get_wield_app_conf(
        project_root.as_posix(),
        conf_root.as_posix(),
        app_name="mock_app",
        cli_overrides=build_cli_overrides(test=False),
    )

    assert conf.mock_app.value == "baseline"
    assert conf.mock_app.get("test_only", "missing") == "missing"
