from types import SimpleNamespace
from pathlib import Path

import pytest

from wielder.util import imager
from wielder.wield.enumerator import ImageRegistrySurface


def test_docker_context_ignore_patterns_keep_git_ignored_by_default():
    lines, _ignore = imager._docker_context_ignore_patterns()

    assert ".git" in lines
    assert "**/.git" in lines


def test_docker_context_ignore_patterns_can_include_git_metadata():
    lines, _ignore = imager._docker_context_ignore_patterns(
        [".git", "**/.git", "node_modules"],
        include_git_metadata=True,
    )

    assert ".git" not in lines
    assert "**/.git" not in lines
    assert "node_modules" in lines


def test_git_metadata_overlay_rejects_stale_embedded_staged_git_dir(tmp_path):
    source = tmp_path / "source" / "workflow-runner"
    source.mkdir(parents=True)
    (source / ".git").write_text("gitdir: ../.git/modules/workflow-runner\n")

    destination = tmp_path / "stage" / "workflow-runner"
    (destination / ".git").mkdir(parents=True)

    with pytest.raises(RuntimeError, match="stale staged image directory"):
        imager._preflight_git_metadata_overlay(source.as_posix(), destination.as_posix())


def test_git_metadata_staging_reset_removes_read_only_git_objects(tmp_path):
    staging_dir = tmp_path / "stage" / "workspace_datalake_web"
    object_path = staging_dir / ".git" / "objects" / "aa" / "object"
    object_path.parent.mkdir(parents=True)
    object_path.write_text("git-object")
    object_path.chmod(0o444)

    imager._reset_git_metadata_staging_dir(staging_dir.as_posix())

    assert not staging_dir.exists()


