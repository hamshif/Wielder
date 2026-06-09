import json
import os
import base64
import tarfile
from configparser import ConfigParser
from pathlib import Path

import pytest

from wielder.util.cloud_identity import GCPMetadataAWSWebIdentity, WCloudIdentity, WCloudSurface
from wielder.util.wcloner import (
    WCloneConfig,
    WCloneEndpoint,
    WCloneToolConfiguration,
    WCloneToolRemote,
    WCloner,
    WCloneSpec,
    WCloneSyncType,
)
from wielder.wield.enumerator import WieldAction


def test_google_drive_folder_url_uses_human_browser_path():
    assert WCloner.google_drive_folder_url("abc123") == "https://drive.google.com/drive/folders/abc123"


def test_google_drive_human_path_uses_shared_drive_breadcrumb():
    assert WCloner.google_drive_human_path("workspace-cro-mirrors-dev", "provider") == "Shared Drives/workspace-cro-mirrors-dev/provider"


def test_local_path_to_drive_bucket_sync_uses_rclone_sync_without_backup_dir(tmp_path):
    source_dir = tmp_path / "assay_harmonization"
    source_dir.mkdir()

    spec = WCloneSpec(
        source=WCloneEndpoint(
            name="local_source",
            provider="local",
            display_uri=source_dir.as_posix(),
            rclone_remote="local",
            rclone_uri=source_dir.as_posix(),
            source="local_path",
        ),
        sinks={
            "google_drive": WCloneEndpoint(
                name="google_drive",
                provider="google_drive",
                display_uri="Google Shared Drive: workspace-biolab-dev/assay_harmonization/provider/in-vitro",
                rclone_remote="workspace_drive",
                bucket="workspace-biolab-dev",
                key="assay_harmonization/provider/in-vitro",
                shared_drive=True,
                create_destination=True,
                mutation_allowed=True,
                source="local_path",
            )
        },
        wclone_config_path=(tmp_path / "wclone.conf").as_posix(),
        backup_enabled=False,
    )

    command = WCloner(
        spec=spec,
        action=WieldAction.APPLY,
        sync_type=WCloneSyncType.LOCAL_PATH_TO_DRIVE_BUCKET,
    ).build_command("google_drive")

    assert command.command[:4] == [
        "rclone",
        "sync",
        source_dir.as_posix(),
        "workspace_drive:assay_harmonization/provider/in-vitro",
    ]
    assert "--backup-dir" not in command.command


def test_local_path_to_drive_bucket_backup_dir_stays_outside_destination_folder(tmp_path, monkeypatch):
    source_dir = tmp_path / "partner"
    source_dir.mkdir()

    spec = WCloneSpec(
        source=WCloneEndpoint(
            name="local_source",
            provider="local",
            display_uri=source_dir.as_posix(),
            rclone_remote="local",
            rclone_uri=source_dir.as_posix(),
            source="local_path",
        ),
        sinks={
            "google_drive": WCloneEndpoint(
                name="google_drive",
                provider="google_drive",
                display_uri="Google Shared Drive: workspace-cro-mirrors-dev/partner",
                rclone_remote="workspace_drive",
                bucket="workspace-cro-mirrors-dev",
                key="partner",
                shared_drive=True,
                create_destination=True,
                mutation_allowed=True,
                source="local_path",
            )
        },
        wclone_config_path=(tmp_path / "wclone.conf").as_posix(),
        backup_enabled=True,
    )
    cloner = WCloner(
        spec=spec,
        action=WieldAction.APPLY,
        sync_type=WCloneSyncType.LOCAL_PATH_TO_DRIVE_BUCKET,
    )
    monkeypatch.setattr(cloner, "new_run_id", lambda: "20260510T000000Z")

    command = cloner.build_command("google_drive")
    effective_command = cloner.effective_drive_sync_command(
        command,
        spec.sinks["google_drive"],
        {"id": "drive-id", "prefix_id": "partner-folder-id"},
    )

    backup_uri = effective_command[effective_command.index("--backup-dir") + 1]
    assert effective_command[3] == "workspace_drive,team_drive=drive-id,root_folder_id=partner-folder-id:"
    assert backup_uri == (
        "workspace_drive,team_drive=drive-id:_wielder/raw_mirror_diff_shadow/partner/20260510T000000Z"
    )


