"""Wielder-native model and artifact fetching contracts."""

from __future__ import annotations

import logging
import shlex
import subprocess
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wielder.util.bucketeer import Bucketeer, get_ecosystem_bucketeer
from wielder.util.wcloner import WCloneToolConfiguration, WCloner
from wielder.wield.enumerator import WieldAction


logger = logging.getLogger(__name__)

ArtifactProvider = Literal["huggingface", "ollama", "bucket", "rclone"]


def _plain_conf(value):
    if hasattr(value, "as_plain_ordered_dict"):
        return value.as_plain_ordered_dict()
    return value


class WArtifactSpec(BaseModel):
    """One fetchable model or artifact."""

    model_config = ConfigDict(extra="forbid")

    provider: ArtifactProvider
    destination: str | None = None
    enabled: bool = True
    skip_if_destination_exists: bool = True

    repo_id: str | None = None
    revision: str | None = None
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)

    model: str | None = None

    bucket: str | None = None
    key: str | None = None
    bucketeer_type: str | None = None

    rclone_remote: str | None = None
    rclone_uri: str | None = None

    @field_validator("destination", "repo_id", "revision", "model", "bucket", "key", "bucketeer_type", "rclone_remote", "rclone_uri")
    @classmethod
    def reject_backslashes(cls, value: str | None) -> str | None:
        if value is not None and "\\" in value:
            raise ValueError(f"backslash is not allowed in artifact config value [{value}]")
        return value

    @field_validator("include", "exclude")
    @classmethod
    def reject_empty_patterns(cls, values: list[str]) -> list[str]:
        if any(not str(value).strip() for value in values):
            raise ValueError("artifact include/exclude patterns must not be empty")
        return values

    @model_validator(mode="after")
    def validate_provider_contract(self):
        if self.provider == "huggingface":
            if not self.repo_id:
                raise ValueError("huggingface artifacts require repo_id")
        elif self.provider == "ollama":
            if not self.model:
                raise ValueError("ollama artifacts require model")
        elif self.provider == "bucket":
            if not self.bucket or self.key is None:
                raise ValueError("bucket artifacts require bucket and key")
        elif self.provider == "rclone":
            if not self.rclone_uri and not (self.rclone_remote and self.bucket is not None):
                raise ValueError("rclone artifacts require rclone_uri or rclone_remote plus bucket/key")
        return self

    def resolved_destination(self, name: str, cache_root: str | None) -> str | None:
        if self.destination:
            return self.destination
        if cache_root:
            return (Path(cache_root).expanduser() / name).as_posix()
        return None


class WArtifactFetchConfig(BaseModel):
    """Pydantic/HOCON contract for model and artifact fetches."""

    model_config = ConfigDict(extra="forbid")

    cache_root: str | None = None
    selected_artifacts: list[str] = Field(default_factory=list)
    common_flags: list[str] = Field(default_factory=list)
    wclone_config_path: str | None = None
    wclone_configs: list[WCloneToolConfiguration] = Field(default_factory=list)
    artifacts: dict[str, WArtifactSpec] = Field(default_factory=dict)

    @classmethod
    def from_conf(cls, conf) -> "WArtifactFetchConfig":
        return cls.model_validate(_plain_conf(conf))

    @field_validator("cache_root", "wclone_config_path")
    @classmethod
    def reject_windows_paths(cls, value: str | None) -> str | None:
        if value is not None and "\\" in value:
            raise ValueError(f"backslash is not allowed in artifact fetch path [{value}]")
        return value

    @field_validator("selected_artifacts", "common_flags")
    @classmethod
    def reject_empty_values(cls, values: list[str]) -> list[str]:
        if any(not str(value).strip() for value in values):
            raise ValueError("artifact fetch lists must not contain empty values")
        return values

    @model_validator(mode="after")
    def validate_artifacts(self):
        if not self.artifacts:
            raise ValueError("artifact fetch config requires at least one artifact")
        missing = [artifact for artifact in self.artifact_names if artifact not in self.artifacts]
        if missing:
            raise ValueError(f"Selected artifacts are not configured: {missing}")
        missing_destinations = [
            name
            for name, spec in self.artifacts.items()
            if spec.provider in {"huggingface", "bucket", "rclone"} and not spec.resolved_destination(name, self.cache_root)
        ]
        if missing_destinations:
            raise ValueError(f"Artifacts require destination or cache_root: {missing_destinations}")
        return self

    @property
    def artifact_names(self) -> list[str]:
        return self.selected_artifacts or list(self.artifacts.keys())


class WArtifactFetchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    provider: ArtifactProvider
    action: str
    status: str
    destination: str | None = None
    command: list[str] = Field(default_factory=list)


class WHuggingFaceModelClient:
    """Small command wrapper around the Hugging Face CLI."""

    @staticmethod
    def download_command(spec: WArtifactSpec, destination: str) -> list[str]:
        command = [
            "hf",
            "download",
            str(spec.repo_id),
            "--local-dir",
            destination,
        ]
        if spec.revision:
            command.extend(["--revision", spec.revision])
        for pattern in spec.include:
            command.extend(["--include", pattern])
        for pattern in spec.exclude:
            command.extend(["--exclude", pattern])
        return command


class WOllamaModelClient:
    """Small command wrapper around the Ollama CLI."""

    @staticmethod
    def pull_command(spec: WArtifactSpec) -> list[str]:
        return ["ollama", "pull", str(spec.model)]


class WArtifactFetcher:
    """Execute configured artifact fetches through provider-specific wrappers."""

    def __init__(
        self,
        conf,
        action: WieldAction | str,
        *,
        bucketeer: Bucketeer | None = None,
        bucketeer_conf=None,
    ) -> None:
        self.config = WArtifactFetchConfig.from_conf(conf)
        self.action = action if isinstance(action, WieldAction) else WieldAction(str(action))
        self.bucketeer = bucketeer
        self.bucketeer_conf = bucketeer_conf

    @classmethod
    def wield(cls, conf, action: WieldAction | str, **kwargs) -> list[WArtifactFetchResult]:
        return cls(conf=conf, action=action, **kwargs).execute()

    @classmethod
    def wield_protocol(cls, conf, action: WieldAction | str, **kwargs) -> list[WArtifactFetchResult]:
        return cls.wield(conf=conf, action=action, **kwargs)

    @classmethod
    def plan(cls, conf, **kwargs) -> list[WArtifactFetchResult]:
        return cls.wield(conf=conf, action=WieldAction.PLAN, **kwargs)

    @classmethod
    def apply(cls, conf, **kwargs) -> list[WArtifactFetchResult]:
        return cls.wield(conf=conf, action=WieldAction.APPLY, **kwargs)

    def execute(self) -> list[WArtifactFetchResult]:
        if self.config.wclone_configs:
            WCloner.configure_rclone(self.config.wclone_configs, action=self.action)

        results = []
        for name in self.config.artifact_names:
            spec = self.config.artifacts[name]
            if not spec.enabled:
                results.append(
                    WArtifactFetchResult(
                        name=name,
                        provider=spec.provider,
                        action=self.action.value,
                        status="disabled",
                        destination=spec.resolved_destination(name, self.config.cache_root),
                    )
                )
                continue
            results.append(self.execute_one(name, spec))
        return results

    def execute_one(self, name: str, spec: WArtifactSpec) -> WArtifactFetchResult:
        if spec.provider == "huggingface":
            return self.fetch_huggingface(name, spec)
        if spec.provider == "ollama":
            return self.fetch_ollama(name, spec)
        if spec.provider == "bucket":
            return self.fetch_bucket(name, spec)
        if spec.provider == "rclone":
            return self.fetch_rclone(name, spec)
        raise ValueError(f"Unsupported artifact provider [{spec.provider}]")

    def fetch_huggingface(self, name: str, spec: WArtifactSpec) -> WArtifactFetchResult:
        destination = str(spec.resolved_destination(name, self.config.cache_root))
        command = WHuggingFaceModelClient.download_command(spec, destination)
        return self.command_result(name=name, spec=spec, command=command, destination=destination)

    def fetch_ollama(self, name: str, spec: WArtifactSpec) -> WArtifactFetchResult:
        command = WOllamaModelClient.pull_command(spec)
        return self.command_result(name=name, spec=spec, command=command, destination=spec.destination)

    def fetch_bucket(self, name: str, spec: WArtifactSpec) -> WArtifactFetchResult:
        destination = str(spec.resolved_destination(name, self.config.cache_root))
        existing_result = self.existing_destination_result(name=name, spec=spec, destination=destination)
        if existing_result:
            return existing_result
        if self.action in {WieldAction.PLAN, WieldAction.SHOW}:
            print(f"bucket fetch {spec.bucket}/{spec.key} -> {destination}", flush=True)
            return WArtifactFetchResult(
                name=name,
                provider=spec.provider,
                action=self.action.value,
                status="planned",
                destination=destination,
            )
        if self.action != WieldAction.APPLY:
            return WArtifactFetchResult(
                name=name,
                provider=spec.provider,
                action=self.action.value,
                status="skipped",
                destination=destination,
            )
        bucketeer = self.selected_bucketeer(spec)
        bucketeer.download_objects_tree_by_key(str(spec.bucket), str(spec.key), destination)
        return WArtifactFetchResult(
            name=name,
            provider=spec.provider,
            action=self.action.value,
            status="fetched",
            destination=destination,
        )

    def fetch_rclone(self, name: str, spec: WArtifactSpec) -> WArtifactFetchResult:
        destination = str(spec.resolved_destination(name, self.config.cache_root))
        source_uri = spec.rclone_uri or self.rclone_uri_from_spec(spec)
        if not self.config.wclone_config_path:
            raise ValueError("rclone artifact fetches require wclone_config_path")
        command = [
            "rclone",
            "copy",
            source_uri,
            destination,
            "--config",
            self.config.wclone_config_path,
            *self.config.common_flags,
        ]
        return self.command_result(name=name, spec=spec, command=command, destination=destination)

    def selected_bucketeer(self, spec: WArtifactSpec) -> Bucketeer:
        if self.bucketeer is not None:
            return self.bucketeer
        if self.bucketeer_conf is None:
            raise ValueError("bucket artifact fetches require bucketeer or bucketeer_conf")
        return get_ecosystem_bucketeer(self.bucketeer_conf, bucketeer_type=spec.bucketeer_type)

    def command_result(
        self,
        *,
        name: str,
        spec: WArtifactSpec,
        command: list[str],
        destination: str | None,
    ) -> WArtifactFetchResult:
        existing_result = self.existing_destination_result(name=name, spec=spec, destination=destination)
        if existing_result:
            return existing_result
        if self.action in {WieldAction.PLAN, WieldAction.SHOW}:
            print(shlex.join(command), flush=True)
            return WArtifactFetchResult(
                name=name,
                provider=spec.provider,
                action=self.action.value,
                status="planned",
                destination=destination,
                command=command,
            )
        if self.action != WieldAction.APPLY:
            return WArtifactFetchResult(
                name=name,
                provider=spec.provider,
                action=self.action.value,
                status="skipped",
                destination=destination,
                command=command,
            )
        if destination:
            Path(destination).expanduser().mkdir(parents=True, exist_ok=True)
        self.run_checked(command)
        return WArtifactFetchResult(
            name=name,
            provider=spec.provider,
            action=self.action.value,
            status="fetched",
            destination=destination,
            command=command,
        )

    def existing_destination_result(
        self,
        *,
        name: str,
        spec: WArtifactSpec,
        destination: str | None,
    ) -> WArtifactFetchResult | None:
        if self.action not in {WieldAction.PLAN, WieldAction.SHOW, WieldAction.APPLY}:
            return None
        if not spec.skip_if_destination_exists or not destination:
            return None
        if not self.destination_has_payload(destination):
            return None
        print(f"artifact [{name}] already present at [{destination}]; skipping fetch.", flush=True)
        return WArtifactFetchResult(
            name=name,
            provider=spec.provider,
            action=self.action.value,
            status="exists",
            destination=destination,
        )

    @staticmethod
    def destination_has_payload(destination: str) -> bool:
        path = Path(destination).expanduser()
        if not path.exists():
            return False
        if path.is_file():
            return True
        if not path.is_dir():
            return True
        try:
            next(path.iterdir())
        except StopIteration:
            return False
        return True

    @staticmethod
    def rclone_uri_from_spec(spec: WArtifactSpec) -> str:
        key = str(spec.key or "").strip("/")
        bucket = str(spec.bucket or "").strip("/")
        path = "/".join(part for part in [bucket, key] if part)
        return f"{spec.rclone_remote}:{path}"

    @staticmethod
    def run_checked(command: list[str]) -> subprocess.CompletedProcess:
        logger.info("Running artifact fetch command: %s", shlex.join(command))
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                "artifact fetch command failed "
                f"[returncode={result.returncode}]: {shlex.join(command)}\n{result.stderr.strip()}"
            )
        return result
