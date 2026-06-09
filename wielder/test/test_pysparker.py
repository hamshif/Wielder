import logging
from types import SimpleNamespace

import boto3
import pytest
from pyhocon import ConfigFactory
from wielder.python.artifactor import (
    PythonArchiveSource,
    WieldedPythonArtifacts,
    bootstrap_conf_app_args,
    bootstrap_conf_files,
)
from wielder.spark import pysparker as pysparker_module
from wielder.spark.pysparker import (
    AzureHDInsightPySparker,
    AzureSynapsePySparker,
    DatabricksPySparker,
    DataprocPySparker,
    EMRPySparker,
    PySparkArtifactJob,
    PySparkCleanupTarget,
    PySparkRunSpec,
    apply_pysparker_runtime_tree,
    configure_pyspark_job_logging,
    get_pysparker,
    should_submit_pyspark_action,
    wield,
)
from wielder.spark.submit import PySparkJobSpec, pyspark_job_spec_from_conf
from wielder.wield.enumerator import WieldAction


class FakeBucketeer:
    def __init__(self):
        self.keys = ["spark/python/job/version/main.py", "spark/python/job/version/pkg.zip"]
        self.deleted = []
        self.uploads = []

    def object_keys_by_prefix(self, bucket_name, root_key, recursive=False):
        return [key for key in self.keys if key.startswith(root_key)]

    def delete_file(self, bucket_name, key):
        self.deleted.append((bucket_name, key))

    def upload_file(self, source, bucket_name, key):
        self.uploads.append((source, bucket_name, key))

    def upload_string(self, payload, bucket_name, key):
        self.uploads.append((payload, bucket_name, key))

    def object_uri_by_key(self, bucket_name, key):
        return f"s3://{bucket_name}/{key}"

    def object_exists_by_key(self, bucket_name, key):
        return key in self.keys

    def join_object_key(self, *parts):
        return "/".join(str(part).strip("/") for part in parts)


class FakePySparker:
    def __init__(self):
        self.submitted = []
        self.deleted = []

    def submit(self, run_spec, *, dry_run=False):
        del dry_run
        self.submitted.append(run_spec)
        return SimpleNamespace(command=run_spec.job.command(), returncode=0)

    def delete(self, run_spec):
        self.deleted.append(run_spec)
        return ["deleted"]


class FakePaginator:
    def __init__(self, pages, client=None):
        self.pages = pages
        self.client = client

    def paginate(self, **kwargs):
        if self.client is not None:
            self.client.cluster_states = kwargs.get("ClusterStates")
        return self.pages


class FakeEMRClient:
    def __init__(self, *, clusters=None, bootstrap_actions=None, step_states=None, instances=None):
        self.added_steps = []
        self.clusters = clusters if clusters is not None else [{"Id": "j-demo", "Name": "demo-emr"}]
        self.bootstrap_actions = bootstrap_actions or {}
        self.step_states = list(step_states or ["COMPLETED"])
        self.instances = instances or []

    def list_clusters(self, ClusterStates):
        self.cluster_states = ClusterStates
        return {"Clusters": self.clusters}

    def get_paginator(self, name):
        assert name == "list_clusters"
        return FakePaginator([{"Clusters": self.clusters}], client=self)

    def add_job_flow_steps(self, JobFlowId, Steps):
        self.added_steps.append({"JobFlowId": JobFlowId, "Steps": Steps})
        return {"StepIds": ["s-demo"]}

    def list_bootstrap_actions(self, ClusterId):
        return {"BootstrapActions": self.bootstrap_actions.get(ClusterId, [])}

    def describe_step(self, ClusterId, StepId):
        del ClusterId, StepId
        if len(self.step_states) > 1:
            state = self.step_states.pop(0)
        else:
            state = self.step_states[0]
        return {"Step": {"Status": {"State": state}}}

    def list_instances(self, ClusterId, InstanceGroupTypes, InstanceStates):
        del ClusterId
        return {
            "Instances": [
                instance
                for instance in self.instances
                if instance.get("InstanceGroupType") in InstanceGroupTypes
                and instance.get("Status", {}).get("State") in InstanceStates
            ]
        }


