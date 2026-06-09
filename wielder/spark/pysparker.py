from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, model_validator

from wielder.python.artifactor import (
    PythonArchiveSource,
    ResolvedConfPublisher,
    WieldedPythonArtifacts,
    bootstrap_conf_app_args,
    bootstrap_conf_files,
    prepare_wielded_python_artifacts,
    print_pyspark_cleanup_report,
    print_wielded_python_artifact_report,
)
from wielder.spark.submit import LocalSparkSubmitter, PySparkJobSpec, SparkSubmitResult
from wielder.spark.submit import pyspark_job_spec_from_conf
from wielder.spark.types import PySparkCleanupTarget
from wielder.util.util import get_aws_session
from wielder.wield.enumerator import RuntimeEnv, WieldAction, local_deployments


class PySparkRuntime(Enum):
    LOCAL = "local"
    EMR = "emr"
    DATAPROC = "dataproc"
    AZURE_SYNAPSE = "azure_synapse"
    AZURE_HDINSIGHT = "azure_hdinsight"
    DATABRICKS = "databricks"


EMR_ACTIVE_CLUSTER_STATES = ("STARTING", "BOOTSTRAPPING", "RUNNING", "WAITING")
EMR_PYTHON_RUNTIME_BOOTSTRAP_ACTION_NAME = "install-python-runtime-dependencies"
EMR_HADOOP_HOME = "/home/hadoop"
EMR_PYTHON_USER_BASE = f"{EMR_HADOOP_HOME}/.local"
EMR_PYTHON_RUNTIME_PATH = f"{EMR_PYTHON_USER_BASE}/wielder-python-runtime"
EMR_PYTHON_RUNTIME_BINARY = "/usr/bin/python3.11"
EMR_WIELDER_STAGE_ROOT = "/tmp/wielder-stage/culture"
EMR_GIT_PYTHON_REFRESH = "quiet"
EMR_SKIP_GIT_SNAPSHOT = "true"
PYSPARK_JOB_LOG_ENABLED_ENV = "WIELDER_PYSPARK_JOB_LOG_ENABLED"
PYSPARK_JOB_LOG_LEVEL_ENV = "WIELDER_PYSPARK_JOB_LOG_LEVEL"
PYSPARK_JOB_LOG_FORMAT_ENV = "WIELDER_PYSPARK_JOB_LOG_FORMAT"
PYSPARK_JOB_LOG_DATEFMT_ENV = "WIELDER_PYSPARK_JOB_LOG_DATEFMT"
PYSPARK_JOB_LOG_DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
EMR_WAIT_LOG_LEVELS = {
    "critical": logging.CRITICAL,
    "fatal": logging.FATAL,
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "warn": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}


class PySparkRuntimeTree(BaseModel):
    model_config = ConfigDict(extra="allow", use_enum_values=True)

    runtime: PySparkRuntime

    @model_validator(mode="after")
    def validate_selected_runtime_tree(self) -> "PySparkRuntimeTree":
        runtime = str(self.runtime)
        if runtime != PySparkRuntime.LOCAL.value and runtime not in (self.model_extra or {}):
            raise ValueError(
                f"PySpark runtime tree selected [{runtime}] but did not define [{runtime}] config."
            )
        return self

    def overlay_tree(self) -> dict[str, Any]:
        return self.model_dump(mode="python")


@dataclass(frozen=True)
class PySparkRunSpec:
    job: PySparkJobSpec
    cleanup_targets: list[PySparkCleanupTarget] = field(default_factory=list)


@dataclass(frozen=True)
class PySparkCleanupResult:
    target: PySparkCleanupTarget
    matched_keys: list[str]
    deleted: bool
    action: str


@dataclass(frozen=True)
class PySparkActionResult:
    command: list[str]
    submitted: bool
    submit_result: SparkSubmitResult | None = None
    cleanup_results: list[PySparkCleanupResult] = field(default_factory=list)


