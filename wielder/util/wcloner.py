"""Wielder-native clone/mirror execution helpers."""

import base64
import json
import logging
import os
import shlex
import subprocess
import tarfile
import tempfile
from configparser import ConfigParser
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from io import BytesIO
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wielder.util.bucketeer import Bucketeer, get_ecosystem_bucketeer
from wielder.util.cloud_identity import WCloudIdentity, WCloudSurface
from wielder.util.credential_helper import require_aws_mfa_cred
from wielder.wield.enumerator import WieldAction


logger = logging.getLogger(__name__)
EndpointProvider = Literal["google_drive", "s3", "gcs", "rclone", "local"]
EndpointSource = Literal["private_drive", "drive_bucket", "local_path"]
RcloneOperation = Literal["sync", "copy"]


class WCloneSyncType(str, Enum):
    PRIVATE_DRIVE_TO_DRIVE_BUCKET = "private_drive_to_drive_bucket"
    LOCAL_PATH_TO_DRIVE_BUCKET = "local_path_to_drive_bucket"
    DRIVE_BUCKET_TO_OBJECT_STORE = "drive_bucket_to_object_store"
    WCLONE = "wclone"
    RCLONE = "rclone"


class WCloneToolRemote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    backend: str
    options: dict[str, str | bool | int | float] = Field(default_factory=dict)
    allow_sensitive_options: bool = False

    @field_validator("name", "backend")
    @classmethod
    def require_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value

    @field_validator("name", "backend")
    @classmethod
    def reject_unsafe_remote_tokens(cls, value: str) -> str:
        if any(char in value for char in [":", ",", "[", "]", "\\"]):
            raise ValueError(f"unsafe rclone token [{value}]")
        return value

    @model_validator(mode="after")
    def reject_sensitive_options_by_default(self):
        if self.allow_sensitive_options:
            return self
        sensitive_tokens = ("token", "secret", "password", "credential", "access_key", "refresh")
        sensitive_options = [
            option
            for option in self.options
            if any(sensitive_token in option.lower() for sensitive_token in sensitive_tokens)
        ]
        if sensitive_options:
            raise ValueError(
                f"Refusing sensitive wclone backend options for remote [{self.name}]: {sensitive_options}. "
                "Inject credentials through runtime environment or explicitly allow sensitive options."
            )
        return self


class WCloneToolConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    remotes: list[WCloneToolRemote] = Field(default_factory=list)

    @field_validator("path")
    @classmethod
    def require_config_path(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("wclone backend config path must not be empty")
        if "\\" in value:
            raise ValueError(f"Refusing wclone backend config path with backslash: {value}")
        return value


class WCloneDriveRbacPermission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    type: str
    email: str


class WCloneEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    provider: EndpointProvider
    display_uri: str
    rclone_remote: str
    rclone_uri: str | None = None
    folder_id: str | None = None
    bucket: str | None = None
    key: str | None = None
    region: str | None = None
    shared_drive: bool = False
    create_destination: bool = False
    mutation_allowed: bool = False
    enabled: bool = True
    source: EndpointSource = "private_drive"
    rbac_permissions: list[WCloneDriveRbacPermission] = Field(default_factory=list)

    @field_validator("rclone_remote", "display_uri", "name")
    @classmethod
    def require_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value

    @field_validator("folder_id", "bucket", "key", "rclone_uri")
    @classmethod
    def reject_backslashes(cls, value: str | None) -> str | None:
        if value is not None and "\\" in value:
            raise ValueError(f"backslash is not allowed in clone endpoint value [{value}]")
        return value

    @model_validator(mode="after")
    def validate_provider_contract(self):
        if self.name == "private_drive" and self.provider == "google_drive" and not self.folder_id:
            raise ValueError("private Google Drive source endpoints require folder_id")
        if self.provider == "local" and not self.rclone_uri:
            raise ValueError("local endpoints require rclone_uri")
        if self.shared_drive and (not self.bucket or not self.key):
            raise ValueError("shared drive endpoints require bucket and key")
        if self.provider in {"s3", "gcs"} and (not self.bucket or not self.key):
            raise ValueError(f"{self.provider} endpoints require bucket and key")
        return self


class WCloneSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: WCloneEndpoint
    sinks: dict[str, WCloneEndpoint]
    wclone_config_path: str | None = None
    rclone_config_path: str | None = None
    common_flags: list[str] = Field(default_factory=list)
    apply_flags: list[str] = Field(default_factory=list)
    drive_bucket_sink: str = "google_drive"
    aws_mfa_role: str | None = None
    cloud_identities: list[WCloudIdentity] = Field(default_factory=list)
    backup_enabled: bool = True
    operation: RcloneOperation = "sync"
    verify_after_sync: bool = True

    @field_validator("wclone_config_path", "rclone_config_path")
    @classmethod
    def reject_empty_config_path(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("wclone_config_path must not be empty")
        if value is not None and "\\" in value:
            raise ValueError(f"Refusing WClone backend config path with backslash: {value}")
        return value

    @field_validator("cloud_identities", mode="before")
    @classmethod
    def validate_cloud_identities(cls, values) -> list[WCloudIdentity]:
        return [WCloudIdentity.from_conf(value) for value in values or []]

    @model_validator(mode="after")
    def normalize_config_path(self):
        config_path = self.wclone_config_path or self.rclone_config_path
        if not config_path:
            raise ValueError("wclone_config_path must not be empty")
        if self.aws_mfa_role and self.cloud_identities:
            raise ValueError("WCloneSpec cannot use both aws_mfa_role and cloud_identities.")
        self.wclone_config_path = config_path
        self.rclone_config_path = config_path
        return self


@dataclass(frozen=True)
class WCloneCommand:
    sink_name: str
    source_uri: str
    sink_uri: str
    source_display_uri: str
    sink_display_uri: str
    backup_uri: str
    config_path: Path
    command: list[str]
    action: WieldAction
    sync_type: WCloneSyncType
    rbac_permissions: tuple[tuple[str, str, str], ...]


BUCKETEER_TYPES_BY_PROVIDER = {
    "google_drive": "GoogleBucketeer",
    "s3": "AWSBucketeer",
    "gcs": "GCSBucketeer",
}


WCloneRcloneRemote = WCloneToolRemote
WCloneRcloneConfiguration = WCloneToolConfiguration


def _plain_conf(value):
    if hasattr(value, "as_plain_ordered_dict"):
        return value.as_plain_ordered_dict()
    return value


class WCloneJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    src: dict
    sink: dict
    verify_after_sync: bool | None = None

    def endpoint(self, key: Literal["src", "sink"], name: str) -> WCloneEndpoint:
        endpoint = dict(_plain_conf(getattr(self, key)))
        endpoint.setdefault("name", name)
        return WCloneEndpoint.model_validate(endpoint)


class WCloneConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wclone_config_path: str
    sync_type: WCloneSyncType = WCloneSyncType.WCLONE
    selected_jobs: list[str] = Field(default_factory=list)
    common_flags: list[str] = Field(default_factory=list)
    apply_flags: list[str] = Field(default_factory=list)
    backup_enabled: bool = False
    operation: RcloneOperation = "sync"
    verify_after_sync: bool = True
    aws_mfa_role: str | None = None
    cloud_identities: list[WCloudIdentity] = Field(default_factory=list)
    gcloud_access_token_remotes: list[str] = Field(default_factory=list)
    microsoft_graph_access_token_remotes: list[str] = Field(default_factory=list)
    microsoft_graph_tenant_id: str | None = None
    microsoft_graph_resource: str = "https://graph.microsoft.com"
    microsoft_graph_azure_config_archive_env: str | None = None
    wclone_configs: list[WCloneToolConfiguration] = Field(default_factory=list)
    storage_loci: dict[str, dict[str, dict]] = Field(default_factory=dict)
    jobs: dict[str, WCloneJob] = Field(default_factory=dict)

    @classmethod
    def from_conf(cls, conf) -> "WCloneConfig":
        return cls.model_validate(_plain_conf(conf))

    @field_validator("wclone_config_path")
    @classmethod
    def require_config_path(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("wclone_config_path must not be empty")
        if "\\" in value:
            raise ValueError(f"Refusing WClone backend config path with backslash: {value}")
        return value

    @field_validator("cloud_identities", mode="before")
    @classmethod
    def validate_cloud_identities(cls, values) -> list[WCloudIdentity]:
        return [WCloudIdentity.from_conf(value) for value in values or []]

    @model_validator(mode="after")
    def validate_jobs(self):
        if not self.jobs:
            raise ValueError("WClone config requires at least one job.")
        missing_jobs = [job_name for job_name in self.job_names if job_name not in self.jobs]
        if missing_jobs:
            raise ValueError(f"Selected WClone jobs are not configured: {missing_jobs}")
        if self.aws_mfa_role and self.cloud_identities:
            raise ValueError("WClone config cannot use both aws_mfa_role and cloud_identities.")
        self.ensure_local_remotes_configured()
        return self

    @property
    def job_names(self) -> list[str]:
        return self.selected_jobs or list(self.jobs.keys())

    def ensure_local_remotes_configured(self) -> None:
        local_remotes = self.local_endpoint_remotes()
        if not local_remotes:
            return
        for configuration in self.wclone_configs:
            configured_remotes = {remote.name for remote in configuration.remotes}
            for remote_name in sorted(local_remotes - configured_remotes):
                configuration.remotes.append(WCloneToolRemote(name=remote_name, backend="local"))

    def local_endpoint_remotes(self) -> set[str]:
        remotes: set[str] = set()
        for job_name in self.job_names:
            job = self.jobs[job_name]
            for endpoint_key, endpoint_name in [("src", f"{job_name}_source"), ("sink", f"{job_name}_target")]:
                endpoint = job.endpoint(endpoint_key, endpoint_name)
                if endpoint.provider == "local":
                    remotes.add(endpoint.rclone_remote)
        return remotes

    def spec_for_job(self, job_name: str) -> WCloneSpec:
        job = self.jobs[job_name]
        return WCloneSpec(
            source=job.endpoint("src", f"{job_name}_source"),
            sinks={"target": job.endpoint("sink", f"{job_name}_target")},
            wclone_config_path=self.wclone_config_path,
            common_flags=self.common_flags,
            apply_flags=self.apply_flags,
            aws_mfa_role=self.aws_mfa_role,
            cloud_identities=self.cloud_identities,
            backup_enabled=self.backup_enabled,
            operation=self.operation,
            verify_after_sync=job.verify_after_sync if job.verify_after_sync is not None else self.verify_after_sync,
        )


class WCloneToolConfigFactory:
    @classmethod
    def configure(cls, configurations: list[WCloneToolConfiguration], action: WieldAction) -> None:
        for configuration in configurations:
            cls.configure_one(configuration, action=action)

    @classmethod
    def configure_one(cls, configuration: WCloneToolConfiguration, action: WieldAction) -> None:
        path = Path(configuration.path).expanduser()
        if action in {WieldAction.SHOW, WieldAction.PLAN}:
            cls.print_plan(path=path, remotes=configuration.remotes, action=action)
            return
        if action not in {WieldAction.APPLY, WieldAction.PROBE}:
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        parser = cls.parser()
        if path.exists():
            parser.read(path)
        for remote in configuration.remotes:
            if not parser.has_section(remote.name):
                parser.add_section(remote.name)
            desired_options = {"type", *map(str, remote.options.keys())}
            for option in parser.options(remote.name):
                if option not in desired_options:
                    parser.remove_option(remote.name, option)
            parser.set(remote.name, "type", remote.backend)
            for option, value in remote.options.items():
                parser.set(remote.name, str(option), cls.option_value(value))
        with path.open("w") as config_file:
            parser.write(config_file)
        path.chmod(0o600)
        cls.print_plan(path=path, remotes=configuration.remotes, action=action)

    @staticmethod
    def parser() -> ConfigParser:
        parser = ConfigParser()
        parser.optionxform = str
        return parser

    @staticmethod
    def option_value(value: str | bool | int | float) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    @staticmethod
    def print_plan(path: Path, remotes: list[WCloneToolRemote], action: WieldAction) -> None:
        print("wclone config:", flush=True)
        print(f"  action: {action.value}", flush=True)
        print(f"  path: {path}", flush=True)
        for remote in remotes:
            option_names = ["type", *remote.options.keys()]
            print(f"  remote: {remote.name} [{remote.backend}] options={option_names}", flush=True)
        print("", flush=True)


class WCloner:
    def __init__(
        self,
        spec: WCloneSpec,
        action: WieldAction,
        sync_type: WCloneSyncType | str,
        bucketeers: dict[str, Bucketeer] | None = None,
        bucketeer_conf=None,
    ):
        self.spec = spec
        self.action = action if isinstance(action, WieldAction) else WieldAction(str(action))
        self.sync_type = sync_type if isinstance(sync_type, WCloneSyncType) else WCloneSyncType(str(sync_type))
        self.bucketeers = bucketeers or {}
        self.bucketeer_conf = bucketeer_conf
        self._aws_env_cache: dict[str, str] | None = None

    @staticmethod
    def configure_wclone(configurations: list[WCloneToolConfiguration], action: WieldAction) -> None:
        WCloneToolConfigFactory.configure(configurations=configurations, action=action)

    @staticmethod
    def configure_rclone(configurations: list[WCloneToolConfiguration], action: WieldAction) -> None:
        WCloner.configure_wclone(configurations=configurations, action=action)

    @classmethod
    def show(cls, conf, **kwargs) -> None:
        cls.wield(conf, action=WieldAction.SHOW, **kwargs)

    @classmethod
    def plan(cls, conf, **kwargs) -> None:
        cls.wield(conf, action=WieldAction.PLAN, **kwargs)

    @classmethod
    def apply(cls, conf, **kwargs) -> None:
        cls.wield(conf, action=WieldAction.APPLY, **kwargs)

    @classmethod
    def delete(cls, conf, **kwargs) -> None:
        raise NotImplementedError("WCloner.delete requires an explicit deletion contract.")

    @classmethod
    def wield(
        cls,
        conf,
        action: WieldAction | str,
        *,
        bucketeer_conf=None,
    ) -> None:
        action = action if isinstance(action, WieldAction) else WieldAction(str(action))
        config = WCloneConfig.from_conf(conf)
        cls.configure_wclone(config.wclone_configs, action=action)
        if action in {WieldAction.APPLY, WieldAction.PROBE}:
            cls.inject_gcloud_access_tokens(config)
            cls.inject_microsoft_graph_access_tokens(config)
        logger.info("Running WClone jobs with action [%s]: %s", action.value, config.job_names)

        for job_name in config.job_names:
            logger.info("Running WClone job [%s].", job_name)
            cls(
                spec=config.spec_for_job(job_name),
                action=action,
                sync_type=config.sync_type,
                bucketeer_conf=bucketeer_conf,
            ).execute_sink("target")

    @classmethod
    def wield_protocol(cls, conf, action: WieldAction | str, **kwargs) -> None:
        cls.wield(conf, action=action, **kwargs)

    @classmethod
    def inject_gcloud_access_tokens(cls, config: WCloneConfig) -> None:
        remotes = [remote for remote in config.gcloud_access_token_remotes if remote.strip()]
        missing_remotes = [
            remote
            for remote in remotes
            if not os.environ.get(cls.backend_remote_env_name(remote, "access_token"))
        ]
        if not missing_remotes:
            return
        token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
        if not token:
            raise RuntimeError("gcloud auth print-access-token returned an empty token.")
        for remote in missing_remotes:
            os.environ[cls.backend_remote_env_name(remote, "access_token")] = token

    @classmethod
    def inject_microsoft_graph_access_tokens(cls, config: WCloneConfig) -> None:
        remotes = [remote for remote in config.microsoft_graph_access_token_remotes if remote.strip()]
        missing_remotes = [
            remote
            for remote in remotes
            if not os.environ.get(cls.backend_remote_env_name(remote, "token"))
        ]
        if not missing_remotes:
            return
        if not config.microsoft_graph_tenant_id:
            raise RuntimeError("microsoft_graph_tenant_id is required for Microsoft Graph token injection.")
        cls.materialize_azure_config_dir(config)
        payload = cls.azure_cli_graph_token(
            tenant_id=config.microsoft_graph_tenant_id,
            resource=config.microsoft_graph_resource,
        )
        token = cls.rclone_oauth_token(payload)
        for remote in missing_remotes:
            os.environ[cls.backend_remote_env_name(remote, "token")] = token

    @staticmethod
    def materialize_azure_config_dir(config: WCloneConfig) -> None:
        archive_env = config.microsoft_graph_azure_config_archive_env
        if not archive_env:
            return
        archive = os.environ.get(archive_env)
        if not archive:
            raise RuntimeError(f"Azure CLI config archive env var [{archive_env}] is missing.")
        azure_config_dir = tempfile.mkdtemp(prefix="wclone-azure-config-")
        WCloner.extract_base64_tar_gz(archive, Path(azure_config_dir))
        os.environ["AZURE_CONFIG_DIR"] = azure_config_dir

    @staticmethod
    def extract_base64_tar_gz(archive: str, destination: Path) -> None:
        payload = base64.b64decode(archive.encode())
        with tarfile.open(fileobj=BytesIO(payload), mode="r:gz") as tar:
            for member in tar.getmembers():
                member_path = Path(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise RuntimeError(f"Refusing unsafe Azure CLI cache archive member [{member.name}].")
                if member.isdir():
                    continue
                if not member.isfile():
                    raise RuntimeError(f"Refusing non-file Azure CLI cache archive member [{member.name}].")
                target = destination / member_path
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    raise RuntimeError(f"Could not extract Azure CLI cache archive member [{member.name}].")
                target.write_bytes(source.read())
                target.chmod(0o600)

    @staticmethod
    def azure_cli_graph_token(tenant_id: str, resource: str) -> dict:
        try:
            raw_token = subprocess.check_output(
                [
                    "az",
                    "account",
                    "get-access-token",
                    "--tenant",
                    tenant_id,
                    "--resource",
                    resource,
                ],
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("Azure CLI is required for Microsoft Graph token injection.") from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "Azure CLI failed to mint a Microsoft Graph token. "
                "Run tenant-scoped `az login --use-device-code --allow-no-subscriptions` first."
            ) from exc
        return json.loads(raw_token)

    @staticmethod
    def rclone_oauth_token(payload: dict) -> str:
        access_token = str(payload.get("accessToken") or payload.get("access_token") or "")
        if not access_token:
            raise RuntimeError("Azure CLI token payload did not include accessToken.")
        expiry = WCloner.rclone_token_expiry(payload)
        return json.dumps(
            {
                "access_token": access_token,
                "token_type": str(payload.get("tokenType") or payload.get("token_type") or "Bearer"),
                "expiry": expiry,
            },
            separators=(",", ":"),
        )

    @staticmethod
    def rclone_token_expiry(payload: dict) -> str | None:
        expires_on_epoch = payload.get("expires_on")
        if expires_on_epoch:
            return datetime.fromtimestamp(int(expires_on_epoch), tz=timezone.utc).isoformat().replace("+00:00", "Z")
        expires_on = payload.get("expiresOn")
        if not expires_on:
            return None
        clean = str(expires_on).split(".", 1)[0]
        return datetime.strptime(clean, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).isoformat().replace(
            "+00:00",
            "Z",
        )

    @staticmethod
    def backend_remote_env_name(remote: str, option: str) -> str:
        safe_remote = "".join(char.upper() if char.isalnum() else "_" for char in remote)
        safe_option = "".join(char.upper() if char.isalnum() else "_" for char in option)
        return f"RCLONE_CONFIG_{safe_remote}_{safe_option}"

    def execute_sink(self, sink_name: str) -> int:
        command = self.build_command(sink_name=sink_name)

        if command.action == WieldAction.PROBE:
            self.probe(command)
            return 0

        self.print_pair(command)
        sink = self.selected_sink(sink_name)

        if command.action in {WieldAction.PLAN, WieldAction.SHOW}:
            if command.action == WieldAction.PLAN:
                self.plan_destination(command, sink)
            if command.action == WieldAction.SHOW:
                self.print_effective_command(command, sink)
            return 0

        if command.action != WieldAction.APPLY:
            raise RuntimeError(f"Unsupported Wielder action for clone: {command.action.value}")

        if not sink.mutation_allowed:
            raise RuntimeError(f"Sink [{sink_name}] has mutation_allowed = false.")

        metadata = self.ensure_destination(command, sink)
        if metadata and sink.rbac_permissions and sink.provider == "google_drive":
            self.ensure_drive_rbac(command=command, metadata=metadata, sink=sink)
        effective_command = self.apply_sync_command(command, sink, metadata)
        self.run_checked(effective_command)
        if self.spec.verify_after_sync:
            self.verify_nonempty_sync(command, effective_command)
        return 0

    def selected_sink(self, sink_name: str) -> WCloneEndpoint:
        if sink_name not in self.spec.sinks:
            raise KeyError(f"Sink [{sink_name}] is not configured.")
        sink = self.spec.sinks[sink_name]
        if not sink.enabled:
            raise RuntimeError(f"Sink [{sink_name}] is disabled.")
        self.validate_sync_type(sink)
        return sink

    def validate_sync_type(self, sink: WCloneEndpoint) -> None:
        if self.sync_type == WCloneSyncType.PRIVATE_DRIVE_TO_DRIVE_BUCKET:
            if sink.source != "private_drive" or sink.provider != "google_drive" or not sink.shared_drive:
                raise ValueError(
                    f"Sync type [{self.sync_type.value}] requires a private_drive source and Google Shared Drive sink; "
                    f"got source=[{sink.source}], provider=[{sink.provider}], shared_drive=[{sink.shared_drive}]."
                )
            return
        if self.sync_type == WCloneSyncType.LOCAL_PATH_TO_DRIVE_BUCKET:
            if sink.source != "local_path" or sink.provider != "google_drive" or not sink.shared_drive:
                raise ValueError(
                    f"Sync type [{self.sync_type.value}] requires a local_path source and Google Shared Drive sink; "
                    f"got source=[{sink.source}], provider=[{sink.provider}], shared_drive=[{sink.shared_drive}]."
                )
            return
        if self.sync_type == WCloneSyncType.DRIVE_BUCKET_TO_OBJECT_STORE:
            if sink.source != "drive_bucket" or sink.provider not in {"s3", "gcs"}:
                raise ValueError(
                    f"Sync type [{self.sync_type.value}] requires a drive_bucket source and s3/gcs sink; "
                    f"got source=[{sink.source}], provider=[{sink.provider}]."
                )
            return
        if self.sync_type in {WCloneSyncType.WCLONE, WCloneSyncType.RCLONE}:
            return
        raise ValueError(f"Unsupported clone sync type [{self.sync_type.value}].")

    def build_command(self, sink_name: str) -> WCloneCommand:
        sink = self.selected_sink(sink_name)
        source_uri = self.private_drive_source_uri()
        sink_uri = self.endpoint_rclone_uri(sink)
        backup_uri = self.shadow_uri(sink, self.new_run_id())
        config_path = Path(self.spec.rclone_config_path).expanduser()
        command = [
            "rclone",
            self.spec.operation,
            source_uri,
            sink_uri,
            "--config",
            str(config_path),
        ]
        if self.spec.backup_enabled:
            command.extend(["--backup-dir", backup_uri])
        command.extend(self.spec.common_flags)
        return WCloneCommand(
            sink_name=sink_name,
            source_uri=source_uri,
            sink_uri=sink_uri,
            source_display_uri=self.source_display_uri_for_sink(sink, source_uri),
            sink_display_uri=sink.display_uri,
            backup_uri=backup_uri,
            config_path=config_path,
            command=command,
            action=self.action,
            sync_type=self.sync_type,
            rbac_permissions=tuple((p.role, p.type, p.email) for p in sink.rbac_permissions),
        )

    def private_drive_source_uri(self) -> str:
        source = self.spec.source
        if source.provider == "google_drive" and source.folder_id:
            return self.rclone_drive_uri(source.rclone_remote, root_folder_id=source.folder_id)
        return self.endpoint_rclone_uri(source)

    def source_display_uri_for_sink(self, sink: WCloneEndpoint, fallback: str) -> str:
        if sink.source == "private_drive":
            return self.spec.source.display_uri or fallback
        if sink.source == "local_path":
            return self.spec.source.display_uri or fallback
        if sink.source == "drive_bucket":
            return self.spec.sinks[self.spec.drive_bucket_sink].display_uri
        raise ValueError(f"Unsupported clone source [{sink.source}] for sink [{sink.name}].")

    def endpoint_rclone_uri(self, endpoint: WCloneEndpoint) -> str:
        if endpoint.rclone_uri:
            self.validate_uri(endpoint.rclone_uri)
            return endpoint.rclone_uri
        if endpoint.provider in {"s3", "gcs"}:
            return self.build_remote_uri(endpoint.rclone_remote, endpoint.bucket or "", endpoint.key or "")
        if endpoint.key:
            return self.build_remote_uri(endpoint.rclone_remote, endpoint.key)
        return f"{endpoint.rclone_remote}:"

    def effective_drive_sync_command(self, command: WCloneCommand, sink: WCloneEndpoint, metadata: dict) -> list[str]:
        drive_id = str(metadata["id"])
        sink_uri = self.google_shared_drive_prefix_uri(sink, metadata)
        backup_uri = self.rclone_drive_uri(
            sink.rclone_remote,
            self.drive_shadow_key(sink, self.new_run_id()),
            team_drive=drive_id,
        )
        effective_command = list(command.command)
        effective_command[2] = command.source_uri
        effective_command[3] = sink_uri
        if "--backup-dir" in effective_command:
            backup_index = effective_command.index("--backup-dir") + 1
            effective_command[backup_index] = backup_uri
        return effective_command

    def drive_bucket_source_metadata(self, command: WCloneCommand) -> dict:
        return self.resolve_google_shared_drive(command, self.spec.sinks[self.spec.drive_bucket_sink])

    def drive_bucket_source_uri(self, command: WCloneCommand) -> str:
        sink = self.spec.sinks[self.spec.drive_bucket_sink]
        metadata = self.drive_bucket_source_metadata(command)
        return self.rclone_drive_uri(
            sink.rclone_remote,
            team_drive=str(metadata["id"]),
            root_folder_id=str(metadata["prefix_id"]),
        )

    def effective_source_uri(self, command: WCloneCommand, sink: WCloneEndpoint) -> str:
        if self.is_google_shared_drive_endpoint(self.spec.source):
            metadata = self.resolve_google_shared_drive(command, self.spec.source, action=WieldAction.PLAN)
            return self.google_shared_drive_prefix_uri(self.spec.source, metadata)
        if sink.source in {"private_drive", "local_path"}:
            return command.source_uri
        if sink.source == "drive_bucket":
            return self.drive_bucket_source_uri(command)
        raise ValueError(f"Unsupported clone source [{sink.source}] for sink [{sink.name}].")

    def effective_sync_command(self, command: WCloneCommand, sink: WCloneEndpoint, metadata: dict) -> list[str]:
        if command.sync_type in {WCloneSyncType.PRIVATE_DRIVE_TO_DRIVE_BUCKET, WCloneSyncType.LOCAL_PATH_TO_DRIVE_BUCKET}:
            return self.effective_drive_sync_command(command, sink, metadata)
        effective_command = [*command.command, *metadata.get("destination_options", [])]
        effective_command[2] = self.effective_source_uri(command, sink)
        if self.is_google_shared_drive_endpoint(sink) and metadata:
            effective_command[3] = self.google_shared_drive_prefix_uri(sink, metadata)
        return effective_command

    def apply_sync_command(self, command: WCloneCommand, sink: WCloneEndpoint, metadata: dict) -> list[str]:
        return [*self.effective_sync_command(command, sink, metadata), *self.spec.apply_flags]

    def print_pair(self, command: WCloneCommand) -> None:
        print("", flush=True)
        print(f"src: {command.source_display_uri}", flush=True)
        print(f"dst: {command.sink_display_uri}", flush=True)
        if command.rbac_permissions:
            print("rbac:", flush=True)
            for role, permission_type, email in command.rbac_permissions:
                print(f"  {role} {permission_type}: {email}", flush=True)
        print("", flush=True)

    def print_effective_command(self, command: WCloneCommand, sink: WCloneEndpoint) -> None:
        try:
            if command.sync_type in {WCloneSyncType.PRIVATE_DRIVE_TO_DRIVE_BUCKET, WCloneSyncType.LOCAL_PATH_TO_DRIVE_BUCKET}:
                metadata = self.resolve_google_shared_drive(command, sink)
                self.print_command(command, self.effective_sync_command(command, sink, metadata))
                return
            metadata = {}
            if self.is_google_shared_drive_endpoint(sink):
                metadata = self.resolve_google_shared_drive(command, sink, action=WieldAction.PLAN)
            self.print_command(command, self.effective_sync_command(command, sink, metadata))
        except Exception:
            self.print_command(command, command.command)

    @staticmethod
    def print_command(command: WCloneCommand, effective_command: list[str]) -> None:
        display_command = list(effective_command)
        if command.sync_type == WCloneSyncType.WCLONE:
            display_command[0] = "wclone"
        print(shlex.join(display_command), flush=True)

    def ensure_destination(self, command: WCloneCommand, sink: WCloneEndpoint) -> dict:
        if self.is_google_shared_drive_endpoint(sink):
            if sink.create_destination or command.sync_type in {
                WCloneSyncType.PRIVATE_DRIVE_TO_DRIVE_BUCKET,
                WCloneSyncType.LOCAL_PATH_TO_DRIVE_BUCKET,
            }:
                return self.ensure_google_shared_drive(command, sink)
            return self.resolve_google_shared_drive(command, sink, action=WieldAction.PLAN)
        if not sink.create_destination:
            return {}
        self.ensure_bucket_destination(sink)
        return {}

    def plan_destination(self, command: WCloneCommand, sink: WCloneEndpoint) -> None:
        if self.is_google_shared_drive_endpoint(sink):
            self.plan_google_drive_destination(command, sink)
            return

        if command.sync_type == WCloneSyncType.DRIVE_BUCKET_TO_OBJECT_STORE:
            self.plan_drive_bucket_source(command, sink)

        if sink.create_destination:
            self.plan_bucket_destination(sink)

    def plan_drive_bucket_source(self, command: WCloneCommand, sink: WCloneEndpoint) -> None:
        drive_sink = self.spec.sinks[self.spec.drive_bucket_sink]
        metadata = self.drive_bucket_source_metadata(command)
        print("plan:", flush=True)
        print(f"  source shared drive exists: {drive_sink.bucket}", flush=True)
        print(f"  source key exists: {drive_sink.key}", flush=True)
        print(f"  source drive id: {metadata['id']}", flush=True)
        print(f"  source key id: {metadata['prefix_id']}", flush=True)
        print(f"  source human path: {self.google_drive_human_path(drive_sink.bucket, drive_sink.key)}", flush=True)
        print(f"  source folder url: {self.google_drive_folder_url(metadata['prefix_id'])}", flush=True)
        print("", flush=True)

    def plan_bucket_destination(self, sink: WCloneEndpoint) -> None:
        try:
            result = self.ensure_bucket(sink, action=WieldAction.PLAN)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to plan {sink.provider} destination bucket "
                f"[bucket={sink.bucket}, sink={sink.name}]: {exc}"
            ) from exc
        print("plan:", flush=True)
        if result:
            print(f"  bucket exists: {sink.bucket}", flush=True)
        else:
            print(f"  create bucket: {sink.bucket}", flush=True)
        print("", flush=True)

    def ensure_bucket_destination(self, sink: WCloneEndpoint) -> None:
        try:
            result = self.ensure_bucket(sink, action=self.action)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to ensure {sink.provider} destination bucket "
                f"[bucket={sink.bucket}, sink={sink.name}]: {exc}"
            ) from exc
        print("plan:", flush=True)
        if result.status == "exists":
            print(f"  bucket exists: {sink.bucket}", flush=True)
        elif result.status == "created":
            print(f"  created bucket: {sink.bucket}", flush=True)
        else:
            print(f"  create bucket: {sink.bucket}", flush=True)
        print("", flush=True)

    def plan_google_drive_destination(self, command: WCloneCommand, sink: WCloneEndpoint) -> None:
        try:
            bucket_result = self.ensure_bucket(sink, action=command.action)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to plan Google Shared Drive destination "
                f"[bucket={sink.bucket}, key={sink.key}, dst={command.sink_display_uri}]: {exc}"
            ) from exc
        if not bucket_result:
            print("plan:", flush=True)
            print(f"  create shared drive: {sink.bucket}", flush=True)
            print(f"  create key: {sink.key}", flush=True)
            if sink.rbac_permissions:
                print("  grant rbac after shared drive creation", flush=True)
            print("", flush=True)
            return
        try:
            prefix_id = self.ensure_prefix(sink, action=command.action)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to plan Google Drive key "
                f"[bucket={sink.bucket}, key={sink.key}, dst={command.sink_display_uri}]: {exc}"
            ) from exc
        print("plan:", flush=True)
        print(f"  shared drive exists: {sink.bucket}", flush=True)
        print(f"  key exists: {sink.key}" if prefix_id else f"  create key: {sink.key}", flush=True)
        if prefix_id:
            print(f"  human path: {self.google_drive_human_path(sink.bucket, sink.key)}", flush=True)
            print(f"  folder url: {self.google_drive_folder_url(prefix_id)}", flush=True)
        print("", flush=True)
        if sink.rbac_permissions:
            results = self.ensure_drive_rbac(command=command, metadata={"id": bucket_result.drive_id}, sink=sink)
            self.print_permission_plan(results)

    def probe(self, command: WCloneCommand) -> None:
        sink = self.selected_sink(command.sink_name)
        source_uri = self.effective_source_uri(command, sink)
        sink_uri = command.sink_uri
        if self.is_google_shared_drive_endpoint(sink):
            metadata = self.resolve_google_shared_drive(command, sink)
            sink_uri = self.google_shared_drive_prefix_uri(sink, metadata)
        self.print_pair(command)
        self.run_checked(["rclone", "lsjson", "--max-depth", "1", "--config", str(command.config_path), source_uri])
        self.run_checked(["rclone", "lsjson", "--max-depth", "1", "--config", str(command.config_path), sink_uri])

    def ensure_google_shared_drive(self, command: WCloneCommand, sink: WCloneEndpoint) -> dict:
        try:
            bucket_result = self.ensure_bucket(sink, action=command.action)
            if not bucket_result.drive_id:
                raise RuntimeError(f"Could not resolve Google Shared Drive ID for [{sink.bucket}].")
            prefix_id = self.ensure_prefix(sink, action=command.action)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to ensure Google Shared Drive destination "
                f"[bucket={sink.bucket}, key={sink.key}, dst={command.sink_display_uri}]: {exc}"
            ) from exc
        return {"id": bucket_result.drive_id, "prefix_id": prefix_id}

    def resolve_google_shared_drive(
        self,
        command: WCloneCommand,
        sink: WCloneEndpoint,
        action: WieldAction | None = None,
    ) -> dict:
        try:
            drive_id = self.bucket_id(sink)
            if not drive_id:
                raise RuntimeError(f"Google Shared Drive [{sink.bucket}] does not exist.")
            prefix_id = self.ensure_prefix(sink, action=action or command.action)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to resolve Google Shared Drive destination "
                f"[bucket={sink.bucket}, key={sink.key}, dst={command.sink_display_uri}]: {exc}"
            ) from exc
        if not prefix_id:
            raise RuntimeError(f"Google Shared Drive key [{sink.key}] does not exist in [{sink.bucket}].")
        return {"id": str(drive_id), "prefix_id": str(prefix_id)}

    def ensure_drive_rbac(self, command: WCloneCommand, metadata: dict, sink: WCloneEndpoint) -> list:
        file_id = self.destination_drive_id(metadata)
        permissions = [
            {"role": permission.role, "type": permission.type, "emailAddress": permission.email}
            for permission in sink.rbac_permissions
        ]
        try:
            return self.bucketeer_for_endpoint(sink).ensure_permissions(
                file_id=file_id,
                permissions=permissions,
                send_notification_email=False,
                action=command.action,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to ensure Google Workspace RBAC for "
                f"[dst={command.sink_display_uri}, file_id={file_id}]: {exc}"
            ) from exc

    def verify_nonempty_sync(self, command: WCloneCommand, effective_command: list[str]) -> None:
        source_uri = effective_command[2]
        sink_uri = effective_command[3]
        source_count = self.rclone_count(source_uri, command.config_path)
        print("sync:", flush=True)
        print(f"  source files: {source_count}", flush=True)
        if source_count == 0:
            print("  destination files: skipped; source is empty", flush=True)
            print("", flush=True)
            return
        sink_count = self.rclone_count(sink_uri, command.config_path)
        print(f"  destination files: {sink_count}", flush=True)
        print("", flush=True)
        if sink_count == 0:
            raise RuntimeError(f"Rclone completed but destination is empty while source has [{source_count}] files.")

    def rclone_count(self, uri: str, config_path: Path) -> int:
        raw_count = self.capture_checked(["rclone", "size", "--json", "--config", str(config_path), uri])
        return int(json.loads(raw_count).get("count", 0))

    def shadow_uri(self, sink: WCloneEndpoint, run_id: str) -> str:
        if sink.bucket and not sink.shared_drive:
            return self.build_remote_uri(
                sink.rclone_remote,
                sink.bucket,
                "_wielder",
                "raw_mirror_diff_shadow",
                sink.key or "",
                run_id,
            )
        return self.build_remote_uri(sink.rclone_remote, "_wielder", "raw_mirror_diff_shadow", sink.key or "", run_id)

    @staticmethod
    def drive_shadow_key(sink: WCloneEndpoint, run_id: str) -> str:
        clean_key = (sink.key or "").strip("/")
        parts = ["_wielder", "raw_mirror_diff_shadow"]
        if clean_key:
            parts.append(clean_key)
        parts.append(run_id)
        return "/".join(parts)

    def bucketeer_for_endpoint(self, endpoint: WCloneEndpoint) -> Bucketeer:
        for key in [endpoint.name, endpoint.provider]:
            if key in self.bucketeers:
                return self.bucketeers[key]

        bucketeer_type = BUCKETEER_TYPES_BY_PROVIDER.get(endpoint.provider)
        if bucketeer_type is None:
            raise RuntimeError(f"No Bucketeer implementation for provider [{endpoint.provider}].")
        if self.bucketeer_conf is None:
            raise RuntimeError(
                f"Bucketeer config is required to create provider [{endpoint.provider}] "
                f"bucketeer [{bucketeer_type}] for endpoint [{endpoint.name}]."
            )

        bucketeer = get_ecosystem_bucketeer(
            self.bucketeer_conf,
            bucketeer_type=bucketeer_type,
            **self.bucketeer_factory_kwargs(endpoint),
        )
        self.bucketeers[endpoint.name] = bucketeer
        return bucketeer

    def bucketeer_factory_kwargs(self, endpoint: WCloneEndpoint) -> dict:
        if endpoint.provider == "s3":
            return {
                "env_credentials": self.aws_credential_env(),
                "region": endpoint.region,
            }
        return {}

    def ensure_bucket(self, endpoint: WCloneEndpoint, action: WieldAction):
        bucketeer = self.bucketeer_for_endpoint(endpoint)
        if not hasattr(bucketeer, "ensure_bucket"):
            raise RuntimeError(f"{bucketeer.__class__.__name__} does not implement ensure_bucket().")
        return bucketeer.ensure_bucket(endpoint.bucket, region=endpoint.region, action=action)

    def bucket_id(self, endpoint: WCloneEndpoint) -> str | None:
        bucketeer = self.bucketeer_for_endpoint(endpoint)
        if not hasattr(bucketeer, "get_bucket_id"):
            raise RuntimeError(f"{bucketeer.__class__.__name__} does not implement get_bucket_id().")
        bucket_id = bucketeer.get_bucket_id(endpoint.bucket)
        return str(bucket_id) if bucket_id else None

    def ensure_prefix(self, endpoint: WCloneEndpoint, action: WieldAction) -> str | None:
        bucketeer = self.bucketeer_for_endpoint(endpoint)
        if not hasattr(bucketeer, "ensure_prefix"):
            raise RuntimeError(f"{bucketeer.__class__.__name__} does not implement ensure_prefix().")
        prefix_id = bucketeer.ensure_prefix(endpoint.bucket, endpoint.key, action=action)
        return str(prefix_id) if prefix_id else None

    @staticmethod
    def is_google_shared_drive_endpoint(endpoint: WCloneEndpoint) -> bool:
        return endpoint.provider == "google_drive" and endpoint.shared_drive

    @staticmethod
    def google_shared_drive_prefix_uri(endpoint: WCloneEndpoint, metadata: dict) -> str:
        return WCloner.rclone_drive_uri(
            endpoint.rclone_remote,
            team_drive=str(metadata["id"]),
            root_folder_id=str(metadata["prefix_id"]),
        )

    @staticmethod
    def destination_drive_id(metadata: dict) -> str:
        for key in ["ID", "id"]:
            value = metadata.get(key)
            if value:
                return str(value)
        nested_metadata = metadata.get("Metadata")
        if isinstance(nested_metadata, dict):
            for key in ["id", "ID"]:
                value = nested_metadata.get(key)
                if value:
                    return str(value)
        raise RuntimeError("Could not retrieve Google Drive destination ID from destination metadata.")

    @staticmethod
    def google_drive_folder_url(folder_id: str) -> str:
        return f"https://drive.google.com/drive/folders/{folder_id}"

    @staticmethod
    def google_drive_human_path(bucket: str | None, key: str | None) -> str:
        clean_bucket = str(bucket or "").strip("/")
        clean_key = str(key or "").strip("/")
        return f"Shared Drives/{clean_bucket}/{clean_key}" if clean_key else f"Shared Drives/{clean_bucket}"

    @staticmethod
    def print_permission_plan(results: list) -> None:
        if not results:
            return
        print("plan:", flush=True)
        for result in results:
            print(f"  rbac {result.status}: {result.role} {result.permission_type} {result.email}", flush=True)
        print("", flush=True)

    @staticmethod
    def rclone_drive_uri(remote: str, path: str = "", **options: str) -> str:
        option_parts = []
        for key, value in options.items():
            clean_value = str(value).strip()
            if not clean_value:
                continue
            if any(char in clean_value for char in [",", ":"]):
                raise ValueError(f"Refusing unsafe rclone Drive option [{key}={clean_value}].")
            option_parts.append(f"{key}={clean_value}")
        remote_with_options = ",".join([remote, *option_parts]) if option_parts else remote
        clean_path = path.strip("/")
        return f"{remote_with_options}:{clean_path}" if clean_path else f"{remote_with_options}:"

    @staticmethod
    def build_remote_uri(remote: str, *parts: str) -> str:
        clean_parts = [part.strip("/") for part in parts if part and part.strip("/")]
        for part in clean_parts:
            if "\\" in part:
                raise ValueError(f"Refusing unsafe remote path part: {part}")
        return f"{remote}:{'/'.join(clean_parts)}" if clean_parts else f"{remote}:"

    @staticmethod
    def validate_uri(uri: str) -> None:
        if not uri.strip():
            raise ValueError("rclone URI must not be empty.")
        if "\\" in uri:
            raise ValueError(f"Refusing rclone URI with backslash: {uri}")

    @staticmethod
    def new_run_id() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def subprocess_env(self, args: list[str]) -> dict[str, str]:
        env = os.environ.copy()
        aws_env = self.aws_credential_env() if self.command_uses_aws(args) else {}
        if aws_env:
            if self.spec.cloud_identities:
                for static_key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
                    env.pop(static_key, None)
            env.update(aws_env)
            env.pop("AWS_PROFILE", None)
            env.pop("AWS_DEFAULT_PROFILE", None)
        return env

    def command_uses_aws(self, args: list[str]) -> bool:
        aws_remotes = {
            endpoint.rclone_remote
            for endpoint in [self.spec.source, *self.spec.sinks.values()]
            if endpoint.provider == "s3"
        }
        return any(
            str(arg).startswith(f"{remote}:") or str(arg).startswith(f"{remote},")
            for arg in args
            for remote in aws_remotes
        )

    def aws_credential_env(self) -> dict[str, str]:
        if self._aws_env_cache is not None:
            return self._aws_env_cache
        cloud_identity = self.aws_cloud_identity()
        if cloud_identity:
            self._aws_env_cache = cloud_identity.materialize_env()
            return self._aws_env_cache
        role_name = self.spec.aws_mfa_role or self.aws_mfa_role_from_profile(os.environ.get("AWS_PROFILE"))
        if not role_name:
            self._aws_env_cache = {}
            return self._aws_env_cache
        self._aws_env_cache = require_aws_mfa_cred(role_name)
        return self._aws_env_cache

    def aws_cloud_identity(self) -> WCloudIdentity | None:
        identities = [
            identity
            for identity in self.spec.cloud_identities
            if identity.known_to_surface == WCloudSurface.AWS
        ]
        if len(identities) > 1:
            raise ValueError("WCloneSpec has more than one AWS-capable WCloudIdentity.")
        return identities[0] if identities else None

    @staticmethod
    def aws_mfa_role_from_profile(profile_name: str | None) -> str | None:
        if not profile_name:
            return None
        config_path = Path.home() / ".aws" / "config"
        if not config_path.exists():
            return None
        parser = ConfigParser()
        parser.read(config_path)
        section = f"profile {profile_name}" if profile_name != "default" else "default"
        if not parser.has_section(section) or not parser.has_option(section, "role_arn"):
            return None
        role_arn = parser.get(section, "role_arn").strip()
        return role_arn.rsplit("/", 1)[-1] if "/" in role_arn else None

    def run_checked(self, args: list[str]) -> None:
        subprocess.run(args, check=True, env=self.subprocess_env(args))

    def capture_checked(self, args: list[str]) -> str:
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, env=self.subprocess_env(args))