def test_local_pysparker_plan_returns_spark_submit_command():
    conf = SimpleNamespace(
        pysparker=SimpleNamespace(runtime="local"),
        spark_home=None,
        java_home=None,
        pyspark_python=None,
    )
    job = PySparkJobSpec(
        name="job",
        entrypoint="main.py",
        master="local[*]",
        app_args=["--x", "1"],
    )
    pysparker = get_pysparker(conf)

    result = pysparker.plan(PySparkRunSpec(job=job))

    assert result.returncode == 0
    assert result.command == ["spark-submit", "--master", "local[*]", "main.py", "--x", "1"]


def test_local_pysparker_delete_cleans_configured_targets():
    conf = SimpleNamespace(
        pysparker=SimpleNamespace(runtime="local"),
        spark_home=None,
        java_home=None,
        pyspark_python=None,
    )
    bucketeer = FakeBucketeer()
    job = PySparkJobSpec(name="job", entrypoint="main.py")
    run_spec = PySparkRunSpec(
        job=job,
        cleanup_targets=[
            PySparkCleanupTarget(
                bucket="artifact-bucket",
                root_key="spark/python/job/version",
                label="job",
            )
        ],
    )
    pysparker = get_pysparker(conf, bucketeer=bucketeer)

    results = pysparker.delete(run_spec)

    assert len(results) == 1
    assert results[0].deleted is True
    assert len(results[0].matched_keys) == 2
    assert bucketeer.deleted == [
        ("artifact-bucket", "spark/python/job/version/main.py"),
        ("artifact-bucket", "spark/python/job/version/pkg.zip"),
    ]


def test_provider_pysparker_factory_returns_explicit_stubs():
    emr_conf = SimpleNamespace(
        aws_profile="",
        aws_region="us-east-2",
        cluster_id="j-demo",
        cluster_name="",
        cluster_states=["WAITING", "RUNNING"],
        action_on_failure="CONTINUE",
        wait_for_completion=False,
        wait_timeout_seconds=60,
        wait_poll_seconds=1,
    )
    conf = SimpleNamespace(
        pysparker=SimpleNamespace(runtime="local", emr=emr_conf),
        runtime_env="mac",
        aws_cred_role="role-a",
        aws_profile="profile-a",
        aws_zone="us-east-2",
        spark_home=None,
        java_home=None,
        pyspark_python=None,
    )

    assert isinstance(get_pysparker(conf, runtime="emr"), EMRPySparker)
    assert isinstance(get_pysparker(conf, runtime="dataproc"), DataprocPySparker)
    assert isinstance(get_pysparker(conf, runtime="azure_synapse"), AzureSynapsePySparker)
    assert isinstance(get_pysparker(conf, runtime="azure_hdinsight"), AzureHDInsightPySparker)
    assert isinstance(get_pysparker(conf, runtime="databricks"), DatabricksPySparker)


def test_apply_pysparker_runtime_tree_overlays_entire_configured_subtree():
    target_conf = ConfigFactory.parse_string(
        """
        binding_complex_scoring {
          spark {
            pysparker {
              runtime = "local"
              emr {
                action_on_failure = "CONTINUE"
                wait_for_completion = false
              }
            }
          }
        }
        """
    )
    runtime_conf = ConfigFactory.parse_string(
        """
        model_binding_spark {
          runtime = "emr"
          emr {
            aws_region = "us-east-2"
            aws_profile = "dev"
            cluster_name = "demo-emr"
            nested {
              keep_me = true
            }
          }
        }
        """
    ).model_binding_spark

    apply_pysparker_runtime_tree(
        target_conf,
        spark_ref_path=("binding_complex_scoring", "spark"),
        runtime_conf=runtime_conf,
    )

    pysparker_conf = target_conf.binding_complex_scoring.spark.pysparker
    assert pysparker_conf.runtime == "emr"
    assert pysparker_conf.emr.aws_region == "us-east-2"
    assert pysparker_conf.emr.aws_profile == "dev"
    assert pysparker_conf.emr.cluster_name == "demo-emr"
    assert pysparker_conf.emr.nested.keep_me is True
    assert pysparker_conf.emr.action_on_failure == "CONTINUE"


def test_apply_pysparker_runtime_tree_requires_selected_provider_subtree():
    runtime_conf = ConfigFactory.parse_string(
        """
        model_binding_spark {
          runtime = "emr"
        }
        """
    ).model_binding_spark

    with pytest.raises(ValueError, match="did not define \\[emr\\] config"):
        apply_pysparker_runtime_tree(
            ConfigFactory.parse_string("binding_complex_scoring.spark.pysparker.runtime = local"),
            spark_ref_path=("binding_complex_scoring", "spark"),
            runtime_conf=runtime_conf,
        )