@dataclass(frozen=True)
class PySparkArtifactJob:
    target_conf: Any
    app_name: str
    repo_root: Path
    spark_conf: Any
    job_key: str
    bootstrap_ref_path: tuple[str, ...]
    unique_name: str
    bucketeer: Any
    publish_resolved_conf: ResolvedConfPublisher | None
    pysparker_runtime_conf: Any | None = None

    def __post_init__(self) -> None:
        if self.pysparker_runtime_conf is None:
            return
        if not self.bootstrap_ref_path:
            return
        apply_pysparker_runtime_tree(
            self.target_conf,
            spark_ref_path=spark_ref_path_from_bootstrap_ref_path(self.bootstrap_ref_path),
            runtime_conf=self.pysparker_runtime_conf,
        )

    @property
    def job_conf(self) -> Any:
        return self.spark_conf.jobs[self.job_key]

    @property
    def uses_resolved_conf_bootstrap(self) -> bool:
        return self.publish_resolved_conf is not None

    def prepare_artifacts(
        self,
        *,
        write: bool,
        force_write: bool = False,
        archive_sources: list[PythonArchiveSource] | None = None,
    ) -> WieldedPythonArtifacts:
        return prepare_wielded_python_artifacts(
            target_conf=self.target_conf,
            app_name=self.app_name,
            repo_root=self.repo_root,
            runtime_conf=self.spark_conf,
            job_conf=self.job_conf,
            bootstrap_ref_path=self.bootstrap_ref_path,
            unique_name=self.unique_name,
            write=write,
            bucketeer=self.bucketeer,
            force_write=force_write,
            publish_resolved_conf=self.publish_resolved_conf,
            archive_sources=archive_sources,
        )

    def run_spec(
        self,
        artifacts: WieldedPythonArtifacts,
        *,
        app_args: list[str] | None = None,
    ) -> PySparkRunSpec:
        files = (
            bootstrap_conf_files(artifacts, self.job_conf)
            if self.uses_resolved_conf_bootstrap
            else [str(item) for item in self.job_conf.files]
        )
        configured_app_args = (
            bootstrap_conf_app_args(artifacts)
            if self.uses_resolved_conf_bootstrap
            else [str(item) for item in self.job_conf.app_args]
        )
        job = pyspark_job_spec_from_conf(
            self.job_conf,
            entrypoint=artifacts.entrypoint,
            py_files=artifacts.py_files,
            files=files,
            archives=[
                *[str(item) for item in self.job_conf.archives],
                *artifacts.archives,
            ],
            app_args=app_args if app_args is not None else configured_app_args,
        )
        return PySparkRunSpec(
            job=job,
            cleanup_targets=artifacts.cleanup_targets,
        )


def spark_ref_path_from_bootstrap_ref_path(bootstrap_ref_path: tuple[str, ...]) -> tuple[str, ...]:
    if bootstrap_ref_path and bootstrap_ref_path[-1] == "resolved_conf":
        return bootstrap_ref_path[:-1]
    return bootstrap_ref_path


def apply_pysparker_runtime_tree(
    target_conf: Any,
    *,
    spark_ref_path: tuple[str, ...],
    runtime_conf: Any,
) -> None:
    """Overlay a configured runtime tree onto the app's pysparker config branch."""
    root = ".".join((*spark_ref_path, "pysparker"))
    runtime_tree = PySparkRuntimeTree.model_validate(_plain_config_value(runtime_conf))
    _put_config_tree(target_conf, root, runtime_tree.overlay_tree())


def _put_config_tree(target_conf: Any, root: str, value: Any) -> None:
    if isinstance(value, dict):
        for key, child_value in value.items():
            _put_config_tree(target_conf, f"{root}.{key}", child_value)
        return
    target_conf.put(root, value)


def _plain_config_value(value: Any) -> Any:
    if hasattr(value, "as_plain_ordered_dict"):
        return value.as_plain_ordered_dict()
    if isinstance(value, list):
        return [_plain_config_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain_config_value(item) for key, item in value.items()}
    return value


