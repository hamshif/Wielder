from types import SimpleNamespace

import pytest
from pyhocon import ConfigFactory

from wielder.util import terraformer as terraformer_module
from wielder.util.terraformer import WrapTerraform


def test_aws_mfa_terraformer_clears_provider_profile_in_generated_tfvars(tmp_path):
    run_dir = "aws/container_registries/workspace"
    module_path = tmp_path / run_dir
    module_path.mkdir(parents=True)
    (module_path / "main.tf").write_text("terraform {}\n")
    tfvars = ConfigFactory.from_dict(
        {
            "aws_region": "us-east-2",
            "aws_profile": "profile-with-mfa-role",
        }
    )
    conf = SimpleNamespace(
        backend_root=str(tmp_path / "backends_tf"),
        backend_name=None,
        backend=None,
        tfvars=tfvars,
        state_backend_bootstrap_run_dir=None,
        state_backend_bootstrap_conf=None,
        verbose=False,
        cred_type="aws_mfa",
        cred_role="cli-mfa-role",
    )
    terraformer = WrapTerraform(root_path=str(tmp_path), run_dir=run_dir, conf=conf)

    terraformer.configure_tfvars()

    rendered = (module_path / "terraform.tfvars").read_text()
    assert 'aws_profile = ""' in rendered


def test_aws_default_terraformer_keeps_provider_profile_in_generated_tfvars(tmp_path):
    run_dir = "aws/container_registries/workspace"
    module_path = tmp_path / run_dir
    module_path.mkdir(parents=True)
    (module_path / "main.tf").write_text("terraform {}\n")
    tfvars = ConfigFactory.from_dict(
        {
            "aws_region": "us-east-2",
            "aws_profile": "ambient-or-profile-selected-by-config",
        }
    )
    conf = SimpleNamespace(
        backend_root=str(tmp_path / "backends_tf"),
        backend_name=None,
        backend=None,
        tfvars=tfvars,
        state_backend_bootstrap_run_dir=None,
        state_backend_bootstrap_conf=None,
        verbose=False,
        cred_type="aws_default",
        cred_role="",
    )
    terraformer = WrapTerraform(root_path=str(tmp_path), run_dir=run_dir, conf=conf)

    terraformer.configure_tfvars()

    rendered = (module_path / "terraform.tfvars").read_text()
    assert 'aws_profile = "ambient-or-profile-selected-by-config"' in rendered


def test_aws_default_terraformer_exports_profile_for_backend_and_cli_calls(tmp_path):
    run_dir = "aws/container_registries/workspace"
    module_path = tmp_path / run_dir
    module_path.mkdir(parents=True)
    tfvars = ConfigFactory.from_dict(
        {
            "aws_region": "us-east-2",
            "aws_profile": "workspace-cli",
        }
    )
    conf = SimpleNamespace(
        backend_root=str(tmp_path / "backends_tf"),
        backend_name=None,
        backend=None,
        tfvars=tfvars,
        state_backend_bootstrap_run_dir=None,
        state_backend_bootstrap_conf=None,
        verbose=False,
        cred_type="aws_default",
        cred_role="",
    )
    terraformer = WrapTerraform(root_path=str(tmp_path), run_dir=run_dir, conf=conf)

    assert "export AWS_PROFILE=workspace-cli;" in terraformer._aws_default_env_prefix()
    assert "export AWS_DEFAULT_PROFILE=workspace-cli;" in terraformer._aws_default_env_prefix()


def test_terraformer_fails_fast_when_terraform_is_missing(tmp_path, monkeypatch):
    run_dir = "aws/spark/emr"
    module_path = tmp_path / run_dir
    module_path.mkdir(parents=True)
    conf = SimpleNamespace(
        backend_root=str(tmp_path / "backends_tf"),
        backend_name=None,
        backend=None,
        tfvars=None,
        state_backend_bootstrap_run_dir=None,
        state_backend_bootstrap_conf=None,
        verbose=False,
    )
    wrapper = WrapTerraform(root_path=str(tmp_path), run_dir=run_dir, conf=conf)

    monkeypatch.setattr(terraformer_module.shutil, "which", lambda command: None)

    with pytest.raises(RuntimeError, match="install_ubuntu.sh --only terraform"):
        wrapper.run_cmd_in_repo(
            t_cmd="terraform version",
            get_reply=False,
            reply_type=None,
        )


def test_terraformer_detects_eks_provision_resources(tmp_path):
    conf = SimpleNamespace(
        backend_root=str(tmp_path / "backends_tf"),
        backend_name=None,
        backend=None,
        tfvars=ConfigFactory.from_dict(
            {
                "aws_region": "us-east-2",
                "aws_profile": "workspace-cli",
                "provision_resources": ["eks", "managed_node_group_class"],
            }
        ),
        state_backend_bootstrap_run_dir=None,
        state_backend_bootstrap_conf=None,
        runtime_env="aws",
        verbose=False,
        cred_type="aws_default",
        cred_role="",
    )
    terraformer = WrapTerraform(root_path=str(tmp_path), run_dir="aws/super_cluster", conf=conf)

    assert terraformer._terraform_provisions_aws_eks() is True


def test_terraformer_updates_kube_context_after_eks_apply(tmp_path, monkeypatch):
    calls = []
    conf = SimpleNamespace(
        backend_root=str(tmp_path / "backends_tf"),
        backend_name=None,
        backend=None,
        tfvars=ConfigFactory.from_dict(
            {
                "aws_region": "us-east-2",
                "aws_profile": "workspace-cli",
                "provision_resources": ["eks", "managed_node_group_class"],
            }
        ),
        state_backend_bootstrap_run_dir=None,
        state_backend_bootstrap_conf=None,
        runtime_env="aws",
        kube_cluster_name="dev--webapps--core",
        kube_context="arn:aws:eks:us-east-2:123456789012:cluster/dev--webapps--core",
        verbose=False,
        cred_type="aws_mfa",
        cred_role="cli-mfa-role",
    )
    terraformer = WrapTerraform(root_path=str(tmp_path), run_dir="aws/super_cluster", conf=conf)

    def fake_update(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(terraformer_module, "update_kubernetes_context", fake_update)

    terraformer._prepare_tfvars_for_execution()
    terraformer._update_kubernetes_context_after_eks_apply()

    assert terraformer.tfvars.aws_profile == ""
    assert calls == [
        (
            ("aws", "workspace-cli", "us-east-2", "dev--webapps--core"),
            {
                "context_alias": "arn:aws:eks:us-east-2:123456789012:cluster/dev--webapps--core",
                "aws_cred_role": "cli-mfa-role",
            },
        )
    ]