def test_pyspark_artifact_job_internalizes_runtime_tree_overlay():
    target_conf = ConfigFactory.parse_string(
        """
        binding_complex_scoring.spark {
          pysparker {
            runtime = "local"
            emr {
              action_on_failure = "CONTINUE"
            }
          }
          jobs {
            score {
              name = "score"
            }
          }
        }
        """
    )
    runtime_conf = ConfigFactory.parse_string(
        """
        runtime = "emr"
        emr {
          cluster_name = "contract-emr"
        }
        """
    )

    PySparkArtifactJob(
        target_conf=target_conf,
        app_name="binding_complex_scoring",
        repo_root=SimpleNamespace(),
        spark_conf=target_conf.binding_complex_scoring.spark,
        job_key="score",
        bootstrap_ref_path=("binding_complex_scoring", "spark", "resolved_conf"),
        unique_name="demo",
        bucketeer=SimpleNamespace(),
        publish_resolved_conf=lambda **kwargs: kwargs,
        pysparker_runtime_conf=runtime_conf,
    )

    pysparker_conf = target_conf.binding_complex_scoring.spark.pysparker
    assert pysparker_conf.runtime == "emr"
    assert pysparker_conf.emr.cluster_name == "contract-emr"
    assert pysparker_conf.emr.action_on_failure == "CONTINUE"


def test_pyspark_artifact_job_can_use_artifactory_without_resolved_conf(tmp_path):
    (tmp_path / "main.py").write_text("print('ok')\n")
    (tmp_path / "conf").mkdir()
    (tmp_path / "conf" / "project.conf").write_text("project = demo\n")
    mode_archive = tmp_path / "mode-files.zip"
    mode_archive.write_text("zip-ish")
    target_conf = ConfigFactory.parse_string(
        """
        git.commit = "abcdef1234567890"
        mmseqs_sequence_alignment {
          search_harmonization {
            spark {
              artifacts {
                bucket = "artifacts"
                root_key = "spark/python"
                version = "local"
              }
              jobs {
                harmonize {
                  name = "harmonize"
                  entrypoint = "main.py"
                  entrypoint_artifact_name = "main.py"
                  master = "yarn"
                  deploy_mode = "cluster"
                  py_files = []
                  files = []
                  archives = []
                  archive_sources = [
                    {
                      name = "project_conf"
                      source = "conf"
                      artifact_name = "project-conf.zip"
                      alias = "project"
                      artifact_kind = "zip"
                    }
                  ]
                  packages = []
                  spark_conf = {}
                  app_args = []
                  py_file_sources = []
                }
              }
            }
          }
        }
        """
    )
    fake_bucketeer = FakeBucketeer()
    artifact_job = PySparkArtifactJob(
        target_conf=target_conf,
        app_name="mmseqs_sequence_alignment",
        repo_root=tmp_path,
        spark_conf=target_conf.mmseqs_sequence_alignment.search_harmonization.spark,
        job_key="harmonize",
        bootstrap_ref_path=(),
        unique_name="demo",
        bucketeer=fake_bucketeer,
        publish_resolved_conf=None,
    )

    artifacts = artifact_job.prepare_artifacts(
        write=True,
        archive_sources=[
            PythonArchiveSource(
                name="mode_files",
                source=mode_archive.as_posix(),
                artifact_name=mode_archive.name,
                alias="context_conf",
            )
        ],
    )
    run_spec = artifact_job.run_spec(artifacts, app_args=["-es", "aws_runtime", "-w", "run"])

    assert artifacts.conf_publication == {}
    assert artifacts.archives == [
        "s3://artifacts/spark/python/harmonize/demo--abcdef12/archives/project-conf.zip#project",
        "s3://artifacts/spark/python/harmonize/demo--abcdef12/archives/mode-files.zip#context_conf"
    ]
    assert run_spec.job.command() == [
        "spark-submit",
        "--master",
        "yarn",
        "--deploy-mode",
        "cluster",
        "--archives",
        (
            "s3://artifacts/spark/python/harmonize/demo--abcdef12/archives/project-conf.zip#project,"
            "s3://artifacts/spark/python/harmonize/demo--abcdef12/archives/mode-files.zip#context_conf"
        ),
        "s3://artifacts/spark/python/harmonize/demo--abcdef12/main.py",
        "-es",
        "aws_runtime",
        "-w",
        "run",
    ]
    assert "--bootstrap-conf-file" not in run_spec.job.command()