class PySparker(ABC):
    def __init__(self, *, bucketeer: Any | None = None) -> None:
        self.bucketeer = bucketeer

    def plan(self, run_spec: PySparkRunSpec) -> SparkSubmitResult:
        return self.submit(run_spec, dry_run=True)

    @abstractmethod
    def submit(self, run_spec: PySparkRunSpec, *, dry_run: bool = False) -> SparkSubmitResult:
        pass

    def delete(self, run_spec: PySparkRunSpec) -> list[PySparkCleanupResult]:
        return self.cleanup(run_spec, action=WieldAction.DELETE)

    def wield_artifact_job(
        self,
        artifact_job: PySparkArtifactJob,
        *,
        action: WieldAction | str,
        actions_conf,
        write: bool | None = None,
        artifacts: WieldedPythonArtifacts | None = None,
        archive_sources: list[PythonArchiveSource] | None = None,
        app_args: list[str] | None = None,
        logger: Any | None = None,
    ) -> PySparkActionResult:
        if artifacts is None:
            if write is None:
                write = should_publish_pyspark_artifacts(action, actions_conf)
            force_write = should_force_publish_pyspark_artifacts(action, actions_conf)
            artifacts = artifact_job.prepare_artifacts(
                write=write,
                force_write=force_write,
                archive_sources=archive_sources,
            )

        run_spec = artifact_job.run_spec(artifacts, app_args=app_args)
        command = " ".join(run_spec.job.command())
        if logger is not None:
            if artifacts.conf_publication:
                logger.info(
                    "Resolved config artifact: %s/%s",
                    artifacts.conf_publication["bucket"],
                    artifacts.conf_publication["versioned_key"],
                )
            logger.info("PySpark artifact manifest: %s", artifacts.manifest_uri)
            logger.info("Spark command: %s", command)
        print_wielded_python_artifact_report(artifacts, spark_command=command)
        result = wield(
            pysparker=self,
            run_spec=run_spec,
            action=action,
            actions_conf=actions_conf,
            delete_artifacts_on_delete=bool(
                artifact_job.spark_conf.pysparker.cleanup.delete_artifacts_on_delete
            ),
        )
        print_pyspark_cleanup_report(result.cleanup_results)
        return result

    def cleanup(
        self,
        run_spec: PySparkRunSpec,
        *,
        action: WieldAction | str = WieldAction.APPLY,
    ) -> list[PySparkCleanupResult]:
        action = action if isinstance(action, WieldAction) else WieldAction(str(action))
        if self.bucketeer is None:
            raise RuntimeError("PySpark cleanup requires a configured Bucketeer.")

        should_delete = action in {WieldAction.APPLY, WieldAction.DELETE, WieldAction.RUN}
        results: list[PySparkCleanupResult] = []
        for target in run_spec.cleanup_targets:
            matched_keys = self.bucketeer.object_keys_by_prefix(
                target.bucket,
                target.root_key,
                recursive=target.recursive,
            )
            logging.info(
                "PySpark cleanup [%s] matched [%d] objects under [%s/%s].",
                target.label,
                len(matched_keys),
                target.bucket,
                target.root_key,
            )
            if should_delete:
                for key in matched_keys:
                    self.bucketeer.delete_file(target.bucket, key)
            results.append(
                PySparkCleanupResult(
                    target=target,
                    matched_keys=matched_keys,
                    deleted=should_delete,
                    action=action.value,
                )
            )
        return results


class LocalPySparker(PySparker):
    def __init__(
        self,
        *,
        spark_home: str | Path | None = None,
        java_home: str | Path | None = None,
        pyspark_python: str | None = None,
        bucketeer: Any | None = None,
    ) -> None:
        super().__init__(bucketeer=bucketeer)
        self.submitter = LocalSparkSubmitter(
            spark_home=spark_home,
            java_home=java_home,
            pyspark_python=pyspark_python,
        )

    def submit(self, run_spec: PySparkRunSpec, *, dry_run: bool = False) -> SparkSubmitResult:
        return self.submitter.submit(run_spec.job, dry_run=dry_run)


