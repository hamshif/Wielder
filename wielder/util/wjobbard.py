"""Wielder-native triggered job orchestration contracts."""

import json
import logging
import os
import shlex
import subprocess
import time
from abc import ABC
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from typing import Literal
from urllib.parse import quote_plus

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wielder.wield.enumerator import WieldAction


logger = logging.getLogger(__name__)


def _plain_conf(value):
    if hasattr(value, "as_plain_ordered_dict"):
        return value.as_plain_ordered_dict()
    return value


def _conf_list(value) -> list:
    if value is None:
        return []
    return list(value)


class WJobBardProvider(str, Enum):
    GCP = "gcp"
    AWS = "aws"


class WJobBardTriggerType(str, Enum):
    CRON = "cron"
    EVENT = "event"
    MANUAL = "manual"


class WJobBardTargetKind(str, Enum):
    WCLONER = "wcloner"
    CUSTOM = "custom"


class WJobBardWorkflowMode(str, Enum):
    PARALLEL = "parallel"
    ORDERED = "ordered"


class WJobBardLifecycleStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class WJobBardLocalMonitor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str | None = None
    region: str | None = None
    execution_limit: int = 5
    command_timeout_seconds: int = 60
    poll_interval_seconds: int = 30
    include_monitor_commands: bool = True
    include_command_output: bool = True
    include_recent_logs: bool = True
    recent_log_limit: int = 20
    format: str = "table(name,completionTime,state)"

    @classmethod
    def from_conf(cls, monitor_conf) -> "WJobBardLocalMonitor":
        if not monitor_conf:
            return cls()
        monitor = dict(_plain_conf(monitor_conf))
        return cls.model_validate(monitor)

    @field_validator("project_id", "region", "format")
    @classmethod
    def validate_token(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.strip():
            raise ValueError("WJobBard local monitor values must not be empty")
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in WJobBard local monitor value [{value}]")
        return value

    @field_validator("execution_limit", "command_timeout_seconds", "poll_interval_seconds", "recent_log_limit")
    @classmethod
    def validate_positive_int(cls, value: int) -> int:
        if value < 1:
            raise ValueError("WJobBard local monitor numeric values must be positive")
        return value

    def require_gcp_coordinates(self) -> tuple[str, str]:
        if not self.project_id:
            raise ValueError("WJobBard GCP local monitor requires project_id.")
        if not self.region:
            raise ValueError("WJobBard GCP local monitor requires region.")
        return self.project_id, self.region


class WJobBardGCPExecutionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    region: str
    job_name: str
    execution_name: str

    @field_validator("project_id", "region", "job_name", "execution_name")
    @classmethod
    def validate_token(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("WJobBard GCP execution view values must not be empty")
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in WJobBard GCP execution view value [{value}]")
        return value

    @property
    def execution_url(self) -> str:
        return (
            "https://console.cloud.google.com/run/jobs/executions/details/"
            f"{self.region}/{self.job_name}/{self.execution_name}?project={self.project_id}"
        )

    @property
    def logs_url(self) -> str:
        query = quote_plus(f'labels."run.googleapis.com/execution_name"="{self.execution_name}"')
        return f"https://console.cloud.google.com/logs/query;query={query}?project={self.project_id}"

    @property
    def view_urls(self) -> list[str]:
        return [self.execution_url, self.logs_url]


class WJobBardSecretEnv(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    secret: str
    version: str = "latest"

    @field_validator("name", "secret", "version")
    @classmethod
    def validate_token(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("WJobBard secret env values must not be empty")
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in WJobBard secret env value [{value}]")
        return value


class WJobBardRuntime(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    image: str
    service_account_email: str
    command: list[str] = Field(default_factory=list)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    secret_env: list[WJobBardSecretEnv] = Field(default_factory=list)
    task_count: int = 1
    parallelism: int = 1
    timeout: str = "3600s"
    max_retries: int = 0
    cpu: str = "1"
    memory: str = "512Mi"

    @classmethod
    def from_conf(cls, runtime_conf) -> "WJobBardRuntime | None":
        if not runtime_conf:
            return None
        runtime = dict(_plain_conf(runtime_conf))
        runtime["command"] = [str(value) for value in _conf_list(runtime.get("command"))]
        runtime["args"] = [str(value) for value in _conf_list(runtime.get("args"))]
        runtime["env"] = {str(key): str(value) for key, value in runtime.get("env", {}).items()}
        runtime["secret_env"] = [
            WJobBardSecretEnv.model_validate(_plain_conf(secret_env))
            for secret_env in _conf_list(runtime.get("secret_env"))
        ]
        return cls.model_validate(runtime)

    @field_validator("name", "image", "service_account_email", "timeout", "cpu", "memory")
    @classmethod
    def validate_token(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("WJobBard runtime values must not be empty")
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in WJobBard runtime value [{value}]")
        return value

    @field_validator("command", "args")
    @classmethod
    def validate_string_lists(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError("WJobBard runtime command/args entries must not be empty")
        return values

    @field_validator("env")
    @classmethod
    def validate_env(cls, values: dict[str, str]) -> dict[str, str]:
        for key, value in values.items():
            if not key.strip():
                raise ValueError("WJobBard runtime env keys must not be empty")
            if "\\" in key:
                raise ValueError(f"backslash is not allowed in WJobBard runtime env key [{key}]")
            if value is None:
                raise ValueError(f"WJobBard runtime env [{key}] must not be null")
        return values

    @field_validator("task_count", "parallelism")
    @classmethod
    def validate_positive_int(cls, value: int) -> int:
        if value < 1:
            raise ValueError("WJobBard runtime task_count and parallelism must be at least 1")
        return value

    @field_validator("max_retries")
    @classmethod
    def validate_nonnegative_int(cls, value: int) -> int:
        if value < 0:
            raise ValueError("WJobBard runtime max_retries must be nonnegative")
        return value


class WJobBardTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    trigger_type: WJobBardTriggerType
    enabled: bool = True
    schedule: str | None = None
    time_zone: str = "UTC"
    topic_ref: str | None = None
    resource_name: str | None = None
    input_event_type: str | None = None

    @field_validator("key", "schedule", "time_zone", "topic_ref", "resource_name", "input_event_type")
    @classmethod
    def validate_token(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.strip():
            raise ValueError("WJobBard trigger values must not be empty")
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in WJobBard trigger value [{value}]")
        return value

    @model_validator(mode="after")
    def validate_trigger_contract(self):
        if self.trigger_type == WJobBardTriggerType.CRON and not self.schedule:
            raise ValueError(f"cron trigger [{self.key}] requires schedule")
        if self.trigger_type == WJobBardTriggerType.EVENT and not self.topic_ref:
            raise ValueError(f"event trigger [{self.key}] requires topic_ref")
        return self


class WJobBardJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    stage_tier: str
    provider: WJobBardProvider
    kind: WJobBardTargetKind
    src: str | None = None
    sink: str | None = None
    command_ref: str | None = None
    runtime: WJobBardRuntime | None = None
    triggers: dict[str, WJobBardTrigger] = Field(default_factory=dict)
    input_event_types: list[str] = Field(default_factory=list)
    output_event_types: list[str] = Field(default_factory=list)
    lifecycle_topic_ref: str | None = None
    enabled: bool = True

    @field_validator("key", "stage_tier", "src", "sink", "command_ref", "lifecycle_topic_ref")
    @classmethod
    def validate_token(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.strip():
            raise ValueError("WJobBard job values must not be empty")
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in WJobBard job value [{value}]")
        return value

    @field_validator("input_event_types", "output_event_types")
    @classmethod
    def validate_event_types(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError("WJobBard event types must not be empty")
            if "\\" in value:
                raise ValueError(f"backslash is not allowed in WJobBard event type [{value}]")
        return values

    @model_validator(mode="after")
    def validate_job_contract(self):
        if self.kind == WJobBardTargetKind.WCLONER and (not self.src or not self.sink):
            raise ValueError(f"WJobBard wcloner job [{self.key}] requires src and sink.")
        for key, trigger in self.triggers.items():
            if trigger.key != key:
                raise ValueError(
                    f"WJobBard trigger map key [{key}] must match trigger key [{trigger.key}]"
                )
        return self

    @property
    def command_identity(self) -> str:
        return self.command_ref or self.key

    def scoped_identity(self, scope: str) -> str:
        clean_scope = scope.strip("/")
        if not clean_scope:
            return self.key
        return f"{clean_scope}/{self.key}"

    def plan_record(self, scope: str) -> dict:
        return {
            "job_id": self.scoped_identity(scope),
            **self.model_dump(mode="json"),
        }


class WJobBardWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    mode: WJobBardWorkflowMode
    job_keys: list[str] = Field(default_factory=list)
    run_job_keys: list[str] = Field(default_factory=list)

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("WJobBard workflow key must not be empty")
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in WJobBard workflow key [{value}]")
        return value

    @field_validator("job_keys", "run_job_keys")
    @classmethod
    def validate_job_keys(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError("WJobBard workflow job keys must not be empty")
        return values


class WJobBardSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: WJobBardProvider
    action: WieldAction
    scope: str
    stage_tier: str
    local_monitor: WJobBardLocalMonitor = Field(default_factory=WJobBardLocalMonitor)
    jobs: dict[str, WJobBardJob] = Field(default_factory=dict)
    workflows: dict[str, WJobBardWorkflow] = Field(default_factory=dict)
    selected_jobs: list[str] = Field(default_factory=list)
    selected_workflows: list[str] = Field(default_factory=list)

    @field_validator("scope", "stage_tier")
    @classmethod
    def validate_token(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("WJobBard spec values must not be empty")
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in WJobBard spec value [{value}]")
        return value

    @model_validator(mode="after")
    def validate_references(self):
        for key, job in self.jobs.items():
            if key != job.key:
                raise ValueError(f"WJobBard job map key [{key}] must match job key [{job.key}]")
            if job.provider != self.provider:
                raise ValueError(
                    f"WJobBard job [{key}] provider [{job.provider.value}] does not match "
                    f"spec provider [{self.provider.value}]"
                )
            if job.stage_tier != self.stage_tier:
                raise ValueError(
                    f"WJobBard job [{key}] stage_tier [{job.stage_tier}] does not match "
                    f"spec stage_tier [{self.stage_tier}]"
                )
        runtime_job_names: dict[str, str] = {}
        for key, job in self.jobs.items():
            if job.runtime is None:
                continue
            previous_key = runtime_job_names.get(job.runtime.name)
            if previous_key:
                raise ValueError(
                    f"WJobBard jobs [{previous_key}] and [{key}] share runtime name "
                    f"[{job.runtime.name}]. Runtime names define provider idempotency and must be unique."
                )
            runtime_job_names[job.runtime.name] = key
        for key, workflow in self.workflows.items():
            if key != workflow.key:
                raise ValueError(
                    f"WJobBard workflow map key [{key}] must match workflow key [{workflow.key}]"
                )
            missing_jobs = [job_key for job_key in workflow.job_keys if job_key not in self.jobs]
            if missing_jobs:
                raise ValueError(
                    f"WJobBard workflow [{key}] references unknown jobs: {missing_jobs}"
                )
            missing_run_jobs = [
                job_key for job_key in workflow.run_job_keys if job_key not in self.jobs
            ]
            if missing_run_jobs:
                raise ValueError(
                    f"WJobBard workflow [{key}] references unknown run jobs: {missing_run_jobs}"
                )
        missing_selected_jobs = [job_key for job_key in self.selected_jobs if job_key not in self.jobs]
        if missing_selected_jobs:
            raise ValueError(f"Selected WJobBard jobs are not configured: {missing_selected_jobs}")
        missing_selected_workflows = [
            workflow_key for workflow_key in self.selected_workflows if workflow_key not in self.workflows
        ]
        if missing_selected_workflows:
            raise ValueError(
                f"Selected WJobBard workflows are not configured: {missing_selected_workflows}"
            )
        return self

    @property
    def effective_job_keys(self) -> list[str]:
        if self.selected_jobs:
            return self.selected_jobs
        if self.selected_workflows:
            keys: list[str] = []
            for workflow_key in self.selected_workflows:
                for job_key in self.workflows[workflow_key].job_keys:
                    if job_key not in keys:
                        keys.append(job_key)
            return keys
        return list(self.jobs.keys())

    @property
    def effective_workflow_keys(self) -> list[str]:
        if self.selected_workflows:
            return self.selected_workflows
        return list(self.workflows.keys())

    @property
    def effective_run_groups(self) -> list[tuple[WJobBardWorkflowMode, list[str], str | None]]:
        if self.selected_jobs:
            return [(WJobBardWorkflowMode.ORDERED, self.selected_jobs, None)]
        if self.selected_workflows:
            groups = []
            seen: set[str] = set()
            for workflow_key in self.selected_workflows:
                workflow = self.workflows[workflow_key]
                job_keys = []
                for job_key in (workflow.run_job_keys or workflow.job_keys):
                    if job_key in seen:
                        continue
                    job_keys.append(job_key)
                    seen.add(job_key)
                if job_keys:
                    groups.append((workflow.mode, job_keys, workflow_key))
            return groups
        return [(WJobBardWorkflowMode.ORDERED, list(self.jobs.keys()), None)]


class WJobBardLifecycleEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "wjobbard.lifecycle.v1"
    job_id: str
    job_key: str
    scope: str
    stage_tier: str
    provider: WJobBardProvider
    surface: str | None = None
    trigger_key: str | None = None
    trigger_type: WJobBardTriggerType | None = None
    input_event_type: str | None = None
    output_event_type: str | None = None
    status: WJobBardLifecycleStatus
    attempt: int = 1
    payload_ref: str | None = None
    started_at: str | None = None
    finished_at: str | None = None

    @classmethod
    def planned_for_job(
        cls,
        job: WJobBardJob,
        scope: str,
        trigger: WJobBardTrigger | None = None,
        output_event_type: str | None = None,
    ) -> "WJobBardLifecycleEnvelope":
        return cls(
            job_id=job.scoped_identity(scope),
            job_key=job.key,
            scope=scope,
            stage_tier=job.stage_tier,
            provider=job.provider,
            trigger_key=trigger.key if trigger else None,
            trigger_type=trigger.trigger_type if trigger else None,
            input_event_type=trigger.input_event_type if trigger else None,
            output_event_type=output_event_type,
            status=WJobBardLifecycleStatus.PLANNED,
        )


class WJobBardTfvarsContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configmap: dict[str, str] = Field(default_factory=dict)

    @field_validator("configmap")
    @classmethod
    def validate_configmap(cls, values: dict[str, str]) -> dict[str, str]:
        for key, value in values.items():
            if not key.strip():
                raise ValueError("WJobBard tfvars configmap keys must not be empty")
            if "\\" in key:
                raise ValueError(f"backslash is not allowed in WJobBard configmap key [{key}]")
            if value is None:
                raise ValueError(f"WJobBard configmap [{key}] must not be null")
        return values


def wjobbard_tfvars_context(
    ecosystem: str,
    stage_tier: str,
    context_conf: str,
    security: str = "org",
    canary: str = "standard",
    destroy: str = "standard",
    action: WieldAction | str = WieldAction.APPLY,
    extra_configmap: dict[str, str] | None = None,
) -> dict:
    return WJobBardRuntimeConfigmap(
        ecosystem=str(ecosystem),
        stage_tier=str(stage_tier),
        context_conf=str(context_conf),
        security=str(security),
        canary=str(canary),
        destroy=str(destroy),
        action=action,
    ).tfvars_context(extra_configmap=extra_configmap)


def wjobbard_tfvars_context_from_conf(
    conf,
    *,
    action: WieldAction | str = WieldAction.APPLY,
    extra_configmap: dict[str, str] | None = None,
) -> dict:
    return WJobBardRuntimeConfigmap.from_conf(conf, action=action).tfvars_context(
        extra_configmap=extra_configmap
    )


class WJobBardRuntimeConfigmap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ecosystem: str
    stage_tier: str
    context_conf: str
    security: str = "org"
    canary: str = "standard"
    destroy: str = "standard"
    action: WieldAction = WieldAction.APPLY
    job_key: str | None = None
    kind: str | None = None
    src: str | None = None
    sink: str | None = None
    entrypoint_module: str | None = None

    @field_validator(
        "ecosystem",
        "stage_tier",
        "context_conf",
        "security",
        "canary",
        "destroy",
        "job_key",
        "kind",
        "src",
        "sink",
        "entrypoint_module",
    )
    @classmethod
    def validate_configmap_value(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.strip():
            raise ValueError("WJobBard runtime configmap values must not be empty")
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in WJobBard runtime configmap value [{value}]")
        return value.strip()

    @classmethod
    def from_conf(
        cls,
        conf,
        *,
        action: WieldAction | str = WieldAction.APPLY,
    ) -> "WJobBardRuntimeConfigmap":
        return cls(
            ecosystem=str(conf.ecosystem),
            stage_tier=str(conf.stage_tier),
            context_conf=str(conf.context_conf),
            security=str(conf.security),
            canary=str(conf.canary),
            destroy=str(conf.destroy),
            action=action,
        )

    @classmethod
    def from_env(
        cls,
        *,
        env: Mapping[str, str] | None = None,
        entrypoint_key: str = "WJOBBARD_ENTRYPOINT_MODULE",
        fallback_entrypoint_keys: Sequence[str] = (),
    ) -> "WJobBardRuntimeConfigmap":
        return cls.from_configmap(
            os.environ if env is None else env,
            entrypoint_key=entrypoint_key,
            fallback_entrypoint_keys=fallback_entrypoint_keys,
        )

    @classmethod
    def from_configmap(
        cls,
        configmap: Mapping[str, str],
        *,
        entrypoint_key: str = "WJOBBARD_ENTRYPOINT_MODULE",
        fallback_entrypoint_keys: Sequence[str] = (),
    ) -> "WJobBardRuntimeConfigmap":
        def required(key: str) -> str:
            value = str(configmap.get(key, "")).strip()
            if not value:
                raise ValueError(f"{key} must be present in the WJobBard runtime configmap.")
            return value

        def optional(key: str) -> str | None:
            value = str(configmap.get(key, "")).strip()
            return value or None

        entrypoint_module = optional(entrypoint_key)
        for fallback_key in fallback_entrypoint_keys:
            if entrypoint_module:
                break
            entrypoint_module = optional(fallback_key)

        return cls(
            ecosystem=required("ECOSYSTEM"),
            stage_tier=required("STAGE_TIER"),
            context_conf=required("CONTEXT_CONF"),
            security=optional("SECURITY") or "org",
            canary=optional("CANARY") or "standard",
            destroy=optional("DESTROY") or "standard",
            action=optional("WIELDER_ACTION") or WieldAction.APPLY.value,
            job_key=optional("WJOBBARD_JOB_KEY"),
            kind=optional("WJOBBARD_KIND"),
            src=optional("WJOBBARD_SRC"),
            sink=optional("WJOBBARD_SINK"),
            entrypoint_module=entrypoint_module,
        )

    def to_configmap(self, extra_configmap: dict[str, str] | None = None) -> dict[str, str]:
        configmap = {
            "ECOSYSTEM": self.ecosystem,
            "STAGE_TIER": self.stage_tier,
            "CONTEXT_CONF": self.context_conf,
            "SECURITY": self.security,
            "CANARY": self.canary,
            "DESTROY": self.destroy,
            "WIELDER_ACTION": self.action.value,
        }
        if self.job_key:
            configmap["WJOBBARD_JOB_KEY"] = self.job_key
        if self.kind:
            configmap["WJOBBARD_KIND"] = self.kind
        if self.src:
            configmap["WJOBBARD_SRC"] = self.src
        if self.sink:
            configmap["WJOBBARD_SINK"] = self.sink
        if self.entrypoint_module:
            configmap["WJOBBARD_ENTRYPOINT_MODULE"] = self.entrypoint_module
        if extra_configmap:
            configmap.update({str(key): value for key, value in extra_configmap.items()})
        return configmap

    def tfvars_context(self, extra_configmap: dict[str, str] | None = None) -> dict:
        return WJobBardTfvarsContext.model_validate(
            {"configmap": self.to_configmap(extra_configmap=extra_configmap)}
        ).model_dump(mode="json")

    def require_entrypoint_module(
        self,
        *,
        allowed_prefixes: Sequence[str] = (),
    ) -> str:
        if not self.entrypoint_module:
            raise ValueError("WJOBBARD_ENTRYPOINT_MODULE must name the payload module to run.")
        if allowed_prefixes and not any(
            self.entrypoint_module.startswith(prefix) for prefix in allowed_prefixes
        ):
            prefixes = ", ".join(allowed_prefixes)
            raise ValueError(
                f"WJOBBARD_ENTRYPOINT_MODULE [{self.entrypoint_module}] must start with one of: {prefixes}."
            )
        return self.entrypoint_module


class WJobBardGCPTerraformJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    image: str
    service_account_email: str
    command: list[str] = Field(default_factory=list)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    secret_env: list[WJobBardSecretEnv] = Field(default_factory=list)
    task_count: int = 1
    parallelism: int = 1
    timeout: str = "3600s"
    max_retries: int = 0
    cpu: str = "1"
    memory: str = "512Mi"
    kind: str
    src: str
    sink: str
    input_event_types: list[str] = Field(default_factory=list)
    output_event_types: list[str] = Field(default_factory=list)
    lifecycle_topic_ref: str = ""


class WJobBardGCPTerraformCronTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_key: str
    job_name: str
    name: str
    trigger_key: str
    input_event_type: str = ""
    invoker_service_account_email: str
    schedule: str
    time_zone: str = "UTC"


class WJobBardGCPTerraformEventTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_key: str
    job_name: str
    name: str
    trigger_key: str
    input_event_type: str = ""
    invoker_service_account_email: str
    topic_name: str
    workflow_name: str


class WJobBardGCPTerraformTfvars(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobs: dict[str, WJobBardGCPTerraformJob] = Field(default_factory=dict)
    cron_triggers: dict[str, WJobBardGCPTerraformCronTrigger] = Field(default_factory=dict)
    event_triggers: dict[str, WJobBardGCPTerraformEventTrigger] = Field(default_factory=dict)


class WJobBard(ABC):
    provider: WJobBardProvider

    def __init__(self, spec: WJobBardSpec):
        self.spec = spec

    @classmethod
    def from_spec(cls, spec: WJobBardSpec) -> "WJobBard":
        match spec.provider:
            case WJobBardProvider.GCP:
                return GCPJobBard(spec)
            case WJobBardProvider.AWS:
                return AWSJobBard(spec)
            case _:
                raise ValueError(f"Unsupported WJobBard provider [{spec.provider}]")

    @classmethod
    def from_provider(
        cls,
        provider: WJobBardProvider | Literal["gcp", "aws"],
        action: WieldAction,
        **kwargs,
    ) -> "WJobBard":
        return cls.from_spec(
            WJobBardSpec(provider=WJobBardProvider(provider), action=action, **kwargs)
        )

    def show(self) -> dict:
        return self.plan()

    def plan(self) -> dict:
        return {
            "provider": self.spec.provider.value,
            "stage_tier": self.spec.stage_tier,
            "scope": self.spec.scope,
            "local_monitor": self.spec.local_monitor.model_dump(mode="json"),
            "jobs": {
                job_key: self.spec.jobs[job_key].plan_record(self.spec.scope)
                for job_key in self.spec.effective_job_keys
            },
            "workflows": [
                {
                    "key": workflow.key,
                    "mode": workflow.mode.value,
                    "job_keys": workflow.job_keys,
                    "run_job_keys": workflow.run_job_keys,
                }
                for workflow_key in self.spec.effective_workflow_keys
                for workflow in [self.spec.workflows[workflow_key]]
            ],
            "lifecycle_envelopes": [
                WJobBardLifecycleEnvelope.planned_for_job(
                    self.spec.jobs[job_key],
                    self.spec.scope,
                ).model_dump(mode="json")
                for job_key in self.spec.effective_job_keys
            ],
        }

    def apply(self):
        raise NotImplementedError(f"{self.__class__.__name__}.apply is not implemented yet.")

    def local_monitor(self, *, execute: bool = False) -> list[dict]:
        raise NotImplementedError(
            f"{self.__class__.__name__}.local_monitor is not implemented yet."
        )

    def job_execution_after(self, job_key: str, *, started_at: datetime, slack_seconds: int = 10) -> dict | None:
        raise NotImplementedError(
            f"{self.__class__.__name__}.job_execution_after is not implemented yet."
        )

    def job_execution_log_evidence_after(
        self,
        job_key: str,
        *,
        started_at: datetime,
        required_texts: Sequence[str],
        evidence_markers: Sequence[str],
        slack_seconds: int = 10,
    ) -> dict | None:
        raise NotImplementedError(
            f"{self.__class__.__name__}.job_execution_log_evidence_after is not implemented yet."
        )

    def run(self, *, execute: bool = False, wait: bool = False) -> list[dict]:
        raise NotImplementedError(
            f"{self.__class__.__name__}.run is not implemented yet."
        )

    def tfvars_plan(self, context: dict) -> dict:
        raise NotImplementedError(
            f"{self.__class__.__name__}.tfvars_plan is not implemented yet."
        )

    def print_plan(self) -> dict:
        plan = self.plan()
        print(json.dumps(plan, indent=2, sort_keys=True), flush=True)
        return plan


class GCPJobBard(WJobBard):
    provider = WJobBardProvider.GCP

    def apply(self):
        raise NotImplementedError("GCPJobBard.apply is reserved for the Cloud Run/Scheduler milestone.")

    def terraform_targets(self) -> list[str]:
        targets: list[str] = []
        for job_key in self.spec.effective_job_keys:
            job = self.spec.jobs[job_key]
            if job.runtime is None:
                raise ValueError(f"GCP WJobBard Terraform targets for job [{job_key}] require runtime.")

            service_account_member = f"serviceAccount:{job.runtime.service_account_email}"
            targets.extend(
                [
                    f'google_cloud_run_v2_job.managed["{job_key}"]',
                    f'google_cloud_run_v2_job_iam_member.run_invokers["{job_key}--{service_account_member}"]',
                ]
            )
            for trigger_key, trigger in job.triggers.items():
                if not trigger.enabled:
                    continue
                materialized_key = f"{job_key}--{trigger_key}"
                if trigger.trigger_type == WJobBardTriggerType.CRON:
                    targets.append(f'google_cloud_scheduler_job.cron["{materialized_key}"]')
                elif trigger.trigger_type == WJobBardTriggerType.EVENT:
                    targets.extend(
                        [
                            f'google_workflows_workflow.event_dispatcher["{materialized_key}"]',
                            f'google_eventarc_trigger.event["{materialized_key}"]',
                            f'google_project_iam_member.eventarc_event_receiver["{service_account_member}"]',
                            f'google_project_iam_member.workflow_invoker["{service_account_member}"]',
                        ]
                    )

        return list(dict.fromkeys(targets))

    @staticmethod
    def _runtime_timeout_seconds(timeout: str) -> int:
        clean_timeout = timeout.strip()
        if clean_timeout.endswith("s"):
            return int(clean_timeout[:-1])
        if clean_timeout.endswith("m"):
            return int(clean_timeout[:-1]) * 60
        if clean_timeout.endswith("h"):
            return int(clean_timeout[:-1]) * 3600
        return int(clean_timeout)

    @staticmethod
    def _run_monitor_command(
        command: list[str],
        timeout: int,
        label: str,
        *,
        include_command: bool = True,
        include_output: bool = True,
    ) -> dict:
        if include_command:
            logger.info("WJobBard local monitor command: %s", shlex.join(command))
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            logger.warning("WJobBard local monitor command [%s] timed out after [%s] seconds.", label, timeout)
            return {
                "command": command,
                "returncode": None,
                "stdout": stdout,
                "stderr": stderr,
                "timed_out": True,
            }
        record = {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        if include_output and completed.stdout.strip():
            logger.info("WJobBard local monitor %s:\n%s", label, completed.stdout)
        if include_output and completed.stderr.strip():
            logger.warning("WJobBard local monitor %s stderr:\n%s", label, completed.stderr)
        if completed.returncode != 0:
            logger.warning(
                "WJobBard local monitor command [%s] exited with code [%s].",
                label,
                completed.returncode,
            )
            if not include_output and completed.stderr.strip():
                logger.warning("WJobBard local monitor %s stderr:\n%s", label, completed.stderr)
        return record

    @staticmethod
    def _parse_execution_name(stdout: str) -> str | None:
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        if not lines:
            return None
        return lines[-1].split("/")[-1]

    @staticmethod
    def _parse_cloud_run_time(value) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None

    @staticmethod
    def _nested_value(record: dict, *path: str):
        value = record
        for part in path:
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value

    @classmethod
    def _cloud_run_execution_time(cls, record: dict) -> datetime | None:
        for path in (
            ("metadata", "creationTimestamp"),
            ("createTime",),
            ("startTime",),
            ("status", "startTime"),
            ("status", "completionTime"),
            ("completionTime",),
        ):
            parsed = cls._parse_cloud_run_time(cls._nested_value(record, *path))
            if parsed is not None:
                return parsed
        return None

    @classmethod
    def _cloud_run_execution_name(cls, record: dict) -> str | None:
        for path in (("metadata", "name"), ("name",)):
            value = cls._nested_value(record, *path)
            if value:
                return str(value).split("/")[-1]
        return None

    def _latest_execution_name(
        self,
        job_name: str,
        *,
        project_id: str,
        region: str,
        monitor: WJobBardLocalMonitor,
    ) -> str | None:
        latest_command = [
            "gcloud",
            "run",
            "jobs",
            "executions",
            "list",
            f"--job={job_name}",
            f"--region={region}",
            f"--project={project_id}",
            "--limit=1",
            "--format=value(name)",
        ]
        latest = self._run_monitor_command(
            latest_command,
            timeout=monitor.command_timeout_seconds,
            label=f"latest execution for [{job_name}]",
            include_command=monitor.include_monitor_commands,
            include_output=monitor.include_command_output,
        )
        return self._parse_execution_name(latest["stdout"])

    def _listed_execution_names(
        self,
        job_name: str,
        *,
        project_id: str,
        region: str,
        monitor: WJobBardLocalMonitor,
        limit: int | None = None,
    ) -> list[str]:
        list_command = [
            "gcloud",
            "run",
            "jobs",
            "executions",
            "list",
            f"--job={job_name}",
            f"--region={region}",
            f"--project={project_id}",
            f"--limit={limit or monitor.execution_limit}",
            "--format=value(name)",
        ]
        listed = self._run_monitor_command(
            list_command,
            timeout=monitor.command_timeout_seconds,
            label=f"executions for [{job_name}]",
            include_command=monitor.include_monitor_commands,
            include_output=monitor.include_command_output,
        )
        return [
            execution_name
            for execution_name in (
                self._parse_execution_name(line)
                for line in str(listed["stdout"]).splitlines()
            )
            if execution_name
        ]

    def _wait_for_started_execution_name(
        self,
        job_name: str,
        *,
        project_id: str,
        region: str,
        monitor: WJobBardLocalMonitor,
        previous_execution_name: str | None = None,
    ) -> str | None:
        # Cloud Run `jobs execute --async` returns before the execution resource is
        # always visible. Poll only until the new execution identity exists so
        # monitor/log commands can attach to the right run.
        deadline = time.monotonic() + monitor.command_timeout_seconds
        while True:
            execution_name = self._latest_execution_name(
                job_name,
                project_id=project_id,
                region=region,
                monitor=monitor,
            )
            if execution_name and execution_name != previous_execution_name:
                return execution_name
            if time.monotonic() >= deadline:
                return None
            time.sleep(min(monitor.poll_interval_seconds, 5))

    def _describe_execution_status(
        self,
        execution_name: str,
        *,
        job_key: str,
        project_id: str,
        region: str,
        monitor: WJobBardLocalMonitor,
    ) -> dict:
        describe_command = [
            "gcloud",
            "run",
            "jobs",
            "executions",
            "describe",
            execution_name,
            f"--region={region}",
            f"--project={project_id}",
            "--format=json(status.conditions,status.completionTime,status.succeededCount,status.failedCount,status.runningCount,status.logUri)",
        ]
        return self._run_monitor_command(
            describe_command,
            timeout=monitor.command_timeout_seconds,
            label=f"execution status for [{job_key}]",
            include_command=monitor.include_monitor_commands,
            include_output=monitor.include_command_output,
        )

    def _execution_status_snapshot(
        self,
        execution_name: str,
        *,
        job_key: str,
        project_id: str,
        region: str,
        monitor: WJobBardLocalMonitor,
    ) -> dict:
        execution_status = self._describe_execution_status(
            execution_name,
            job_key=job_key,
            project_id=project_id,
            region=region,
            monitor=monitor,
        )
        task_command = [
            "gcloud",
            "run",
            "jobs",
            "executions",
            "tasks",
            "list",
            f"--execution={execution_name}",
            f"--region={region}",
            f"--project={project_id}",
            "--format=table(index,name,runningState,lastAttemptResult.exitCode,lastAttemptResult.status.message)",
        ]
        tasks = self._run_monitor_command(
            task_command,
            timeout=monitor.command_timeout_seconds,
            label=f"task status for [{job_key}]",
            include_command=monitor.include_monitor_commands,
            include_output=monitor.include_command_output,
        )
        logs_command = [
            "gcloud",
            "logging",
            "read",
            f'labels."run.googleapis.com/execution_name"="{execution_name}"',
            f"--project={project_id}",
            f"--limit={monitor.recent_log_limit}",
            "--format=table(timestamp,severity,textPayload,jsonPayload.message)",
        ]
        snapshot = {
            "execution_status": execution_status,
            "tasks": tasks,
        }
        if monitor.include_recent_logs:
            snapshot["logs"] = self._run_monitor_command(
                logs_command,
                timeout=monitor.command_timeout_seconds,
                label=f"recent logs for [{job_key}]",
                include_command=monitor.include_monitor_commands,
                include_output=monitor.include_command_output,
            )
        return snapshot

    def _execution_logs_json(
        self,
        execution_name: str,
        *,
        project_id: str,
        monitor: WJobBardLocalMonitor,
    ) -> dict:
        logs_command = [
            "gcloud",
            "logging",
            "read",
            f'labels."run.googleapis.com/execution_name"="{execution_name}"',
            f"--project={project_id}",
            "--limit=200",
            "--format=json",
        ]
        return self._run_monitor_command(
            logs_command,
            timeout=monitor.command_timeout_seconds,
            label=f"logs for [{execution_name}]",
            include_command=monitor.include_monitor_commands,
            include_output=monitor.include_command_output,
        )

    @staticmethod
    def _execution_status_payload(execution_status: dict) -> dict | None:
        if execution_status.get("returncode") != 0:
            return None
        stdout = str(execution_status.get("stdout", "")).strip()
        if not stdout:
            return None
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return None

    @classmethod
    def _terminal_execution_state(cls, execution_status: dict) -> str | None:
        payload = cls._execution_status_payload(execution_status)
        if payload is None:
            return None
        for condition in payload.get("status", {}).get("conditions", []):
            if condition.get("type") != "Completed":
                continue
            if condition.get("status") == "True":
                return "succeeded"
            if condition.get("status") == "False":
                return "failed"
        return None

    @classmethod
    def _execution_state_label(cls, execution_status: dict) -> str:
        terminal_state = cls._terminal_execution_state(execution_status)
        if terminal_state:
            return terminal_state
        payload = cls._execution_status_payload(execution_status)
        if payload is None:
            return "status unavailable"
        status = payload.get("status", {})
        if int(status.get("runningCount") or 0) > 0:
            return "running"
        for condition in status.get("conditions", []):
            if condition.get("type") == "Completed" and condition.get("status") == "Unknown":
                reason = str(condition.get("reason") or "").strip()
                return f"pending ({reason})" if reason else "pending"
        return "pending"

    @staticmethod
    def _log_operator_monitor_mode(monitor: WJobBardLocalMonitor) -> None:
        if monitor.include_monitor_commands or monitor.include_command_output or monitor.include_recent_logs:
            return
        logger.info(
            "WJobBard operator monitor is in quiet mode: command output is retained in records, "
            "but only lifecycle status changes are printed."
        )

    @classmethod
    def _execution_is_alive(cls, execution_status: dict) -> bool:
        payload = cls._execution_status_payload(execution_status)
        if payload is None:
            return True
        if cls._terminal_execution_state(execution_status) is not None:
            return False
        status = payload.get("status", {})
        if int(status.get("runningCount") or 0) > 0:
            return True
        for condition in status.get("conditions", []):
            if condition.get("type") == "Completed" and condition.get("status") == "Unknown":
                return True
        return True

    def _latest_alive_execution_name(
        self,
        job_name: str,
        *,
        job_key: str,
        project_id: str,
        region: str,
        monitor: WJobBardLocalMonitor,
    ) -> str | None:
        alive = self._alive_execution_names(
            job_name,
            job_key=job_key,
            project_id=project_id,
            region=region,
            monitor=monitor,
        )
        return alive[0] if alive else None

    def _alive_execution_names(
        self,
        job_name: str,
        *,
        job_key: str,
        project_id: str,
        region: str,
        monitor: WJobBardLocalMonitor,
    ) -> list[str]:
        alive = []
        for execution_name in self._listed_execution_names(
            job_name,
            project_id=project_id,
            region=region,
            monitor=monitor,
            limit=max(monitor.execution_limit, 50),
        ):
            execution_status = self._describe_execution_status(
                execution_name,
                job_key=job_key,
                project_id=project_id,
                region=region,
                monitor=monitor,
            )
            if self._execution_is_alive(execution_status):
                alive.append(execution_name)
        return alive

    def monitor_execution_until_terminal(
        self,
        job_key: str,
        execution_name: str,
        *,
        timeout_seconds: int,
    ) -> dict:
        monitor = self.spec.local_monitor
        project_id, region = monitor.require_gcp_coordinates()
        deadline = time.monotonic() + timeout_seconds
        latest_snapshot = {}
        last_state_label = None
        logger.info(
            "WJobBard monitoring execution [%s] for job [%s]. Ctrl-C stops local monitoring only.",
            execution_name,
            job_key,
        )
        self._log_operator_monitor_mode(monitor)
        logger.info(
            "WJobBard waiting for Cloud Run execution status; polling every [%s] seconds.",
            monitor.poll_interval_seconds,
        )
        while True:
            latest_snapshot = self._execution_status_snapshot(
                execution_name,
                job_key=job_key,
                project_id=project_id,
                region=region,
                monitor=monitor,
            )
            state_label = self._execution_state_label(latest_snapshot["execution_status"])
            if state_label != last_state_label:
                logger.info(
                    "WJobBard execution [%s] for job [%s] is [%s].",
                    execution_name,
                    job_key,
                    state_label,
                )
                last_state_label = state_label
            terminal_state = self._terminal_execution_state(latest_snapshot["execution_status"])
            if terminal_state == "succeeded":
                logger.info("WJobBard execution [%s] for job [%s] succeeded.", execution_name, job_key)
                return latest_snapshot
            if terminal_state == "failed":
                raise RuntimeError(f"WJobBard execution [{execution_name}] for job [{job_key}] failed.")
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"WJobBard execution [{execution_name}] for job [{job_key}] did not finish "
                    f"within [{timeout_seconds}] seconds."
                )
            time.sleep(monitor.poll_interval_seconds)

    @staticmethod
    def _execution_env_arg(execution_env: dict[str, str] | None) -> str | None:
        if not execution_env:
            return None
        delimiter = "|||"
        parts = []
        for key, value in execution_env.items():
            clean_key = str(key).strip()
            clean_value = str(value)
            if not clean_key:
                raise ValueError("WJobBard execution env keys must not be empty.")
            if "=" in clean_key or "," in clean_key or delimiter in clean_key or delimiter in clean_value:
                raise ValueError(f"WJobBard execution env contains unsafe token [{clean_key}].")
            parts.append(f"{clean_key}={clean_value}")
        return f"--update-env-vars=^{delimiter}^" + delimiter.join(parts)

    def _run_one_job(
        self,
        job_key: str,
        *,
        execute: bool,
        wait: bool,
        project_id: str,
        region: str,
        execution_env: dict[str, str] | None = None,
    ) -> dict:
        monitor = self.spec.local_monitor
        job = self.spec.jobs[job_key]
        if job.runtime is None:
            raise ValueError(f"GCP WJobBard run job [{job_key}] requires runtime.")

        command = [
            "gcloud",
            "run",
            "jobs",
            "execute",
            job.runtime.name,
            f"--region={region}",
            f"--project={project_id}",
            "--async",
            "--format=value(metadata.name)",
        ]
        execution_env_arg = self._execution_env_arg(execution_env)
        if execution_env_arg:
            command.append(execution_env_arg)
        record = {
            "job_key": job_key,
            "job_name": job.runtime.name,
            "project_id": project_id,
            "region": region,
            "command": command,
        }
        if execution_env:
            record["execution_env_keys"] = sorted(execution_env)
        logger.info("WJobBard run command: %s", shlex.join(command))

        if not execute:
            return record

        logger.info("WJobBard checking for an existing live execution of job [%s].", job_key)
        alive_execution_names = self._alive_execution_names(
            job.runtime.name,
            job_key=job_key,
            project_id=project_id,
            region=region,
            monitor=monitor,
        )
        if len(alive_execution_names) > 1:
            record["live_executions"] = alive_execution_names
            record["skipped_start"] = True
            raise RuntimeError(
                f"WJobBard job [{job_key}] already has multiple live executions; "
                f"not starting another run. Live executions: {alive_execution_names}"
            )
        if alive_execution_names:
            alive_execution_name = alive_execution_names[0]
            record["execution_name"] = alive_execution_name
            record["existing_execution"] = True
            record["skipped_start"] = True
            logger.info(
                "WJobBard job [%s] already has live execution [%s]; not starting another run.",
                job_key,
                alive_execution_name,
            )
            if wait:
                record["status_records"] = self.monitor_execution_until_terminal(
                    job_key,
                    alive_execution_name,
                    timeout_seconds=self._runtime_timeout_seconds(job.runtime.timeout) + 300,
                )
            else:
                logger.info(
                    "WJobBard live execution [%s] for job [%s] left running.",
                    alive_execution_name,
                    job_key,
                )
            return record

        previous_execution_name = self._latest_execution_name(
            job.runtime.name,
            project_id=project_id,
            region=region,
            monitor=monitor,
        )
        logger.info("WJobBard starting Cloud Run job [%s].", job_key)
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=monitor.command_timeout_seconds,
        )
        record["returncode"] = completed.returncode
        record["stdout"] = completed.stdout
        record["stderr"] = completed.stderr
        execution_name = None
        if completed.returncode == 0:
            execution_name = self._wait_for_started_execution_name(
                job.runtime.name,
                project_id=project_id,
                region=region,
                monitor=monitor,
                previous_execution_name=previous_execution_name,
            )
            if execution_name:
                logger.info("WJobBard Cloud Run job [%s] started execution [%s].", job_key, execution_name)
        record["execution_name"] = execution_name
        if completed.stdout.strip():
            logger.info("WJobBard run output for [%s]:\n%s", job_key, completed.stdout)
        if completed.stderr.strip():
            logger.warning("WJobBard run stderr for [%s]:\n%s", job_key, completed.stderr)
        if completed.returncode != 0:
            raise RuntimeError(
                f"WJobBard run failed for job [{job_key}] with exit code "
                f"[{completed.returncode}]."
            )
        if wait:
            if not execution_name:
                raise RuntimeError(f"WJobBard could not determine execution name for job [{job_key}].")
            record["status_records"] = self.monitor_execution_until_terminal(
                job_key,
                execution_name,
                timeout_seconds=self._runtime_timeout_seconds(job.runtime.timeout) + 300,
            )

        return record

    def _run_parallel_group(
        self,
        job_keys: list[str],
        *,
        execute: bool,
        wait: bool,
        project_id: str,
        region: str,
        execution_env: dict[str, str] | None = None,
    ) -> list[dict]:
        records_by_key = {}
        with ThreadPoolExecutor(max_workers=len(job_keys)) as executor:
            futures = {
                executor.submit(
                    self._run_one_job,
                    job_key,
                    execute=execute,
                    wait=wait,
                    project_id=project_id,
                    region=region,
                    execution_env=execution_env,
                ): job_key
                for job_key in job_keys
            }
            for future in as_completed(futures):
                job_key = futures[future]
                records_by_key[job_key] = future.result()
        return [records_by_key[job_key] for job_key in job_keys]

    def run(
        self,
        *,
        execute: bool = False,
        wait: bool = False,
        execution_env: dict[str, str] | None = None,
    ) -> list[dict]:
        monitor = self.spec.local_monitor
        project_id, region = monitor.require_gcp_coordinates()
        records = []
        for workflow_mode, job_keys, workflow_key in self.spec.effective_run_groups:
            if workflow_key:
                logger.info(
                    "WJobBard running workflow [%s] in [%s] mode with jobs: %s",
                    workflow_key,
                    workflow_mode.value,
                    job_keys,
                )
            if workflow_mode == WJobBardWorkflowMode.PARALLEL and len(job_keys) > 1:
                records.extend(
                    self._run_parallel_group(
                        job_keys,
                        execute=execute,
                        wait=wait,
                        project_id=project_id,
                        region=region,
                        execution_env=execution_env,
                    )
                )
                continue

            for job_key in job_keys:
                records.append(
                    self._run_one_job(
                        job_key,
                        execute=execute,
                        wait=wait,
                        project_id=project_id,
                        region=region,
                        execution_env=execution_env,
                    )
                )

        return records

    def local_monitor(self, *, execute: bool = False) -> list[dict]:
        monitor = self.spec.local_monitor
        project_id, region = monitor.require_gcp_coordinates()
        records = []
        for job_key in self.spec.effective_job_keys:
            job = self.spec.jobs[job_key]
            if job.runtime is None:
                raise ValueError(f"GCP WJobBard local monitor job [{job_key}] requires runtime.")

            command = [
                "gcloud",
                "run",
                "jobs",
                "executions",
                "list",
                f"--job={job.runtime.name}",
                f"--region={region}",
                f"--project={project_id}",
                f"--limit={monitor.execution_limit}",
                f"--format={monitor.format}",
            ]
            record = {
                "job_key": job_key,
                "job_name": job.runtime.name,
                "project_id": project_id,
                "region": region,
                "command": command,
            }
            records.append(record)
            if not execute:
                logger.info("WJobBard local monitor command: %s", shlex.join(command))

            if execute:
                status_records = {
                    "executions": self._run_monitor_command(
                        command,
                        timeout=monitor.command_timeout_seconds,
                        label=f"executions for [{job_key}]",
                    )
                }
                record.update(status_records["executions"])

                execution_name = self._latest_execution_name(
                    job.runtime.name,
                    project_id=project_id,
                    region=region,
                    monitor=monitor,
                )
                if execution_name:
                    record["latest_execution_name"] = execution_name
                    status_records.update(
                        self._execution_status_snapshot(
                            execution_name,
                            job_key=job_key,
                            project_id=project_id,
                            region=region,
                            monitor=monitor,
                        )
                    )
                else:
                    logger.warning("WJobBard local monitor found no executions for job [%s].", job_key)
                record["status_records"] = status_records

        return records

    def job_execution_after(self, job_key: str, *, started_at: datetime, slack_seconds: int = 10) -> dict | None:
        monitor = self.spec.local_monitor
        project_id, region = monitor.require_gcp_coordinates()
        job = self.spec.jobs[str(job_key)]
        if job.runtime is None:
            raise ValueError(f"GCP WJobBard local monitor job [{job_key}] requires runtime.")
        command = [
            "gcloud",
            "run",
            "jobs",
            "executions",
            "list",
            f"--job={job.runtime.name}",
            f"--region={region}",
            f"--project={project_id}",
            f"--limit={monitor.execution_limit}",
            "--format=json",
        ]
        result = self._run_monitor_command(
            command,
            timeout=monitor.command_timeout_seconds,
            label=f"executions for [{job_key}]",
        )
        if result.get("returncode") != 0:
            raise RuntimeError(f"Cloud Run execution monitor failed: {str(result.get('stderr') or '').strip()}")
        executions = json.loads(result["stdout"]) if str(result.get("stdout") or "").strip() else []
        threshold = started_at.astimezone(UTC) - timedelta(seconds=slack_seconds)
        recent_executions = [
            execution
            for execution in executions
            if (self._cloud_run_execution_time(execution) or datetime.min.replace(tzinfo=UTC)) >= threshold
        ]
        if not recent_executions:
            return None
        return {
            "job_key": str(job_key),
            "job_name": job.runtime.name,
            "project_id": project_id,
            "region": region,
            "started_at": started_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "command": command,
            "executions": recent_executions,
        }

    def cloud_run_execution_view(self, job_key: str, execution_name: str) -> WJobBardGCPExecutionView:
        project_id, region = self.spec.local_monitor.require_gcp_coordinates()
        job = self.spec.jobs[str(job_key)]
        if job.runtime is None:
            raise ValueError(f"GCP WJobBard execution view job [{job_key}] requires runtime.")
        return WJobBardGCPExecutionView(
            project_id=project_id,
            region=region,
            job_name=job.runtime.name,
            execution_name=execution_name,
        )

    def job_execution_log_evidence_after(
        self,
        job_key: str,
        *,
        started_at: datetime,
        required_texts: Sequence[str],
        evidence_markers: Sequence[str],
        slack_seconds: int = 10,
    ) -> dict | None:
        monitor = self.spec.local_monitor
        execution_record = self.job_execution_after(job_key, started_at=started_at, slack_seconds=slack_seconds)
        if execution_record is None:
            return None
        required = [str(value) for value in required_texts if str(value)]
        markers = [str(value) for value in evidence_markers if str(value)]
        for execution in execution_record.get("executions", []):
            execution_name = self._cloud_run_execution_name(execution)
            if not execution_name:
                continue
            logs = self._execution_logs_json(
                execution_name,
                project_id=str(execution_record["project_id"]),
                monitor=monitor,
            )
            log_text = str(logs.get("stdout", ""))
            if all(text in log_text for text in required) and (not markers or any(marker in log_text for marker in markers)):
                execution_view = self.cloud_run_execution_view(job_key, execution_name)
                return {
                    **execution_record,
                    "execution_name": execution_name,
                    "required_texts": required,
                    "evidence_markers": markers,
                    "view_urls": execution_view.view_urls,
                    "logs": logs,
                }
        return None

    def tfvars_plan(self, context: dict) -> dict:
        materialization_context = WJobBardTfvarsContext.model_validate(context)
        jobs = {}
        cron_triggers = {}
        event_triggers = {}

        for job_key in self.spec.effective_job_keys:
            job = self.spec.jobs[job_key]
            if job.runtime is None:
                raise ValueError(f"GCP WJobBard Terraform job [{job_key}] requires runtime.")

            job_env = {
                **materialization_context.configmap,
                **job.runtime.env,
                "WJOBBARD_JOB_KEY": job_key,
                "WJOBBARD_KIND": job.kind.value,
                "WJOBBARD_SRC": job.src or "",
                "WJOBBARD_SINK": job.sink or "",
            }
            jobs[job_key] = {
                "name": job.runtime.name,
                "image": job.runtime.image,
                "service_account_email": job.runtime.service_account_email,
                "command": job.runtime.command,
                "args": job.runtime.args,
                "env": job_env,
                "secret_env": [secret_env.model_dump(mode="json") for secret_env in job.runtime.secret_env],
                "task_count": job.runtime.task_count,
                "parallelism": job.runtime.parallelism,
                "timeout": job.runtime.timeout,
                "max_retries": job.runtime.max_retries,
                "cpu": job.runtime.cpu,
                "memory": job.runtime.memory,
                "kind": job.kind.value,
                "src": job.src or "",
                "sink": job.sink or "",
                "input_event_types": job.input_event_types,
                "output_event_types": job.output_event_types,
                "lifecycle_topic_ref": job.lifecycle_topic_ref or "",
            }

            for trigger_key, trigger in job.triggers.items():
                if not trigger.enabled:
                    continue
                materialized_trigger = {
                    "job_key": job_key,
                    "job_name": job.runtime.name,
                    "name": trigger.resource_name or f"{job.runtime.name}-{trigger.key}",
                    "trigger_key": trigger.key,
                    "input_event_type": trigger.input_event_type or "",
                    "invoker_service_account_email": job.runtime.service_account_email,
                }
                if trigger.trigger_type == WJobBardTriggerType.CRON:
                    cron_triggers[f"{job_key}--{trigger_key}"] = {
                        **materialized_trigger,
                        "schedule": trigger.schedule,
                        "time_zone": trigger.time_zone,
                    }
                elif trigger.trigger_type == WJobBardTriggerType.EVENT:
                    event_triggers[f"{job_key}--{trigger_key}"] = {
                        **materialized_trigger,
                        "topic_name": trigger.topic_ref,
                        "workflow_name": f"{materialized_trigger['name']}-workflow",
                    }

        tfvars = WJobBardGCPTerraformTfvars.model_validate(
            {
                "jobs": jobs,
                "cron_triggers": cron_triggers,
                "event_triggers": event_triggers,
            }
        )
        return tfvars.model_dump(mode="json")


class AWSJobBard(WJobBard):
    provider = WJobBardProvider.AWS

    def apply(self):
        raise NotImplementedError("AWSJobBard.apply is reserved for the AWS scheduling milestone.")