def test_pyspark_artifact_job_reuses_existing_artifactory_bundle_without_upload(tmp_path):
    (tmp_path / "main.py").write_text("print('ok')\n")
    (tmp_path / "conf").mkdir()
    (tmp_path / "conf" / "project.conf").write_text("project = demo\n")
    mode_archive = tmp_path / "mode-files.zip"
    mode_archive.write_text("zip-ish")
    target_conf = ConfigFactory.parse_string(
        """
        git.commit = "abcdef1234567890"
        mmseqs_sequence_alignment {
          search_harmonization {
            spark {
              artifacts {
                bucket = "artifacts"
                root_key = "spark/python"
                version = "local"
              }
              jobs {
                harmonize {
                  name = "harmonize"
                  entrypoint = "main.py"
                  entrypoint_artifact_name = "main.py"
                  master = "yarn"
                  deploy_mode = "cluster"
                  py_files = []
                  files = []
                  archives = []
                  archive_sources = [
                    {
                      name = "project_conf"
                      source = "conf"
                      artifact_name = "project-conf.zip"
                      alias = "project"
                      artifact_kind = "zip"
                    }
                  ]
                  packages = []
                  spark_conf = {}
                  app_args = []
                  py_file_sources = []
                }
              }
            }
          }
        }
        """
    )
    fake_bucketeer = FakeBucketeer()
    fake_bucketeer.keys = [
        "spark/python/harmonize/demo--abcdef12/main.py",
        "spark/python/harmonize/demo--abcdef12/archives/project-conf.zip",
        "spark/python/harmonize/demo--abcdef12/archives/mode-files.zip",
        "spark/python/harmonize/demo--abcdef12/manifest.json",
    ]
    artifact_job = PySparkArtifactJob(
        target_conf=target_conf,
        app_name="mmseqs_sequence_alignment",
        repo_root=tmp_path,
        spark_conf=target_conf.mmseqs_sequence_alignment.search_harmonization.spark,
        job_key="harmonize",
        bootstrap_ref_path=(),
        unique_name="demo",
        bucketeer=fake_bucketeer,
        publish_resolved_conf=None,
    )

    artifacts = artifact_job.prepare_artifacts(
        write=True,
        archive_sources=[
            PythonArchiveSource(
                name="mode_files",
                source=mode_archive.as_posix(),
                artifact_name=mode_archive.name,
                alias="context_conf",
            )
        ],
    )
    run_spec = artifact_job.run_spec(artifacts, app_args=["-es", "aws_runtime", "-w", "run"])

    assert fake_bucketeer.uploads == []
    assert artifacts.manifest_uri == "s3://artifacts/spark/python/harmonize/demo--abcdef12/manifest.json"
    assert artifacts.archives == [
        "s3://artifacts/spark/python/harmonize/demo--abcdef12/archives/project-conf.zip#project",
        "s3://artifacts/spark/python/harmonize/demo--abcdef12/archives/mode-files.zip#context_conf",
    ]
    assert run_spec.job.command() == [
        "spark-submit",
        "--master",
        "yarn",
        "--deploy-mode",
        "cluster",
        "--archives",
        (
            "s3://artifacts/spark/python/harmonize/demo--abcdef12/archives/project-conf.zip#project,"
            "s3://artifacts/spark/python/harmonize/demo--abcdef12/archives/mode-files.zip#context_conf"
        ),
        "s3://artifacts/spark/python/harmonize/demo--abcdef12/main.py",
        "-es",
        "aws_runtime",
        "-w",
        "run",
    ]


def test_pyspark_artifact_job_force_write_republishes_existing_bundle(tmp_path):
    (tmp_path / "main.py").write_text("print('ok')\n")
    target_conf = ConfigFactory.parse_string(
        """
        git.commit = "abcdef1234567890"
        demo {
          spark {
            artifacts {
              bucket = "artifacts"
              root_key = "spark/python"
              version = "local"
            }
            jobs {
              job {
                name = "job"
                entrypoint = "main.py"
                entrypoint_artifact_name = "main.py"
                master = "local[*]"
                deploy_mode = null
                py_files = []
                files = []
                archives = []
                archive_sources = []
                packages = []
                spark_conf = {}
                app_args = []
                py_file_sources = []
              }
            }
          }
        }
        """
    )
    fake_bucketeer = FakeBucketeer()
    fake_bucketeer.keys = [
        "spark/python/job/demo--abcdef12/main.py",
        "spark/python/job/demo--abcdef12/manifest.json",
    ]
    artifact_job = PySparkArtifactJob(
        target_conf=target_conf,
        app_name="demo",
        repo_root=tmp_path,
        spark_conf=target_conf.demo.spark,
        job_key="job",
        bootstrap_ref_path=(),
        unique_name="demo",
        bucketeer=fake_bucketeer,
        publish_resolved_conf=None,
    )

    artifact_job.prepare_artifacts(write=True, force_write=True)

    assert len(fake_bucketeer.uploads) == 2