class EMRPySparker(PySparker):
    ACTIVE_CLUSTER_STATES = EMR_ACTIVE_CLUSTER_STATES
    PYTHON_RUNTIME_BOOTSTRAP_ACTION_NAME = EMR_PYTHON_RUNTIME_BOOTSTRAP_ACTION_NAME

    def __init__(
        self,
        *,
        emr_conf: Any,
        auth_conf: Any | None = None,
        bucketeer: Any | None = None,
        emr_client: Any | None = None,
        job_log_conf: Any | None = None,
    ) -> None:
        super().__init__(bucketeer=bucketeer)
        self.emr_conf = emr_conf
        self.auth_conf = auth_conf if auth_conf is not None else emr_conf
        self._emr_client = emr_client
        self.job_log_conf = job_log_conf

    def submit(self, run_spec: PySparkRunSpec, *, dry_run: bool = False) -> SparkSubmitResult:
        cluster_id = None if dry_run else self._resolve_cluster_id()
        job = self._with_emr_python_runtime_env(run_spec.job, cluster_id=cluster_id)
        command = job.command()
        if dry_run:
            return SparkSubmitResult(command=command, returncode=0)

        step = {
            "Name": str(run_spec.job.name),
            "ActionOnFailure": str(self.emr_conf.action_on_failure),
            "HadoopJarStep": {
                "Jar": "command-runner.jar",
                "Args": command,
            },
        }
        response = self.emr_client.add_job_flow_steps(JobFlowId=cluster_id, Steps=[step])
        step_ids = [str(step_id) for step_id in response.get("StepIds", [])]
        logging.info("Submitted EMR Spark step(s) %s to cluster [%s].", step_ids, cluster_id)
        if bool(self.emr_conf.wait_for_completion):
            self._wait_for_steps(cluster_id, step_ids)
        return SparkSubmitResult(command=command, returncode=0)

    @property
    def emr_client(self) -> Any:
        if self._emr_client is None:
            import boto3

            runtime_env = self._runtime_env()
            if runtime_env.value in local_deployments:
                session = get_aws_session(self.auth_conf)
            else:
                session = boto3.Session(region_name=self._aws_region())
            self._emr_client = session.client("emr")
        return self._emr_client

    def _runtime_env(self) -> RuntimeEnv:
        value = _optional_conf_value(self.auth_conf, "runtime_env")
        if value is None:
            value = _optional_conf_value(self.emr_conf, "runtime_env")
        if value is None:
            value = _optional_conf_value(self.emr_conf, "launch_env", RuntimeEnv.MAC.value)
        return value if isinstance(value, RuntimeEnv) else RuntimeEnv(str(value))

    def _aws_region(self) -> str | None:
        value = _optional_conf_value(self.auth_conf, "aws_zone")
        if value is None:
            value = _optional_conf_value(self.auth_conf, "aws_region")
        if value is None:
            value = _optional_conf_value(self.emr_conf, "aws_zone")
        if value is None:
            value = _optional_conf_value(self.emr_conf, "aws_region")
        if value is None:
            return None
        return str(value).strip() or None

    def _resolve_cluster_id(self) -> str:
        cluster_id = str(self.emr_conf.cluster_id).strip()
        if cluster_id:
            return cluster_id

        cluster_name = str(self.emr_conf.cluster_name).strip()
        if not cluster_name:
            raise ValueError("EMR PySparker requires either pysparker.emr.cluster_id or cluster_name.")

        states = [str(state) for state in self.emr_conf.cluster_states]
        resolved_cluster_id = self.latest_cluster_id(cluster_name, states=states)
        if resolved_cluster_id is None:
            raise RuntimeError(f"No EMR cluster named [{cluster_name}] found in states {states}.")
        return resolved_cluster_id

    def latest_cluster_id(
        self,
        cluster_name: str,
        *,
        states: Sequence[str] | None = None,
    ) -> str | None:
        matching_clusters = [
            cluster
            for cluster in self._list_clusters(states=states or self.ACTIVE_CLUSTER_STATES)
            if str(cluster.get("Name")) == cluster_name
        ]
        if not matching_clusters:
            return None

        matching_clusters.sort(
            key=_emr_cluster_creation_sort_key,
            reverse=True,
        )
        cluster_id = matching_clusters[0].get("Id")
        return str(cluster_id) if cluster_id else None

    def bootstrap_action_args(self, cluster_id: str, action_name: str) -> list[str] | None:
        bootstrap_actions = self.emr_client.list_bootstrap_actions(ClusterId=cluster_id).get(
            "BootstrapActions",
            [],
        )
        for bootstrap_action in bootstrap_actions:
            if bootstrap_action.get("Name") != action_name:
                continue
            args = bootstrap_action.get("ScriptBootstrapAction", {}).get("Args", [])
            return [str(arg) for arg in args]
        return None

    def latest_cluster_bootstrap_action_args(
        self,
        cluster_name: str,
        *,
        action_name: str = EMR_PYTHON_RUNTIME_BOOTSTRAP_ACTION_NAME,
        states: Sequence[str] | None = None,
    ) -> tuple[str, list[str] | None] | None:
        cluster_id = self.latest_cluster_id(cluster_name, states=states)
        if cluster_id is None:
            return None
        return cluster_id, self.bootstrap_action_args(cluster_id, action_name)

    def _list_clusters(self, *, states: Sequence[str]) -> list[dict[str, Any]]:
        states = [str(state) for state in states]
        if hasattr(self.emr_client, "get_paginator"):
            paginator = self.emr_client.get_paginator("list_clusters")
            clusters = []
            for page in paginator.paginate(ClusterStates=states):
                clusters.extend(page.get("Clusters", []))
            return clusters

        response = self.emr_client.list_clusters(ClusterStates=states)
        return list(response.get("Clusters", []))

    def _wait_for_steps(self, cluster_id: str, step_ids: list[str]) -> None:
        terminal_success = {"COMPLETED"}
        terminal_failure = {"CANCELLED", "FAILED", "INTERRUPTED"}
        wait_started_at = time.time()
        deadline = wait_started_at + float(self.emr_conf.wait_timeout_seconds)
        poll_seconds = float(self.emr_conf.wait_poll_seconds)
        wait_log_conf = _optional_conf_value(self.emr_conf, "wait_log")
        last_logged_state_by_step: dict[str, str] = {}
        last_logged_at_by_step: dict[str, float] = {}

        pending = set(step_ids)
        while pending and time.time() < deadline:
            for step_id in list(pending):
                response = self.emr_client.describe_step(ClusterId=cluster_id, StepId=step_id)
                state = str(response["Step"]["Status"]["State"])
                now = time.time()
                if _should_log_emr_step_state(
                    wait_log_conf,
                    state=state,
                    last_logged_state=last_logged_state_by_step.get(step_id),
                    last_logged_at=last_logged_at_by_step.get(step_id),
                    now=now,
                    wait_started_at=wait_started_at,
                ):
                    _log_emr_step_state(
                        wait_log_conf,
                        step_id=step_id,
                        state=state,
                        elapsed_seconds=now - wait_started_at,
                    )
                    last_logged_state_by_step[step_id] = state
                    last_logged_at_by_step[step_id] = now
                if state in terminal_success:
                    pending.remove(step_id)
                elif state in terminal_failure:
                    raise RuntimeError(f"EMR step [{step_id}] failed in state [{state}].")
            if pending:
                time.sleep(poll_seconds)

        if pending:
            raise TimeoutError(f"Timed out waiting for EMR step(s): {sorted(pending)}")

    def _with_emr_python_runtime_env(
        self,
        job: PySparkJobSpec,
        *,
        cluster_id: str | None = None,
    ) -> PySparkJobSpec:
        spark_conf = dict(job.spark_conf)
        runtime_binary = str(
            _optional_conf_value(
                self.emr_conf,
                "python_runtime_binary",
                EMR_PYTHON_RUNTIME_BINARY,
            )
        )
        runtime_env_conf = {
            "spark.pyspark.python": runtime_binary,
            "spark.pyspark.driver.python": runtime_binary,
            "spark.yarn.appMasterEnv.HOME": EMR_HADOOP_HOME,
            "spark.yarn.appMasterEnv.PYTHONPATH": EMR_PYTHON_RUNTIME_PATH,
            "spark.yarn.appMasterEnv.PYTHONUSERBASE": EMR_PYTHON_USER_BASE,
            "spark.yarn.appMasterEnv.PYSPARK_PYTHON": runtime_binary,
            "spark.yarn.appMasterEnv.GIT_PYTHON_REFRESH": EMR_GIT_PYTHON_REFRESH,
            "spark.yarn.appMasterEnv.WIELDER_STAGE_ROOT": EMR_WIELDER_STAGE_ROOT,
            "spark.yarn.appMasterEnv.WIELDER_SKIP_GIT_SNAPSHOT": EMR_SKIP_GIT_SNAPSHOT,
            "spark.executorEnv.HOME": EMR_HADOOP_HOME,
            "spark.executorEnv.PYTHONPATH": EMR_PYTHON_RUNTIME_PATH,
            "spark.executorEnv.PYTHONUSERBASE": EMR_PYTHON_USER_BASE,
            "spark.executorEnv.PYSPARK_PYTHON": runtime_binary,
            "spark.executorEnv.GIT_PYTHON_REFRESH": EMR_GIT_PYTHON_REFRESH,
            "spark.executorEnv.WIELDER_STAGE_ROOT": EMR_WIELDER_STAGE_ROOT,
            "spark.executorEnv.WIELDER_SKIP_GIT_SNAPSHOT": EMR_SKIP_GIT_SNAPSHOT,
        }
        runtime_env_conf.update(
            _emr_pyspark_job_log_runtime_env_conf(
                self.job_log_conf
                if self.job_log_conf is not None
                else _optional_conf_value(self.emr_conf, "job_log")
            )
        )
        for key, value in runtime_env_conf.items():
            spark_conf.setdefault(key, value)
        self._apply_emr_resource_profile(spark_conf, cluster_id=cluster_id)
        return replace(job, spark_conf=spark_conf)

    def _apply_emr_resource_profile(
        self,
        spark_conf: dict[str, str],
        *,
        cluster_id: str | None,
    ) -> None:
        profile = _optional_conf_value(self.emr_conf, "resource_profile")
        if profile is None or not _optional_conf_bool(profile, "enabled", False):
            return

        set_only_if_missing = _optional_conf_bool(profile, "set_only_if_missing", True)

        def put_spark_conf(key: str, value: Any) -> None:
            if value is None:
                return
            if set_only_if_missing and key in spark_conf:
                return
            spark_conf[key] = str(value).lower() if isinstance(value, bool) else str(value)

        worker_count = self._emr_worker_instance_count(cluster_id, profile)
        executor_instances = _emr_profile_executor_instances(profile, worker_count=worker_count)

        put_spark_conf(
            "spark.dynamicAllocation.enabled",
            _optional_conf_bool(profile, "dynamic_allocation_enabled", False),
        )
        put_spark_conf("spark.executor.instances", executor_instances)
        put_spark_conf("spark.executor.cores", _optional_conf_value(profile, "executor_cores"))
        put_spark_conf("spark.executor.memory", _optional_conf_value(profile, "executor_memory"))
        put_spark_conf(
            "spark.executor.memoryOverhead",
            _optional_conf_value(profile, "executor_memory_overhead"),
        )
        put_spark_conf("spark.driver.memory", _optional_conf_value(profile, "driver_memory"))

        if worker_count is not None:
            logging.info(
                "Applied EMR Spark resource profile from cluster [%s]: workers=%s, executors=%s.",
                cluster_id,
                worker_count,
                executor_instances,
            )

    def _emr_worker_instance_count(self, cluster_id: str | None, profile: Any) -> int | None:
        fallback_worker_count = _optional_conf_int(profile, "fallback_worker_count")
        if cluster_id is None or not _optional_conf_bool(
            profile,
            "derive_executor_instances_from_cluster",
            True,
        ):
            return fallback_worker_count

        response = self.emr_client.list_instances(
            ClusterId=cluster_id,
            InstanceGroupTypes=[
                str(item)
                for item in _optional_conf_value(profile, "worker_group_types", ["CORE", "TASK"])
            ],
            InstanceStates=[
                str(item) for item in _optional_conf_value(profile, "worker_states", ["RUNNING"])
            ],
        )
        return len(response.get("Instances", []))