def test_configure_wclone_apply_writes_non_secret_remotes(tmp_path):
    config_path = tmp_path / "rclone.conf"
    configuration = WCloneToolConfiguration(
        path=config_path.as_posix(),
        remotes=[
            WCloneToolRemote(
                name="workspace_gcs",
                backend="gcs",
                options={"project_number": "workspace-dev", "user_project": "workspace-dev", "env_auth": True},
            ),
            WCloneToolRemote(
                name="workspace_aws",
                backend="s3",
                options={"provider": "AWS", "env_auth": True, "region": "us-east-1", "acl": "private"},
            ),
        ],
    )

    WCloner.configure_wclone([configuration], action=WieldAction.APPLY)

    contents = config_path.read_text()
    assert "[workspace_gcs]" in contents
    assert "type = gcs" in contents
    assert "project_number = workspace-dev" in contents
    assert "env_auth = true" in contents
    assert "[workspace_aws]" in contents
    assert "provider = AWS" in contents
    assert oct(config_path.stat().st_mode & 0o777) == "0o600"


def test_wclone_config_adds_local_remote_for_local_sink_backup(tmp_path):
    config_path = tmp_path / "rclone.conf"
    config = WCloneConfig.from_conf(
        {
            "wclone_config_path": config_path.as_posix(),
            "sync_type": "wclone",
            "selected_jobs": ["gcs_to_local"],
            "backup_enabled": True,
            "wclone_configs": [
                {
                    "path": config_path.as_posix(),
                    "remotes": [
                        {
                            "name": "workspace_models_gcs",
                            "backend": "gcs",
                            "options": {"project_number": "workspace-dev", "user_project": "workspace-dev"},
                        }
                    ],
                }
            ],
            "jobs": {
                "gcs_to_local": {
                    "src": {
                        "provider": "gcs",
                        "display_uri": "gs://workspace-model-artifacts-dev/models",
                        "rclone_remote": "workspace_models_gcs",
                        "bucket": "workspace-model-artifacts-dev",
                        "key": "models",
                    },
                    "sink": {
                        "provider": "local",
                        "display_uri": (tmp_path / "model_artifacts").as_posix(),
                        "rclone_remote": "local",
                        "rclone_uri": (tmp_path / "model_artifacts").as_posix(),
                        "source": "local_path",
                        "mutation_allowed": True,
                    },
                }
            },
        }
    )

    WCloner.configure_wclone(config.wclone_configs, action=WieldAction.APPLY)

    parser = ConfigParser()
    parser.read(config_path)
    assert parser.get("local", "type") == "local"


def test_configure_wclone_probe_writes_exact_remote_config(tmp_path):
    config_path = tmp_path / "rclone.conf"
    config_path.write_text(
        "[workspace_gcs]\n"
        "type = gcs\n"
        "project_number = stale-project\n"
        "user_project = stale-project\n"
        "env_auth = true\n"
        "bucket_policy_only = true\n"
    )
    configuration = WCloneToolConfiguration(
        path=config_path.as_posix(),
        remotes=[
            WCloneToolRemote(
                name="workspace_gcs",
                backend="gcs",
                options={"project_number": "workspace-dev", "user_project": "workspace-dev", "bucket_policy_only": True},
            ),
        ],
    )

    WCloner.configure_wclone([configuration], action=WieldAction.PROBE)

    contents = config_path.read_text()
    assert "project_number = workspace-dev" in contents
    assert "user_project = workspace-dev" in contents
    assert "bucket_policy_only = true" in contents
    assert "env_auth" not in contents
    assert oct(config_path.stat().st_mode & 0o777) == "0o600"