def test_emr_pysparker_submits_spark_command_as_emr_step():
    emr_client = FakeEMRClient()
    conf = SimpleNamespace(
        aws_profile="",
        aws_region="us-east-2",
        cluster_id="",
        cluster_name="demo-emr",
        cluster_states=["WAITING", "RUNNING"],
        action_on_failure="CONTINUE",
        wait_for_completion=False,
        wait_timeout_seconds=60,
        wait_poll_seconds=1,
    )
    pysparker = EMRPySparker(emr_conf=conf, emr_client=emr_client)
    run_spec = PySparkRunSpec(
        job=PySparkJobSpec(
            name="score",
            entrypoint="s3://artifact/run.py",
            master="yarn",
            deploy_mode="cluster",
            py_files=["s3://artifact/pkg.zip"],
            app_args=["--bootstrap-conf-file", "s3://conf/bootstrap.conf"],
        )
    )

    result = pysparker.submit(run_spec)

    assert result.returncode == 0
    assert emr_client.added_steps[0]["JobFlowId"] == "j-demo"
    step = emr_client.added_steps[0]["Steps"][0]
    assert step["Name"] == "score"
    assert step["HadoopJarStep"]["Jar"] == "command-runner.jar"
    assert step["HadoopJarStep"]["Args"] == [
        "spark-submit",
        "--master",
        "yarn",
        "--deploy-mode",
        "cluster",
        "--py-files",
        "s3://artifact/pkg.zip",
        "--conf",
        "spark.pyspark.python=/usr/bin/python3.11",
        "--conf",
        "spark.pyspark.driver.python=/usr/bin/python3.11",
        "--conf",
        "spark.yarn.appMasterEnv.HOME=/home/hadoop",
        "--conf",
        "spark.yarn.appMasterEnv.PYTHONPATH=/home/hadoop/.local/wielder-python-runtime",
        "--conf",
        "spark.yarn.appMasterEnv.PYTHONUSERBASE=/home/hadoop/.local",
        "--conf",
        "spark.yarn.appMasterEnv.PYSPARK_PYTHON=/usr/bin/python3.11",
        "--conf",
        "spark.yarn.appMasterEnv.GIT_PYTHON_REFRESH=quiet",
        "--conf",
        "spark.yarn.appMasterEnv.WIELDER_STAGE_ROOT=/tmp/wielder-stage/culture",
        "--conf",
        "spark.yarn.appMasterEnv.WIELDER_SKIP_GIT_SNAPSHOT=true",
        "--conf",
        "spark.executorEnv.HOME=/home/hadoop",
        "--conf",
        "spark.executorEnv.PYTHONPATH=/home/hadoop/.local/wielder-python-runtime",
        "--conf",
        "spark.executorEnv.PYTHONUSERBASE=/home/hadoop/.local",
        "--conf",
        "spark.executorEnv.PYSPARK_PYTHON=/usr/bin/python3.11",
        "--conf",
        "spark.executorEnv.GIT_PYTHON_REFRESH=quiet",
        "--conf",
        "spark.executorEnv.WIELDER_STAGE_ROOT=/tmp/wielder-stage/culture",
        "--conf",
        "spark.executorEnv.WIELDER_SKIP_GIT_SNAPSHOT=true",
        "s3://artifact/run.py",
        "--bootstrap-conf-file",
        "s3://conf/bootstrap.conf",
    ]