def _emr_cluster_creation_sort_key(cluster) -> float:
    creation_time = cluster.get("Status", {}).get("Timeline", {}).get("CreationDateTime")
    if hasattr(creation_time, "timestamp"):
        return float(creation_time.timestamp())
    return float(creation_time or 0)


def _should_log_emr_step_state(
    wait_log_conf: Any,
    *,
    state: str,
    last_logged_state: str | None,
    last_logged_at: float | None,
    now: float,
    wait_started_at: float,
) -> bool:
    if wait_log_conf is None:
        return True
    if not _optional_conf_bool(wait_log_conf, "enabled", True):
        return False
    if _optional_conf_bool(wait_log_conf, "log_every_poll", False):
        return True
    if last_logged_state is None or last_logged_at is None:
        return _optional_conf_bool(wait_log_conf, "log_initial_state", True)
    if state != last_logged_state and _optional_conf_bool(wait_log_conf, "log_state_changes", True):
        return True

    repeated_log_seconds = _emr_repeated_state_log_seconds(
        wait_log_conf,
        elapsed_seconds=now - wait_started_at,
    )
    return now - last_logged_at >= repeated_log_seconds


def _log_emr_step_state(
    wait_log_conf: Any,
    *,
    step_id: str,
    state: str,
    elapsed_seconds: float,
) -> None:
    level = _emr_wait_log_level(wait_log_conf)
    if wait_log_conf is not None and _optional_conf_bool(wait_log_conf, "include_elapsed", True):
        logging.log(
            level,
            "EMR step [%s] state [%s] (elapsed %.0fs).",
            step_id,
            state,
            elapsed_seconds,
        )
        return
    logging.log(level, "EMR step [%s] state [%s].", step_id, state)