def test_object_store_backup_dir_stays_outside_destination_prefix(tmp_path):
    spec = WCloneSpec(
        source=WCloneEndpoint(
            name="local_source",
            provider="local",
            display_uri="/tmp/local-partner",
            rclone_remote="local",
            rclone_uri="/tmp/local-partner",
            source="local_path",
        ),
        sinks={
            "target": WCloneEndpoint(
                name="gcs_target",
                provider="gcs",
                display_uri="gs://workspace-cro-mirrors-dev/partner",
                rclone_remote="workspace_gcs",
                bucket="workspace-cro-mirrors-dev",
                key="partner",
                create_destination=False,
                mutation_allowed=True,
                source="local_path",
            )
        },
        wclone_config_path=(tmp_path / "wclone.conf").as_posix(),
        backup_enabled=True,
    )

    command = WCloner(
        spec=spec,
        action=WieldAction.APPLY,
        sync_type=WCloneSyncType.WCLONE,
    ).build_command("target").command

    assert command[3] == "workspace_gcs:workspace-cro-mirrors-dev/partner"
    backup_uri = command[command.index("--backup-dir") + 1]
    assert backup_uri.startswith("workspace_gcs:workspace-cro-mirrors-dev/_wielder/raw_mirror_diff_shadow/partner/")
    assert not backup_uri.startswith("workspace_gcs:workspace-cro-mirrors-dev/partner/")


def test_wclone_operation_can_use_rclone_copy(tmp_path):
    spec = WCloneSpec(
        source=WCloneEndpoint(
            name="gcs_source",
            provider="gcs",
            display_uri="gs://workspace-cro-mirrors-dev/partner",
            rclone_remote="workspace_gcs",
            bucket="workspace-cro-mirrors-dev",
            key="partner",
        ),
        sinks={
            "target": WCloneEndpoint(
                name="drive_target",
                provider="google_drive",
                display_uri="Google Shared Drive: workspace-cro-mirrors-dev/partner",
                rclone_remote="workspace_drive",
                bucket="workspace-cro-mirrors-dev",
                key="partner",
                shared_drive=True,
                mutation_allowed=True,
            )
        },
        wclone_config_path=(tmp_path / "wclone.conf").as_posix(),
        backup_enabled=False,
        operation="copy",
    )

    command = WCloner(
        spec=spec,
        action=WieldAction.APPLY,
        sync_type=WCloneSyncType.WCLONE,
    ).build_command("target").command

    assert command[:4] == [
        "rclone",
        "copy",
        "workspace_gcs:workspace-cro-mirrors-dev/partner",
        "workspace_drive:partner",
    ]
    assert "--backup-dir" not in command


def test_verify_nonempty_sync_skips_missing_destination_when_source_empty(tmp_path, monkeypatch, capsys):
    spec = WCloneSpec(
        source=WCloneEndpoint(
            name="gcs_source",
            provider="gcs",
            display_uri="gs://workspace-artifactory-dev/models",
            rclone_remote="workspace_models_gcs",
            bucket="workspace-artifactory-dev",
            key="models",
        ),
        sinks={
            "target": WCloneEndpoint(
                name="local_target",
                provider="local",
                display_uri=(tmp_path / "model_artifacts").as_posix(),
                rclone_remote="local",
                rclone_uri=(tmp_path / "model_artifacts").as_posix(),
                source="local_path",
                mutation_allowed=True,
            )
        },
        wclone_config_path=(tmp_path / "rclone.conf").as_posix(),
        backup_enabled=True,
        operation="copy",
    )
    cloner = WCloner(spec=spec, action=WieldAction.APPLY, sync_type=WCloneSyncType.WCLONE)
    command = cloner.build_command("target")
    calls = []

    def fake_rclone_count(uri, config_path):
        calls.append(uri)
        if uri == command.source_uri:
            return 0
        raise AssertionError("destination count should be skipped when source is empty")

    monkeypatch.setattr(cloner, "rclone_count", fake_rclone_count)

    cloner.verify_nonempty_sync(command, command.command)

    assert calls == [command.source_uri]
    assert "source files: 0" in capsys.readouterr().out


