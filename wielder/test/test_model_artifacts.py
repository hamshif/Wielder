from types import SimpleNamespace

from pyhocon import ConfigFactory

from wielder.models.artifacts import WArtifactFetchConfig, WArtifactFetcher
from wielder.wield.enumerator import WieldAction


class FakeBucketeer:
    def __init__(self):
        self.downloads = []

    def download_objects_tree_by_key(self, bucket_name, root_key="", dest="/tmp"):
        self.downloads.append((bucket_name, root_key, dest))
        return True


def test_artifact_fetch_config_accepts_hocon_and_cache_root():
    conf = ConfigFactory.parse_string(
        """
        cache_root = "/tmp/workspace-models"
        selected_artifacts = ["example_model_v2"]
        artifacts {
          example_model_v2 {
            provider = "huggingface"
            repo_id = "ExampleOrg/example-model-v2"
            revision = "main"
            include = ["*.json", "*.safetensors"]
          }
        }
        """
    )

    config = WArtifactFetchConfig.from_conf(conf)

    assert config.artifact_names == ["example_model_v2"]
    assert config.artifacts["example_model_v2"].resolved_destination("example_model_v2", config.cache_root) == "/tmp/workspace-models/example_model_v2"


def test_huggingface_plan_prints_download_command(capsys):
    results = WArtifactFetcher.plan(
        {
            "cache_root": "/tmp/workspace-models",
            "selected_artifacts": ["example_model_v2"],
            "artifacts": {
                "example_model_v2": {
                    "provider": "huggingface",
                    "repo_id": "ExampleOrg/example-model-v2",
                    "revision": "main",
                    "include": ["*.json"],
                    "exclude": ["*.msgpack"],
                }
            },
        }
    )

    output = capsys.readouterr().out
    assert "hf download ExampleOrg/example-model-v2 --local-dir /tmp/workspace-models/example_model_v2" in output
    assert "--revision main" in output
    assert "--include '*.json'" in output
    assert "--exclude '*.msgpack'" in output
    assert results[0].status == "planned"


def test_huggingface_plan_reports_existing_destination(tmp_path, capsys):
    destination = tmp_path / "example_model_v2"
    destination.mkdir()
    (destination / "README.md").write_text("cached\n")

    results = WArtifactFetcher.plan(
        {
            "selected_artifacts": ["example_model_v2"],
            "artifacts": {
                "example_model_v2": {
                    "provider": "huggingface",
                    "repo_id": "ExampleOrg/example-model-v2",
                    "destination": destination.as_posix(),
                }
            },
        }
    )

    output = capsys.readouterr().out
    assert "already present" in output
    assert "hf download" not in output
    assert results[0].status == "exists"
    assert results[0].command == []


def test_huggingface_apply_skips_existing_destination(monkeypatch, tmp_path):
    destination = tmp_path / "example_model_v2"
    destination.mkdir()
    (destination / "model.bin").write_text("cached\n")

    def forbidden_run(command, capture_output, text):
        raise AssertionError(f"unexpected fetch command: {command}")

    monkeypatch.setattr("wielder.models.artifacts.subprocess.run", forbidden_run)

    results = WArtifactFetcher.apply(
        {
            "selected_artifacts": ["example_model_v2"],
            "artifacts": {
                "example_model_v2": {
                    "provider": "huggingface",
                    "repo_id": "ExampleOrg/example-model-v2",
                    "destination": destination.as_posix(),
                }
            },
        }
    )

    assert results[0].status == "exists"
    assert results[0].command == []


def test_huggingface_apply_fetches_empty_existing_destination(monkeypatch, tmp_path):
    destination = tmp_path / "example_model_v2"
    destination.mkdir()
    commands = []

    def fake_run(command, capture_output, text):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("wielder.models.artifacts.subprocess.run", fake_run)

    results = WArtifactFetcher.apply(
        {
            "selected_artifacts": ["example_model_v2"],
            "artifacts": {
                "example_model_v2": {
                    "provider": "huggingface",
                    "repo_id": "ExampleOrg/example-model-v2",
                    "destination": destination.as_posix(),
                }
            },
        }
    )

    assert commands == [["hf", "download", "ExampleOrg/example-model-v2", "--local-dir", destination.as_posix()]]
    assert results[0].status == "fetched"


def test_ollama_apply_invokes_pull(monkeypatch):
    commands = []

    def fake_run(command, capture_output, text):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("wielder.models.artifacts.subprocess.run", fake_run)

    results = WArtifactFetcher.apply(
        {
            "selected_artifacts": ["llama"],
            "artifacts": {
                "llama": {
                    "provider": "ollama",
                    "model": "llama3.2",
                }
            },
        }
    )

    assert commands == [["ollama", "pull", "llama3.2"]]
    assert results[0].status == "fetched"


def test_bucket_apply_uses_supplied_bucketeer():
    bucketeer = FakeBucketeer()

    results = WArtifactFetcher.apply(
        {
            "selected_artifacts": ["weights"],
            "artifacts": {
                "weights": {
                    "provider": "bucket",
                    "bucket": "workspace-models",
                    "key": "example_model_v2",
                    "destination": "/tmp/workspace-models/example_model_v2",
                }
            },
        },
        bucketeer=bucketeer,
    )

    assert bucketeer.downloads == [("workspace-models", "example_model_v2", "/tmp/workspace-models/example_model_v2")]
    assert results[0].status == "fetched"


def test_bucket_apply_skips_existing_destination(tmp_path):
    destination = tmp_path / "example_model_v2"
    destination.mkdir()
    (destination / "weights.bin").write_text("cached\n")
    bucketeer = FakeBucketeer()

    results = WArtifactFetcher.apply(
        {
            "selected_artifacts": ["weights"],
            "artifacts": {
                "weights": {
                    "provider": "bucket",
                    "bucket": "workspace-models",
                    "key": "example_model_v2",
                    "destination": destination.as_posix(),
                }
            },
        },
        bucketeer=bucketeer,
    )

    assert bucketeer.downloads == []
    assert results[0].status == "exists"


def test_rclone_plan_uses_configured_rclone_uri(capsys):
    results = WArtifactFetcher.plan(
        {
            "wclone_config_path": "/tmp/rclone.conf",
            "common_flags": ["--fast-list"],
            "selected_artifacts": ["weights"],
            "artifacts": {
                "weights": {
                    "provider": "rclone",
                    "rclone_uri": "workspace_models:models/example_model_v2",
                    "destination": "/tmp/workspace-models/example_model_v2",
                }
            },
        }
    )

    output = capsys.readouterr().out
    assert "rclone copy workspace_models:models/example_model_v2 /tmp/workspace-models/example_model_v2 --config /tmp/rclone.conf --fast-list" in output
    assert results[0].command[:4] == [
        "rclone",
        "copy",
        "workspace_models:models/example_model_v2",
        "/tmp/workspace-models/example_model_v2",
    ]
