from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from wielder.spark.runtime import bootstrap_spark_env


@dataclass(frozen=True)
class SparkSubmitResult:
    command: list[str]
    returncode: int


@dataclass(frozen=True)
class JarSparkJobSpec:
    name: str
    jar_path: str
    main_class: str
    app_args: list[str] = field(default_factory=list)
    master: str | None = None
    deploy_mode: str | None = None
    spark_conf: dict[str, str] = field(default_factory=dict)

    def command(self) -> list[str]:
        command = ["spark-submit"]
        if self.master:
            command.extend(["--master", self.master])
        if self.deploy_mode:
            command.extend(["--deploy-mode", self.deploy_mode])
        command.extend(["--class", self.main_class])
        for key, value in self.spark_conf.items():
            command.extend(["--conf", f"{key}={value}"])
        command.append(self.jar_path)
        command.extend(self.app_args)
        return command


@dataclass(frozen=True)
class PySparkJobSpec:
    name: str
    entrypoint: str
    app_args: list[str] = field(default_factory=list)
    master: str | None = None
    deploy_mode: str | None = None
    py_files: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    archives: list[str] = field(default_factory=list)
    packages: list[str] = field(default_factory=list)
    spark_conf: dict[str, str] = field(default_factory=dict)

    def command(self) -> list[str]:
        command = ["spark-submit"]
        if self.master:
            command.extend(["--master", self.master])
        if self.deploy_mode:
            command.extend(["--deploy-mode", self.deploy_mode])
        if self.py_files:
            command.extend(["--py-files", ",".join(self.py_files)])
        if self.files:
            command.extend(["--files", ",".join(self.files)])
        if self.archives:
            command.extend(["--archives", ",".join(self.archives)])
        if self.packages:
            command.extend(["--packages", ",".join(self.packages)])
        for key, value in self.spark_conf.items():
            command.extend(["--conf", f"{key}={value}"])
        command.append(self.entrypoint)
        command.extend(self.app_args)
        return command


class LocalSparkSubmitter:
    def __init__(
        self,
        *,
        spark_home: str | Path | None = None,
        java_home: str | Path | None = None,
        pyspark_python: str | None = None,
    ) -> None:
        self.spark_home = spark_home
        self.java_home = java_home
        self.pyspark_python = pyspark_python

    def submit(self, job: JarSparkJobSpec | PySparkJobSpec, *, dry_run: bool = False) -> SparkSubmitResult:
        command = job.command()
        if dry_run:
            return SparkSubmitResult(command=command, returncode=0)
        bootstrap_spark_env(
            spark_home=self.spark_home,
            java_home=self.java_home,
            pyspark_python=self.pyspark_python,
        )
        completed = subprocess.run(command, check=False)
        return SparkSubmitResult(command=command, returncode=completed.returncode)


def pyspark_job_spec_from_conf(
    job_conf,
    *,
    entrypoint: str | None = None,
    py_files: list[str] | None = None,
    files: list[str] | None = None,
    extra_files: list[str] | None = None,
    archives: list[str] | None = None,
    packages: list[str] | None = None,
    spark_conf: dict[str, str] | None = None,
    app_args: list[str] | None = None,
) -> PySparkJobSpec:
    def _optional_str(name: str) -> str | None:
        value = getattr(job_conf, name)
        return None if value is None else str(value)

    configured_spark_conf = {}
    for key, value in _plain_config_value(job_conf.spark_conf).items():
        configured_spark_conf[str(key)] = str(value)
    if spark_conf is not None:
        configured_spark_conf = {str(key): str(value) for key, value in spark_conf.items()}

    configured_files = files if files is not None else [str(item) for item in job_conf.files]
    if extra_files:
        configured_files = [*configured_files, *[str(item) for item in extra_files]]

    return PySparkJobSpec(
        name=str(job_conf.name),
        entrypoint=str(entrypoint if entrypoint is not None else job_conf.entrypoint),
        master=_optional_str("master"),
        deploy_mode=_optional_str("deploy_mode"),
        py_files=[str(item) for item in (py_files if py_files is not None else job_conf.py_files)],
        files=[str(item) for item in configured_files],
        archives=[str(item) for item in (archives if archives is not None else job_conf.archives)],
        packages=[str(item) for item in (packages if packages is not None else job_conf.packages)],
        spark_conf=configured_spark_conf,
        app_args=app_args if app_args is not None else [str(item) for item in job_conf.app_args],
    )


def _plain_config_value(value: Any) -> Any:
    if hasattr(value, "as_plain_ordered_dict"):
        return value.as_plain_ordered_dict()
    if isinstance(value, list):
        return [_plain_config_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain_config_value(item) for key, item in value.items()}
    return value