def test_wclone_google_shared_drive_sink_uses_resolved_folder_id(tmp_path):
    spec = WCloneSpec(
        source=WCloneEndpoint(
            name="gcs_source",
            provider="gcs",
            display_uri="gs://workspace-cro-mirrors-dev/partner",
            rclone_remote="workspace_gcs",
            bucket="workspace-cro-mirrors-dev",
            key="partner",
        ),
        sinks={
            "target": WCloneEndpoint(
                name="drive_target",
                provider="google_drive",
                display_uri="Google Shared Drive: workspace-cro-mirrors-dev/partner",
                rclone_remote="workspace_drive",
                bucket="workspace-cro-mirrors-dev",
                key="partner",
                shared_drive=True,
                mutation_allowed=True,
            )
        },
        wclone_config_path=(tmp_path / "wclone.conf").as_posix(),
        backup_enabled=False,
        operation="copy",
    )
    cloner = WCloner(
        spec=spec,
        action=WieldAction.APPLY,
        sync_type=WCloneSyncType.WCLONE,
    )
    command = cloner.build_command("target")

    effective_command = cloner.effective_sync_command(
        command,
        spec.sinks["target"],
        {"id": "drive-id", "prefix_id": "partner-folder-id"},
    )

    assert effective_command[:4] == [
        "rclone",
        "copy",
        "workspace_gcs:workspace-cro-mirrors-dev/partner",
        "workspace_drive,team_drive=drive-id,root_folder_id=partner-folder-id:",
    ]


def test_configure_wclone_plan_does_not_write_config(tmp_path):
    config_path = tmp_path / "rclone.conf"
    configuration = WCloneToolConfiguration(
        path=config_path.as_posix(),
        remotes=[WCloneToolRemote(name="workspace_gcs", backend="gcs", options={"env_auth": True})],
    )

    WCloner.configure_wclone([configuration], action=WieldAction.PLAN)

    assert not config_path.exists()


def test_wclone_remote_rejects_sensitive_options_by_default():
    with pytest.raises(ValueError, match="Refusing sensitive wclone backend options"):
        WCloneToolRemote(
            name="unsafe",
            backend="gcs",
            options={"access_token": "do-not-store"},
        )


def test_wclone_job_can_disable_post_sync_verification():
    config = WCloneConfig.from_conf(
        {
            "wclone_config_path": "/tmp/wclone.conf",
            "verify_after_sync": True,
            "selected_jobs": ["large_sharepoint"],
            "jobs": {
                "large_sharepoint": {
                    "verify_after_sync": False,
                    "src": {
                        "provider": "rclone",
                        "display_uri": "Microsoft SharePoint",
                        "rclone_remote": "partner_sharepoint",
                        "rclone_uri": "partner_sharepoint:",
                    },
                    "sink": {
                        "provider": "gcs",
                        "display_uri": "gs://workspace-cro-mirrors-dev/partner",
                        "rclone_remote": "workspace_gcs",
                        "bucket": "workspace-cro-mirrors-dev",
                        "key": "partner",
                        "mutation_allowed": True,
                    },
                }
            },
        }
    )

    assert config.spec_for_job("large_sharepoint").verify_after_sync is False