def test_emr_pysparker_exports_configured_job_log_env_to_emr_step():
    emr_client = FakeEMRClient()
    conf = SimpleNamespace(
        aws_profile="",
        aws_region="us-east-2",
        cluster_id="j-demo",
        cluster_name="",
        cluster_states=["WAITING", "RUNNING"],
        action_on_failure="CONTINUE",
        wait_for_completion=False,
        wait_timeout_seconds=60,
        wait_poll_seconds=1,
        job_log=SimpleNamespace(
            enabled=True,
            level="debug",
            format="%(levelname)s:%(message)s",
            datefmt="%H:%M:%S",
        ),
    )
    pysparker = EMRPySparker(emr_conf=conf, emr_client=emr_client)
    run_spec = PySparkRunSpec(
        job=PySparkJobSpec(
            name="score",
            entrypoint="s3://artifact/run.py",
            master="yarn",
            deploy_mode="cluster",
        )
    )

    pysparker.submit(run_spec)

    command = emr_client.added_steps[0]["Steps"][0]["HadoopJarStep"]["Args"]
    assert "spark.yarn.appMasterEnv.PYTHONUNBUFFERED=1" in command
    assert "spark.executorEnv.PYTHONUNBUFFERED=1" in command
    assert "spark.yarn.appMasterEnv.WIELDER_PYSPARK_JOB_LOG_LEVEL=debug" in command
    assert "spark.executorEnv.WIELDER_PYSPARK_JOB_LOG_LEVEL=debug" in command
    assert "spark.yarn.appMasterEnv.WIELDER_PYSPARK_JOB_LOG_FORMAT=%(levelname)s:%(message)s" in command
    assert "spark.executorEnv.WIELDER_PYSPARK_JOB_LOG_DATEFMT=%H:%M:%S" in command


def test_configure_pyspark_job_logging_uses_configured_policy(monkeypatch):
    basic_config_calls = []
    capture_warnings_calls = []
    monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: basic_config_calls.append(kwargs))
    monkeypatch.setattr(logging, "captureWarnings", lambda enabled: capture_warnings_calls.append(enabled))
    conf = SimpleNamespace(
        job_log=SimpleNamespace(
            enabled=True,
            level="debug",
            format="%(message)s",
            datefmt="%H:%M",
            force=False,
            capture_warnings=False,
            emit_startup_summary=False,
            loggers={"py4j": "error"},
        )
    )

    logger = configure_pyspark_job_logging(conf, logger_name="demo.spark")

    assert logger.name == "demo.spark"
    assert basic_config_calls == [
        {
            "level": logging.DEBUG,
            "format": "%(message)s",
            "datefmt": "%H:%M",
            "force": False,
        }
    ]
    assert capture_warnings_calls == [False]
    assert logging.getLogger("py4j").level == logging.ERROR


def test_emr_pysparker_wait_logs_every_poll_without_policy(caplog):
    caplog.set_level(logging.INFO)
    emr_client = FakeEMRClient(step_states=["RUNNING", "RUNNING", "COMPLETED"])
    conf = SimpleNamespace(
        wait_timeout_seconds=60,
        wait_poll_seconds=0,
    )
    pysparker = EMRPySparker(emr_conf=conf, emr_client=emr_client)

    pysparker._wait_for_steps("j-demo", ["s-demo"])

    messages = [record.message for record in caplog.records if "EMR step [s-demo]" in record.message]
    assert messages == [
        "EMR step [s-demo] state [RUNNING].",
        "EMR step [s-demo] state [RUNNING].",
        "EMR step [s-demo] state [COMPLETED].",
    ]


def test_emr_pysparker_wait_log_policy_suppresses_repeated_same_state(caplog):
    caplog.set_level(logging.INFO)
    emr_client = FakeEMRClient(step_states=["RUNNING", "RUNNING", "RUNNING", "COMPLETED"])
    conf = SimpleNamespace(
        wait_timeout_seconds=60,
        wait_poll_seconds=0,
        wait_log=SimpleNamespace(
            enabled=True,
            log_every_poll=False,
            log_initial_state=True,
            log_state_changes=True,
            repeated_state_log_seconds=999,
            include_elapsed=True,
            level="info",
        ),
    )
    pysparker = EMRPySparker(emr_conf=conf, emr_client=emr_client)

    pysparker._wait_for_steps("j-demo", ["s-demo"])

    messages = [record.message for record in caplog.records if "EMR step [s-demo]" in record.message]
    assert len(messages) == 2
    assert messages[0].startswith("EMR step [s-demo] state [RUNNING] (elapsed ")
    assert messages[1].startswith("EMR step [s-demo] state [COMPLETED] (elapsed ")