def _emr_wait_log_level(wait_log_conf: Any) -> int:
    value = (
        _optional_conf_value(wait_log_conf, "level", "info")
        if wait_log_conf is not None
        else "info"
    )
    if isinstance(value, int):
        return value
    return EMR_WAIT_LOG_LEVELS.get(str(value).strip().lower(), logging.INFO)


def _emr_repeated_state_log_seconds(wait_log_conf: Any, *, elapsed_seconds: float) -> float:
    default_seconds = float(_optional_conf_value(wait_log_conf, "repeated_state_log_seconds", 300))
    tiers = _optional_conf_value(wait_log_conf, "tiers", [])
    selected_seconds = default_seconds
    for tier in _plain_config_value(tiers or []):
        threshold = float(tier.get("after_elapsed_seconds", 0))
        if elapsed_seconds >= threshold:
            selected_seconds = float(tier.get("repeated_state_log_seconds", selected_seconds))
    return max(0.0, selected_seconds)


def _emr_profile_executor_instances(profile: Any, *, worker_count: int | None) -> int | None:
    if worker_count is None:
        return _optional_conf_int(profile, "fallback_executor_instances")

    reserve_workers = _optional_conf_int(profile, "reserve_workers", 0)
    executor_instances_per_worker = _optional_conf_float(
        profile,
        "executor_instances_per_worker",
        1.0,
    )
    executor_worker_fraction = _optional_conf_float(profile, "executor_worker_fraction", 1.0)
    min_executor_instances = _optional_conf_int(profile, "min_executor_instances", 1)
    max_executor_instances = _optional_conf_int(profile, "max_executor_instances")

    available_workers = max(0, worker_count - reserve_workers)
    executor_instances = int(available_workers * executor_worker_fraction * executor_instances_per_worker)
    if min_executor_instances is not None:
        executor_instances = max(min_executor_instances, executor_instances)
    if max_executor_instances is not None:
        executor_instances = min(max_executor_instances, executor_instances)
    return max(0, executor_instances)


class DataprocPySparker(PySparker):
    def submit(self, run_spec: PySparkRunSpec, *, dry_run: bool = False) -> SparkSubmitResult:
        raise NotImplementedError(
            "Dataproc PySparker is not implemented yet. The factory boundary is present so GCP support can be added without changing app callers."
        )