def test_microsoft_graph_token_injection_uses_azure_cli_payload(monkeypatch):
    config = {
        "wclone_config_path": "/tmp/wclone.conf",
        "selected_jobs": ["common"],
        "microsoft_graph_access_token_remotes": ["partner_sharepoint"],
        "microsoft_graph_tenant_id": "tenant-id",
        "microsoft_graph_resource": "https://graph.microsoft.com",
        "jobs": {
            "common": {
                "src": {
                    "provider": "rclone",
                    "display_uri": "Microsoft SharePoint",
                    "rclone_remote": "partner_sharepoint",
                    "rclone_uri": "partner_sharepoint:",
                },
                "sink": {
                    "provider": "local",
                    "display_uri": "/tmp/partner",
                    "rclone_remote": "local",
                    "rclone_uri": "/tmp/partner",
                    "mutation_allowed": True,
                },
            }
        },
    }

    monkeypatch.delenv("RCLONE_CONFIG_PARTNER_SHAREPOINT_TOKEN", raising=False)
    monkeypatch.setattr(
        WCloner,
        "azure_cli_graph_token",
        staticmethod(
            lambda tenant_id, resource: {
                "accessToken": "graph-token",
                "tokenType": "Bearer",
                "expires_on": "1779062400",
            }
        ),
    )

    WCloner.inject_microsoft_graph_access_tokens(WCloneConfig.from_conf(config))

    token = json.loads(os.environ["RCLONE_CONFIG_PARTNER_SHAREPOINT_TOKEN"])
    assert token["access_token"] == "graph-token"
    assert token["token_type"] == "Bearer"
    assert token["expiry"] == "2026-05-18T00:00:00Z"


def test_microsoft_graph_token_injection_requires_tenant(monkeypatch):
    monkeypatch.delenv("RCLONE_CONFIG_PARTNER_SHAREPOINT_TOKEN", raising=False)
    config = WCloneConfig.from_conf(
        {
            "wclone_config_path": "/tmp/wclone.conf",
            "selected_jobs": ["common"],
            "microsoft_graph_access_token_remotes": ["partner_sharepoint"],
            "jobs": {
                "common": {
                    "src": {
                        "provider": "rclone",
                        "display_uri": "Microsoft SharePoint",
                        "rclone_remote": "partner_sharepoint",
                        "rclone_uri": "partner_sharepoint:",
                    },
                    "sink": {
                        "provider": "local",
                        "display_uri": "/tmp/partner",
                        "rclone_remote": "local",
                        "rclone_uri": "/tmp/partner",
                        "mutation_allowed": True,
                    },
                }
            },
        }
    )

    with pytest.raises(RuntimeError, match="microsoft_graph_tenant_id is required"):
        WCloner.inject_microsoft_graph_access_tokens(config)