def test_emr_pysparker_derives_executor_count_from_cluster_workers():
    emr_client = FakeEMRClient(
        instances=[
            {"InstanceGroupType": "MASTER", "Status": {"State": "RUNNING"}},
            {"InstanceGroupType": "CORE", "Status": {"State": "RUNNING"}},
            {"InstanceGroupType": "CORE", "Status": {"State": "RUNNING"}},
            {"InstanceGroupType": "TASK", "Status": {"State": "RUNNING"}},
            {"InstanceGroupType": "TASK", "Status": {"State": "TERMINATED"}},
        ],
    )
    conf = SimpleNamespace(
        aws_profile="",
        aws_region="us-east-2",
        cluster_id="j-demo",
        cluster_name="",
        cluster_states=["WAITING", "RUNNING"],
        action_on_failure="CONTINUE",
        wait_for_completion=False,
        wait_timeout_seconds=60,
        wait_poll_seconds=1,
        resource_profile=SimpleNamespace(
            enabled=True,
            derive_executor_instances_from_cluster=True,
            worker_group_types=["CORE", "TASK"],
            worker_states=["RUNNING"],
            reserve_workers=1,
            executor_worker_fraction=1.0,
            executor_instances_per_worker=1,
            min_executor_instances=1,
            max_executor_instances=2,
            dynamic_allocation_enabled=False,
            executor_cores=1,
            executor_memory="2g",
            executor_memory_overhead="512m",
            driver_memory="2g",
            set_only_if_missing=True,
        ),
    )
    pysparker = EMRPySparker(emr_conf=conf, emr_client=emr_client)
    run_spec = PySparkRunSpec(job=PySparkJobSpec(name="score", entrypoint="s3://artifact/run.py"))

    pysparker.submit(run_spec)

    command = emr_client.added_steps[0]["Steps"][0]["HadoopJarStep"]["Args"]
    assert "--conf" in command
    assert "spark.dynamicAllocation.enabled=false" in command
    assert "spark.executor.instances=2" in command
    assert "spark.executor.cores=1" in command
    assert "spark.executor.memory=2g" in command
    assert "spark.executor.memoryOverhead=512m" in command
    assert "spark.driver.memory=2g" in command


def test_emr_pysparker_inspects_latest_cluster_bootstrap_action_args():
    emr_client = FakeEMRClient(
        clusters=[
            {
                "Id": "j-old",
                "Name": "demo-emr",
                "Status": {"Timeline": {"CreationDateTime": 1}},
            },
            {
                "Id": "j-new",
                "Name": "demo-emr",
                "Status": {"Timeline": {"CreationDateTime": 2}},
            },
        ],
        bootstrap_actions={
            "j-new": [
                {
                    "Name": EMRPySparker.PYTHON_RUNTIME_BOOTSTRAP_ACTION_NAME,
                    "ScriptBootstrapAction": {
                        "Args": ["pydantic>=2.9.2,<3", "pyhocon>=0.3.60"],
                    },
                }
            ],
        },
    )
    conf = SimpleNamespace(
        aws_profile="",
        aws_region="us-east-2",
    )
    pysparker = EMRPySparker(emr_conf=conf, emr_client=emr_client)

    assert pysparker.latest_cluster_bootstrap_action_args("demo-emr") == (
        "j-new",
        ["pydantic>=2.9.2,<3", "pyhocon>=0.3.60"],
    )
    assert emr_client.cluster_states == list(EMRPySparker.ACTIVE_CLUSTER_STATES)


def test_emr_pysparker_uses_wielder_aws_session_for_workstation_bootstrap(monkeypatch):
    calls = []

    class FakeSession:
        def client(self, service_name):
            calls.append(("client", service_name))
            return "emr-client"

    monkeypatch.setattr(
        pysparker_module,
        "get_aws_session",
        lambda conf: calls.append(
            (
                "get_aws_session",
                conf.aws_cred_role,
                conf.aws_profile,
                conf.aws_zone,
            )
        )
        or FakeSession(),
    )

    conf = SimpleNamespace(
        aws_region="us-east-2",
    )
    auth_conf = SimpleNamespace(
        runtime_env="mac",
        aws_cred_role="role-a",
        aws_profile="profile-a",
        aws_zone="us-east-2",
    )
    pysparker = EMRPySparker(emr_conf=conf, auth_conf=auth_conf)

    assert pysparker.emr_client == "emr-client"
    assert calls == [
        ("get_aws_session", "role-a", "profile-a", "us-east-2"),
        ("client", "emr"),
    ]


