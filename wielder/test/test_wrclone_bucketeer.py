import json
from types import SimpleNamespace

from pyhocon import ConfigFactory

from wielder.util.bucketeer import WRcloneBucketeer
from wielder.wield.enumerator import WieldAction


def test_wrclone_bucketeer_configures_rclone_from_hocon(tmp_path):
    config_path = tmp_path / "rclone.conf"
    conf = ConfigFactory.parse_string(
        f"""
        rclone_remote = "workspace_models"
        rclone_config_path = "{config_path.as_posix()}"
        wclone_configs = [
          {{
            path = "{config_path.as_posix()}"
            remotes = [
              {{
                name = "workspace_models"
                backend = "s3"
                options = {{
                  provider = "AWS"
                  env_auth = true
                  region = "us-east-1"
                }}
              }}
            ]
          }}
        ]
        """
    )

    WRcloneBucketeer(rclone_conf=conf, action=WieldAction.APPLY)

    contents = config_path.read_text()
    assert "[workspace_models]" in contents
    assert "type = s3" in contents
    assert "provider = AWS" in contents
    assert "env_auth = true" in contents
    assert oct(config_path.stat().st_mode & 0o777) == "0o600"


def test_wrclone_bucketeer_lists_and_downloads_with_rclone_commands(tmp_path, monkeypatch):
    config_path = tmp_path / "rclone.conf"
    conf = {
        "rclone_remote": "workspace_models",
        "rclone_config_path": config_path.as_posix(),
        "configure_on_init": False,
        "common_flags": ["--fast-list"],
    }
    commands = []

    def fake_run(command, capture_output, text):
        commands.append(command)
        if command[1] == "lsjson":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    [
                        {"Path": "config.json", "IsDir": False},
                        {"Path": "weights/model.safetensors", "IsDir": False},
                    ]
                ),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("wielder.util.bucketeer.subprocess.run", fake_run)

    bucketeer = WRcloneBucketeer(rclone_conf=conf)
    object_names = bucketeer.get_object_names("models", "example_model_v2")
    destination = tmp_path / "example_model_v2"
    bucketeer.download_objects_tree_by_key("models", "example_model_v2", destination.as_posix())

    assert object_names == [
        "example_model_v2/config.json",
        "example_model_v2/weights/model.safetensors",
    ]
    assert commands[0] == [
        "rclone",
        "lsjson",
        "workspace_models:models/example_model_v2",
        "--recursive",
        "--files-only",
        "--config",
        config_path.as_posix(),
    ]
    assert commands[1] == [
        "rclone",
        "copy",
        "workspace_models:models/example_model_v2",
        destination.as_posix(),
        "--config",
        config_path.as_posix(),
        "--fast-list",
    ]