def test_microsoft_graph_token_injection_can_materialize_azure_config_archive(tmp_path, monkeypatch):
    archive_path = tmp_path / "azure-cache.tgz"
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "azureProfile.json").write_text("{}")
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(source_dir / "azureProfile.json", arcname="azureProfile.json")
    archive = base64.b64encode(archive_path.read_bytes()).decode()

    config = WCloneConfig.from_conf(
        {
            "wclone_config_path": "/tmp/wclone.conf",
            "selected_jobs": ["common"],
            "microsoft_graph_access_token_remotes": ["partner_sharepoint"],
            "microsoft_graph_tenant_id": "tenant-id",
            "microsoft_graph_azure_config_archive_env": "AZURE_CONFIG_ARCHIVE_TGZ_B64",
            "jobs": {
                "common": {
                    "src": {
                        "provider": "rclone",
                        "display_uri": "Microsoft SharePoint",
                        "rclone_remote": "partner_sharepoint",
                        "rclone_uri": "partner_sharepoint:",
                    },
                    "sink": {
                        "provider": "local",
                        "display_uri": "/tmp/partner",
                        "rclone_remote": "local",
                        "rclone_uri": "/tmp/partner",
                        "mutation_allowed": True,
                    },
                }
            },
        }
    )
    monkeypatch.setenv("AZURE_CONFIG_ARCHIVE_TGZ_B64", archive)
    monkeypatch.delenv("AZURE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("RCLONE_CONFIG_PARTNER_SHAREPOINT_TOKEN", raising=False)
    monkeypatch.setattr(
        WCloner,
        "azure_cli_graph_token",
        staticmethod(
            lambda tenant_id, resource: {
                "accessToken": Path(os.environ["AZURE_CONFIG_DIR"], "azureProfile.json").read_text(),
                "tokenType": "Bearer",
            }
        ),
    )

    WCloner.inject_microsoft_graph_access_tokens(config)

    assert json.loads(os.environ["RCLONE_CONFIG_PARTNER_SHAREPOINT_TOKEN"])["access_token"] == "{}"


def test_wcloner_show_accepts_config_contract(tmp_path, capsys):
    WCloner.show(
        {
            "wclone_config_path": (tmp_path / "wclone.conf").as_posix(),
            "sync_type": "wclone",
            "selected_jobs": ["common"],
            "common_flags": ["--progress"],
            "wclone_configs": [],
            "jobs": {
                "common": {
                    "src": {
                        "provider": "s3",
                        "display_uri": "s3://workspace-common",
                        "rclone_remote": "workspace_aws",
                        "bucket": "workspace-common",
                        "key": "/",
                    },
                    "sink": {
                        "provider": "gcs",
                        "display_uri": "gs://workspace-common",
                        "rclone_remote": "workspace_gcs",
                        "bucket": "workspace-common",
                        "key": "/",
                    },
                }
            },
        }
    )

    output = capsys.readouterr().out
    assert "src: s3://workspace-common" in output
    assert "dst: gs://workspace-common" in output
    assert "wclone sync workspace_aws:workspace-common workspace_gcs:workspace-common" in output


def test_s3_clone_can_use_gcp_backed_aws_web_identity(tmp_path, monkeypatch):
    token_file = tmp_path / "aws-web-identity.jwt"
    spec = WCloneSpec(
        source=WCloneEndpoint(
            name="s3_source",
            provider="s3",
            display_uri="s3://workspace-common",
            rclone_remote="workspace_aws",
            bucket="workspace-common",
            key="/",
        ),
        sinks={
            "target": WCloneEndpoint(
                name="gcs_target",
                provider="gcs",
                display_uri="gs://workspace-common",
                rclone_remote="workspace_gcs",
                bucket="workspace-common",
                key="/",
                create_destination=True,
                mutation_allowed=True,
            )
        },
        wclone_config_path=(tmp_path / "wclone.conf").as_posix(),
        cloud_identities=[
            WCloudIdentity.from_conf(
                {
                    "identity_type": "gcp_metadata_aws_web_identity",
                    "role_arn": "arn:aws:iam::123456789012:role/domain-datalake-ingestion-raw-gcp-wclone-dev",
                    "audience": "sts.amazonaws.com",
                    "token_file": token_file.as_posix(),
                    "region": "us-east-1",
                    "session_name": "workspace-common-buckets-wclone-dev",
                    "refresh_interval_seconds": 0,
                }
            )
        ],
        backup_enabled=False,
    )
    cloner = WCloner(spec=spec, action=WieldAction.APPLY, sync_type=WCloneSyncType.WCLONE)
    assert spec.cloud_identities[0].lives_on_surface == WCloudSurface.GCP
    assert spec.cloud_identities[0].known_to_surface == WCloudSurface.AWS
    monkeypatch.setattr(GCPMetadataAWSWebIdentity, "token", lambda self: "google-oidc-token")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "stale")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "stale")
    command = cloner.build_command("target")

    env = cloner.subprocess_env(command.command)

    assert token_file.read_text() == "google-oidc-token"
    assert oct(token_file.stat().st_mode & 0o777) == "0o600"
    assert env["AWS_ROLE_ARN"] == spec.cloud_identities[0].role_arn
    assert env["AWS_WEB_IDENTITY_TOKEN_FILE"] == token_file.as_posix()
    assert env["AWS_ROLE_SESSION_NAME"] == "workspace-common-buckets-wclone-dev"
    assert env["AWS_REGION"] == "us-east-1"
    assert "AWS_ACCESS_KEY_ID" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