class AzureSynapsePySparker(PySparker):
    def submit(self, run_spec: PySparkRunSpec, *, dry_run: bool = False) -> SparkSubmitResult:
        raise NotImplementedError(
            "Azure Synapse PySparker is not implemented yet. The factory boundary is present so Synapse Spark pool support can be added without changing app callers."
        )


class AzureHDInsightPySparker(PySparker):
    def submit(self, run_spec: PySparkRunSpec, *, dry_run: bool = False) -> SparkSubmitResult:
        raise NotImplementedError(
            "Azure HDInsight PySparker is not implemented yet. The factory boundary is present so HDInsight Spark cluster support can be added without changing app callers."
        )


class DatabricksPySparker(PySparker):
    def submit(self, run_spec: PySparkRunSpec, *, dry_run: bool = False) -> SparkSubmitResult:
        raise NotImplementedError(
            "Databricks PySparker is not implemented yet. The factory boundary is present so Databricks support can be added without changing app callers."
        )


def get_pysparker(
    conf,
    *,
    bucketeer: Any | None = None,
    auth_conf: Any | None = None,
    runtime: str | PySparkRuntime | None = None,
) -> PySparker:
    selected_runtime = runtime
    if selected_runtime is None:
        selected_runtime = str(conf.pysparker.runtime)
    selected_runtime = (
        selected_runtime
        if isinstance(selected_runtime, PySparkRuntime)
        else PySparkRuntime(str(selected_runtime))
    )

    if selected_runtime == PySparkRuntime.LOCAL:
        return LocalPySparker(
            spark_home=conf.spark_home,
            java_home=conf.java_home,
            pyspark_python=conf.pyspark_python,
            bucketeer=bucketeer,
        )
    if selected_runtime == PySparkRuntime.EMR:
        return EMRPySparker(
            emr_conf=conf.pysparker.emr,
            auth_conf=auth_conf if auth_conf is not None else conf,
            bucketeer=bucketeer,
            job_log_conf=_optional_conf_value(conf.pysparker, "job_log"),
        )
    if selected_runtime == PySparkRuntime.DATAPROC:
        return DataprocPySparker(bucketeer=bucketeer)
    if selected_runtime == PySparkRuntime.AZURE_SYNAPSE:
        return AzureSynapsePySparker(bucketeer=bucketeer)
    if selected_runtime == PySparkRuntime.AZURE_HDINSIGHT:
        return AzureHDInsightPySparker(bucketeer=bucketeer)
    if selected_runtime == PySparkRuntime.DATABRICKS:
        return DatabricksPySparker(bucketeer=bucketeer)
    raise ValueError(f"Unsupported PySpark runtime [{selected_runtime}].")


def _optional_conf_value(conf: Any, key: str, default: Any = None) -> Any:
    if hasattr(conf, key):
        return getattr(conf, key)
    if isinstance(conf, dict):
        return conf.get(key, default)
    try:
        if key in conf:
            return conf[key]
    except TypeError:
        pass
    return default