def test_emr_pysparker_uses_plain_boto3_session_on_aws(monkeypatch):
    calls = []

    class FakeSession:
        def __init__(self, **kwargs):
            calls.append(("Session", kwargs))

        def client(self, service_name):
            calls.append(("client", service_name))
            return "emr-client"

    monkeypatch.setattr(boto3, "Session", FakeSession)

    conf = SimpleNamespace(
        aws_profile="ignored",
        aws_region="us-east-2",
    )
    auth_conf = SimpleNamespace(
        runtime_env="aws",
        aws_profile="ignored",
        aws_region="us-east-2",
    )
    pysparker = EMRPySparker(emr_conf=conf, auth_conf=auth_conf)

    assert pysparker.emr_client == "emr-client"
    assert calls == [
        ("Session", {"region_name": "us-east-2"}),
        ("client", "emr"),
    ]


def test_pyspark_job_spec_from_conf_accepts_runtime_artifact_overrides():
    job_conf = SimpleNamespace(
        name="job",
        entrypoint="source.py",
        master="local[*]",
        deploy_mode=None,
        py_files=["configured.zip"],
        files=["configured.conf"],
        archives=[],
        packages=[],
        spark_conf={"spark.demo": "yes"},
        app_args=["--configured"],
    )

    job = pyspark_job_spec_from_conf(
        job_conf,
        entrypoint="artifact://main.py",
        py_files=["artifact://pkg.zip"],
        extra_files=["bootstrap.conf"],
        app_args=["--bootstrap-conf-file", "bootstrap.conf"],
    )

    assert job.entrypoint == "artifact://main.py"
    assert job.py_files == ["artifact://pkg.zip"]
    assert job.files == ["configured.conf", "bootstrap.conf"]
    assert job.app_args == ["--bootstrap-conf-file", "bootstrap.conf"]
    assert job.command() == [
        "spark-submit",
        "--master",
        "local[*]",
        "--py-files",
        "artifact://pkg.zip",
        "--files",
        "configured.conf,bootstrap.conf",
        "--conf",
        "spark.demo=yes",
        "artifact://main.py",
        "--bootstrap-conf-file",
        "bootstrap.conf",
    ]


def test_bootstrap_conf_helpers_use_remote_file_ref_and_localized_name():
    artifacts = WieldedPythonArtifacts(
        conf_publication={
            "bootstrap_staged_file": "/tmp/workspace/bootstrap--demo.conf",
            "bootstrap_staged_name": "bootstrap--demo.conf",
            "bootstrap_file_ref": "s3://conf-bucket/resolved_conf/dev/demo/bootstrap--demo.conf#bootstrap--demo.conf",
        },
        entrypoint="main.py",
        py_files=[],
        archives=[],
        manifest_uri="<not-published>",
        cleanup_targets=[],
    )
    job_conf = SimpleNamespace(files=["extra.conf"])

    assert bootstrap_conf_app_args(artifacts) == [
        "--bootstrap-conf-file",
        "bootstrap--demo.conf",
    ]
    assert bootstrap_conf_files(artifacts, job_conf) == [
        "s3://conf-bucket/resolved_conf/dev/demo/bootstrap--demo.conf#bootstrap--demo.conf",
        "extra.conf",
    ]


def test_pyspark_wield_action_runner_owns_submit_and_delete_decisions():
    actions_conf = SimpleNamespace(submit_on_apply=True, submit_on_run=False)
    job = PySparkJobSpec(name="job", entrypoint="main.py")
    run_spec = PySparkRunSpec(job=job)
    pysparker = FakePySparker()

    assert should_submit_pyspark_action(WieldAction.APPLY, actions_conf) is True
    result = wield(
        pysparker=pysparker,
        run_spec=run_spec,
        action=WieldAction.APPLY,
        actions_conf=actions_conf,
        delete_artifacts_on_delete=True,
    )
    assert result.submitted is True
    assert len(pysparker.submitted) == 1

    delete_result = wield(
        pysparker=pysparker,
        run_spec=run_spec,
        action=WieldAction.DELETE,
        actions_conf=actions_conf,
        delete_artifacts_on_delete=True,
    )
    assert delete_result.submitted is False
    assert delete_result.cleanup_results == ["deleted"]
    assert len(pysparker.deleted) == 1