def test_layered_super_repo_context_copies_shell_without_submodules(tmp_path, monkeypatch):
    source_root = tmp_path / "source"
    staging_dir = tmp_path / "stage"
    source_root.mkdir()
    staging_dir.mkdir()
    (source_root / "README.md").write_text("root readme")
    (source_root / ".git").mkdir()
    (source_root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (source_root / "Wielder").mkdir()
    (source_root / "Wielder" / ".git").write_text("gitdir: ../.git/modules/Wielder\n")
    (source_root / "Wielder" / "wielder.py").write_text("print('wielder')\n")
    (source_root / "domain-app").mkdir()
    (source_root / "domain-app" / ".git").write_text("gitdir: ../.git/modules/domain-app\n")
    (source_root / "domain-app" / "app.py").write_text("print('app')\n")
    (source_root / "untracked.tmp").write_text("should not copy")

    class FakeWGit:
        def __init__(self, _repo_path):
            pass

        def get_submodule_paths(self):
            return ["Wielder", "domain-app"]

        def get_tracked_root_items(self):
            return ["README.md", "Wielder", "domain-app"]

    monkeypatch.setattr(imager, "WGit", FakeWGit)
    _lines, ignore_patterns = imager._docker_context_ignore_patterns(include_git_metadata=True)

    modules = imager._stage_layered_super_repo_context(
        image_context=source_root.as_posix(),
        staging_dir=staging_dir.as_posix(),
        layered_super_repo_context={
            "enabled": True,
            "shell_dir": "_shell",
            "module_order": ["Wielder"],
        },
        ignore_patterns=ignore_patterns,
    )

    assert modules == ["Wielder", "domain-app"]
    assert (staging_dir / "_shell" / "README.md").read_text() == "root readme"
    assert (staging_dir / "_shell" / ".git" / "HEAD").exists()
    assert not (staging_dir / "_shell" / "Wielder").exists()
    assert not (staging_dir / "_shell" / "domain-app").exists()
    assert not (staging_dir / "_shell" / "untracked.tmp").exists()
    assert (staging_dir / "Wielder" / "wielder.py").exists()
    assert (staging_dir / "domain-app" / "app.py").exists()


def test_bulk_super_repo_context_exports_tracked_shape_without_workspace_junk(tmp_path, monkeypatch):
    source_root = tmp_path / "source"
    staging_dir = tmp_path / "stage"
    source_root.mkdir()
    staging_dir.mkdir()
    (source_root / ".git").mkdir()
    (source_root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (source_root / "Wielder").mkdir()
    (source_root / "Wielder" / ".git").write_text("gitdir: ../.git/modules/Wielder\n")
    (source_root / "domain-app").mkdir()
    (source_root / "domain-app" / ".git").write_text("gitdir: ../.git/modules/domain-app\n")

    class FakeWGit:
        def __init__(self, repo_path):
            self.repo_path = repo_path

        def get_submodule_paths(self):
            return ["Wielder", "domain-app"] if self.repo_path == source_root.as_posix() else []

        def export_tree_to(self, destination):
            destination_path = Path(destination)
            destination_path.mkdir(parents=True, exist_ok=True)
            if self.repo_path == source_root.as_posix():
                (destination_path / "README.md").write_text("root readme")
                (destination_path / ".gitmodules").write_text("submodules")
            elif self.repo_path.endswith("Wielder"):
                (destination_path / "wielder.py").write_text("print('wielder')\n")
            elif self.repo_path.endswith("domain-app"):
                (destination_path / "app.py").write_text("print('app')\n")

    monkeypatch.setattr(imager, "WGit", FakeWGit)
    _lines, ignore_patterns = imager._docker_context_ignore_patterns(include_git_metadata=True)

    assert imager._stage_bulk_super_repo_context(
        image_context=source_root.as_posix(),
        staging_dir=staging_dir.as_posix(),
        bulk_super_repo_context={
            "enabled": True,
            "destination": ".",
            "module_order": ["Wielder"],
        },
        ignore_patterns=ignore_patterns,
    )

    assert (staging_dir / "README.md").read_text() == "root readme"
    assert (staging_dir / ".git" / "HEAD").exists()
    assert (staging_dir / "Wielder" / "wielder.py").exists()
    assert (staging_dir / "Wielder" / ".git").is_file()
    assert (staging_dir / "domain-app" / "app.py").exists()
    assert (staging_dir / "domain-app" / ".git").is_file()
    assert not (staging_dir / ".venv").exists()


def test_layered_super_repo_copy_marker_expands_per_module_layers(tmp_path):
    staging_dir = tmp_path / "stage"
    staging_dir.mkdir()
    dockerfile_path = staging_dir / "Dockerfile"
    dockerfile_path.write_text(
        "FROM python:3.11\n"
        "RUN mkdir -p /app/workspace\n"
        "# WIELDER_LAYERED_SUPER_REPO_COPY\n"
        "RUN python -V\n"
    )

    imager._inject_layered_super_repo_copy_instructions(
        staging_dir=staging_dir.as_posix(),
        layered_super_repo_context={
            "enabled": True,
            "root_destination": "/app/workspace",
            "shell_dir": "_shell",
        },
        modules=["Wielder", "domain-app"],
    )

    rendered = dockerfile_path.read_text()
    assert "# WIELDER_LAYERED_SUPER_REPO_COPY" not in rendered
    assert "COPY Wielder/ /app/workspace/Wielder/" in rendered
    assert "COPY domain-app/ /app/workspace/domain-app/" in rendered
    assert rendered.index("COPY Wielder/") < rendered.index("COPY _shell/")
    assert "COPY _shell/ /app/workspace/" in rendered


def test_gcp_artifact_registry_image_exists_returns_true(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(imager.subprocess, "run", fake_run)

    assert imager.gcp_artifact_registry_image_exists(
        image_ref="us-central1-docker.pkg.dev/workspace-dev/workspace/wclone_job_runner:dev",
        project_id="workspace-dev",
    ) is True
    assert calls[0][0] == [
        "gcloud",
        "artifacts",
        "docker",
        "images",
        "describe",
        "us-central1-docker.pkg.dev/workspace-dev/workspace/wclone_job_runner:dev",
        "--project",
        "workspace-dev",
    ]


def test_gcp_artifact_registry_image_exists_returns_false_for_not_found(monkeypatch):
    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stderr="NOT_FOUND: image does not exist")

    monkeypatch.setattr(imager.subprocess, "run", fake_run)

    assert imager.gcp_artifact_registry_image_exists(
        image_ref="us-central1-docker.pkg.dev/workspace-dev/workspace/wclone_job_runner:dev",
        project_id="workspace-dev",
    ) is False


def test_gcp_artifact_registry_image_exists_returns_none_for_ambiguous_failure(monkeypatch):
    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stderr="permission denied")

    monkeypatch.setattr(imager.subprocess, "run", fake_run)

    assert imager.gcp_artifact_registry_image_exists(
        image_ref="us-central1-docker.pkg.dev/workspace-dev/workspace/wclone_job_runner:dev",
        project_id="workspace-dev",
    ) is None


def test_gcp_artifact_registry_accessor_builds_image_ref_without_repeated_repository_prefix():
    accessor = imager.GCPArtifactRegistryImageAccessor(
        SimpleNamespace(
            registry_authority="us-central1-docker.pkg.dev/workspace-dev/workspace",
            project_id="workspace-dev",
            repository_id="workspace",
        )
    )

    assert accessor.image_ref("workspace/wclone_job_runner", "dev") == (
        "us-central1-docker.pkg.dev/workspace-dev/workspace/wclone_job_runner:dev"
    )


def test_remote_registry_accessor_builds_pull_image_ref():
    accessor = imager.RemoteRegistryImageAccessor(
        SimpleNamespace(push_authority="localhost:5000", pull_authority="k3d-registry.localhost:5000")
    )

    assert accessor.image_ref("workspace/wclone_job_runner", "dev") == (
        "k3d-registry.localhost:5000/workspace/wclone_job_runner:dev"
    )


def test_aws_ecr_accessor_builds_image_ref_from_authority():
    accessor = imager.AWSECRImageAccessor(
        SimpleNamespace(
            registry_authority="123456789012.dkr.ecr.us-east-1.amazonaws.com",
            push=SimpleNamespace(
                account_id="123456789012",
                image_repo_zone="us-east-1",
                cred_profile="default",
            ),
        )
    )

    assert accessor.image_ref("workspace/wclone_job_runner", "dev") == (
        "123456789012.dkr.ecr.us-east-1.amazonaws.com/workspace/wclone_job_runner:dev"
    )


def test_aws_ecr_image_exists_uses_wielder_aws_actions(monkeypatch):
    calls = []

    class FakeAWSActions:
        def __init__(self, conf):
            calls.append(("init", conf))

        def ecr_image_exists(self, **kwargs):
            calls.append(("ecr_image_exists", kwargs))
            return True

    monkeypatch.setattr(imager, "AWSActions", FakeAWSActions)
    conf = SimpleNamespace(image_repo_zone="us-east-1", cred_profile="default")

    assert imager.aws_ecr_image_exists(conf, "workspace/app", "dev") is True
    assert calls == [
        ("init", conf),
        (
            "ecr_image_exists",
            {"repository_name": "workspace/app", "image_tag": "dev"},
        ),
    ]


def test_configured_image_registry_accessor_builds_image_ref():
    conf = SimpleNamespace(
        image_registry_surface=ImageRegistrySurface.KIND_REGISTRY.value,
        kind=SimpleNamespace(
            registry=SimpleNamespace(
                push_authority="localhost:5000",
                pull_authority="kind-registry:5000",
            )
        ),
    )

    accessor = imager.configured_image_registry_accessor(conf)

    assert accessor.image_ref("workspace/wclone_job_runner", "dev") == (
        "kind-registry:5000/workspace/wclone_job_runner:dev"
    )


def test_configured_image_registry_accessor_selects_gcp_accessor():
    conf = SimpleNamespace(
        image_registry_surface=ImageRegistrySurface.GCP_ARTIFACT_REGISTRY.value,
        gcp=SimpleNamespace(
            artifact_registry=SimpleNamespace(
                registry_authority="us-central1-docker.pkg.dev/workspace-dev/workspace",
                project_id="workspace-dev",
                repository_id="workspace",
            )
        ),
    )

    selected = imager.configured_image_registry_accessor(conf)

    assert isinstance(selected, imager.GCPArtifactRegistryImageAccessor)
    assert selected.image_ref("workspace/wclone_job_runner", "dev") == (
        "us-central1-docker.pkg.dev/workspace-dev/workspace/wclone_job_runner:dev"
    )


def test_image_registry_accessor_factory_selects_gcp_accessor():
    selected = imager.image_registry_accessor(
        ImageRegistrySurface.GCP_ARTIFACT_REGISTRY,
        lambda: SimpleNamespace(
            registry_authority="us-central1-docker.pkg.dev/workspace-dev/workspace",
            project_id="workspace-dev",
            repository_id="workspace",
        ),
    )

    assert isinstance(selected, imager.GCPArtifactRegistryImageAccessor)


def test_image_registry_accessor_factory_selects_plain_registry_accessor():
    registry_conf = SimpleNamespace(push_authority="localhost:5000")

    selected = imager.image_registry_accessor(
        ImageRegistrySurface.KIND_REGISTRY,
        lambda: registry_conf,
    )

    assert isinstance(selected, imager.RemoteRegistryImageAccessor)
    assert selected.registry_conf is registry_conf


def test_gcp_artifact_registry_accessor_push_plan_logs_commands(caplog):
    caplog.set_level("INFO")
    accessor = imager.GCPArtifactRegistryImageAccessor(
        SimpleNamespace(
            registry_authority="us-central1-docker.pkg.dev/workspace-dev/workspace",
            project_id="workspace-dev",
            repository_id="workspace",
        )
    )

    accessor.push_image("workspace/wclone_job_runner", "dev", action=imager.WieldAction.PLAN)

    assert "gcloud auth configure-docker us-central1-docker.pkg.dev --quiet" in caplog.text
    assert (
        "docker tag workspace/wclone_job_runner:dev "
        "us-central1-docker.pkg.dev/workspace-dev/workspace/wclone_job_runner:dev"
    ) in caplog.text


def test_gcp_artifact_registry_accessor_push_apply_runs_publish_commands(monkeypatch, caplog):
    caplog.set_level("INFO")
    calls = []

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            calls.append(cmd)
            self.stdout = iter([f"output from {' '.join(cmd[:2])}\n"])
            self.returncode = 0

        def wait(self):
            return self.returncode

    monkeypatch.setattr(imager.subprocess, "Popen", FakePopen)
    accessor = imager.GCPArtifactRegistryImageAccessor(
        SimpleNamespace(
            registry_authority="us-central1-docker.pkg.dev/workspace-dev/workspace",
            project_id="workspace-dev",
            repository_id="workspace",
        )
    )

    accessor.push_image("workspace/wclone_job_runner", "dev", action=imager.WieldAction.APPLY)

    assert calls == [
        ["gcloud", "auth", "configure-docker", "us-central1-docker.pkg.dev", "--quiet"],
        [
            "docker",
            "tag",
            "workspace/wclone_job_runner:dev",
            "us-central1-docker.pkg.dev/workspace-dev/workspace/wclone_job_runner:dev",
        ],
        [
            "docker",
            "push",
            "us-central1-docker.pkg.dev/workspace-dev/workspace/wclone_job_runner:dev",
        ],
    ]
    assert "running:\ngcloud auth configure-docker us-central1-docker.pkg.dev --quiet" in caplog.text
    assert "running:\ndocker push us-central1-docker.pkg.dev/workspace-dev/workspace/wclone_job_runner:dev" in caplog.text
    assert "output from docker push" in caplog.text