def _optional_conf_bool(conf: Any, key: str, default: bool = False) -> bool:
    value = _optional_conf_value(conf, key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _optional_conf_int(conf: Any, key: str, default: int | None = None) -> int | None:
    value = _optional_conf_value(conf, key, default)
    if value is None:
        return default
    return int(value)


def _optional_conf_float(conf: Any, key: str, default: float | None = None) -> float | None:
    value = _optional_conf_value(conf, key, default)
    if value is None:
        return default
    return float(value)


def configure_pyspark_job_logging(
    conf: Any | None = None,
    *,
    logger_name: str | None = None,
) -> logging.Logger:
    """Configure stdout/stderr Python logging for a PySpark driver or executor."""
    logger = logging.getLogger(logger_name)
    job_log_conf = _resolve_pyspark_job_log_conf(conf)
    if not _pyspark_job_log_enabled(job_log_conf):
        return logger

    level = _pyspark_log_level(
        os.environ.get(PYSPARK_JOB_LOG_LEVEL_ENV)
        or _optional_conf_value(job_log_conf, "level", "info")
    )
    log_format = str(
        os.environ.get(PYSPARK_JOB_LOG_FORMAT_ENV)
        or _optional_conf_value(job_log_conf, "format", PYSPARK_JOB_LOG_DEFAULT_FORMAT)
    )
    datefmt = os.environ.get(PYSPARK_JOB_LOG_DATEFMT_ENV) or _optional_conf_value(
        job_log_conf,
        "datefmt",
    )
    force = _optional_conf_bool(job_log_conf, "force", True)
    logging.basicConfig(level=level, format=log_format, datefmt=datefmt, force=force)
    logging.captureWarnings(_optional_conf_bool(job_log_conf, "capture_warnings", True))

    for child_logger, child_level in _plain_config_value(
        _optional_conf_value(job_log_conf, "loggers", {})
    ).items():
        logging.getLogger(str(child_logger)).setLevel(_pyspark_log_level(child_level))

    if _optional_conf_bool(job_log_conf, "emit_startup_summary", True):
        logger.info(
            "Configured PySpark job logging: logger=[%s], level=[%s].",
            logger.name or "root",
            logging.getLevelName(level),
        )
    return logger


def _resolve_pyspark_job_log_conf(conf: Any | None) -> Any | None:
    if conf is None:
        return None
    job_log_conf = _optional_conf_value(conf, "job_log")
    if job_log_conf is not None:
        return job_log_conf
    pysparker_conf = _optional_conf_value(conf, "pysparker")
    if pysparker_conf is not None:
        job_log_conf = _optional_conf_value(pysparker_conf, "job_log")
        if job_log_conf is not None:
            return job_log_conf
    spark_conf = _optional_conf_value(conf, "spark")
    if spark_conf is not None:
        return _resolve_pyspark_job_log_conf(spark_conf)
    return None


def _pyspark_job_log_enabled(job_log_conf: Any | None) -> bool:
    return _optional_conf_bool(job_log_conf, "enabled", True)


def _pyspark_log_level(value: Any, default: int = logging.INFO) -> int:
    if isinstance(value, int):
        return value
    if value is None:
        return default
    return EMR_WAIT_LOG_LEVELS.get(str(value).strip().lower(), default)


def _emr_pyspark_job_log_runtime_env_conf(job_log_conf: Any | None) -> dict[str, str]:
    if job_log_conf is None or not _pyspark_job_log_enabled(job_log_conf):
        return {}

    env = {
        "PYTHONUNBUFFERED": "1",
        PYSPARK_JOB_LOG_ENABLED_ENV: "true",
        PYSPARK_JOB_LOG_LEVEL_ENV: str(_optional_conf_value(job_log_conf, "level", "info")),
        PYSPARK_JOB_LOG_FORMAT_ENV: str(
            _optional_conf_value(job_log_conf, "format", PYSPARK_JOB_LOG_DEFAULT_FORMAT)
        ),
    }
    datefmt = _optional_conf_value(job_log_conf, "datefmt")
    if datefmt is not None:
        env[PYSPARK_JOB_LOG_DATEFMT_ENV] = str(datefmt)

    spark_conf: dict[str, str] = {}
    for env_key, env_value in env.items():
        spark_conf[f"spark.yarn.appMasterEnv.{env_key}"] = env_value
        spark_conf[f"spark.executorEnv.{env_key}"] = env_value
    return spark_conf


def should_submit_pyspark_action(action: WieldAction | str, actions_conf) -> bool:
    action = action if isinstance(action, WieldAction) else WieldAction(str(action))
    return (
        action == WieldAction.RUN
        and bool(actions_conf.submit_on_run)
    ) or (
        action == WieldAction.APPLY
        and bool(actions_conf.submit_on_apply)
    )


def should_publish_pyspark_artifacts(action: WieldAction | str, actions_conf) -> bool:
    action = action if isinstance(action, WieldAction) else WieldAction(str(action))
    return action in {WieldAction.APPLY, WieldAction.RUN} and bool(
        actions_conf.publish_artifacts_before_submit
    )


def should_force_publish_pyspark_artifacts(action: WieldAction | str, actions_conf) -> bool:
    if not should_publish_pyspark_artifacts(action, actions_conf):
        return False
    return bool(_optional_conf_value(actions_conf, "force_publish_artifacts_before_submit", False))


def wield(
    *,
    pysparker: PySparker,
    run_spec: PySparkRunSpec,
    action: WieldAction | str,
    actions_conf,
    delete_artifacts_on_delete: bool,
) -> PySparkActionResult:
    action = action if isinstance(action, WieldAction) else WieldAction(str(action))
    command = run_spec.job.command()

    if action == WieldAction.DELETE:
        cleanup_results: list[PySparkCleanupResult] = []
        if delete_artifacts_on_delete:
            cleanup_results = pysparker.delete(run_spec)
        return PySparkActionResult(
            command=command,
            submitted=False,
            cleanup_results=cleanup_results,
        )

    if not should_submit_pyspark_action(action, actions_conf):
        return PySparkActionResult(command=command, submitted=False)

    submit_result = pysparker.submit(run_spec)
    if submit_result.returncode != 0:
        raise RuntimeError(f"Spark submit failed with return code [{submit_result.returncode}].")
    return PySparkActionResult(
        command=command,
        submitted=True,
        submit_result=submit_result,
    )
