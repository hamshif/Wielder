import json
import pytest
import time
from datetime import UTC, datetime
from pydantic import ValidationError

from wielder.util.wjobbard import (
    AWSJobBard,
    GCPJobBard,
    WJobBard,
    WJobBardJob,
    WJobBardLifecycleStatus,
    WJobBardLocalMonitor,
    WJobBardProvider,
    WJobBardRuntime,
    WJobBardRuntimeConfigmap,
    WJobBardSecretEnv,
    WJobBardSpec,
    WJobBardTargetKind,
    WJobBardTrigger,
    WJobBardTriggerType,
    WJobBardWorkflow,
    WJobBardWorkflowMode,
    wjobbard_tfvars_context,
    wjobbard_tfvars_context_from_conf,
)
from wielder.wield.enumerator import WieldAction


@pytest.mark.parametrize(
    ("provider", "expected_class"),
    [
        (WJobBardProvider.GCP, GCPJobBard),
        (WJobBardProvider.AWS, AWSJobBard),
    ],
)
def test_wjobbard_factory_returns_provider_implementation(provider, expected_class):
    bard = WJobBard.from_spec(
        WJobBardSpec(
            provider=provider,
            action=WieldAction.PLAN,
            scope="gcp_ops/wjobbard",
            stage_tier="dev",
        )
    )

    assert isinstance(bard, expected_class)
    assert bard.provider == provider


def test_wjobbard_cron_trigger_requires_schedule():
    with pytest.raises(ValidationError, match="requires schedule"):
        WJobBardTrigger(key="nightly", trigger_type=WJobBardTriggerType.CRON)


def test_wjobbard_event_trigger_requires_topic_ref():
    with pytest.raises(ValidationError, match="requires topic_ref"):
        WJobBardTrigger(key="requested", trigger_type=WJobBardTriggerType.EVENT)


def test_wjobbard_job_identity_is_scoped_by_config_tree():
    job = _wclone_job()

    assert job.scoped_identity("gcp_ops/wjobbard") == "gcp_ops/wjobbard/provider_drive_to_gcs"


def test_wjobbard_job_plan_pretty_dumps_typed_config():
    record = _wclone_job().plan_record("gcp_ops/wjobbard")

    assert record["job_id"] == "gcp_ops/wjobbard/provider_drive_to_gcs"
    assert record["triggers"]["nightly"]["schedule"] == "0 2 * * *"
    assert record["triggers"]["requested"]["topic_ref"] == "example-provider-raw-ingestion-dev"
    assert record["output_event_types"] == ["raw_mirror.completed"]
    assert record["lifecycle_topic_ref"] == "example-wjobbard-lifecycle-dev"


def test_wjobbard_spec_accepts_empty_event_lists_and_loci():
    spec = WJobBardSpec(
        provider=WJobBardProvider.GCP,
        action=WieldAction.PLAN,
        scope="gcp_ops/wjobbard",
        stage_tier="dev",
        jobs={"provider_drive_to_gcs": _wclone_job(input_event_types=[], output_event_types=[])},
    )

    job = spec.jobs["provider_drive_to_gcs"]

    assert job.kind == WJobBardTargetKind.WCLONER
    assert job.src == "gcp_ops.bucket_migration.storage_loci.provider.drive"
    assert job.sink == "gcp_ops.bucket_migration.storage_loci.provider.gcs"
    assert job.input_event_types == []
    assert job.output_event_types == []


def test_wjobbard_job_accepts_hosted_runtime_contract():
    job = _wclone_job(runtime=_hosted_runtime())

    assert job.runtime.name == "example-provider-wclone-dev"
    assert job.runtime.secret_env[0].version == "latest"


def test_wjobbard_runtime_from_conf_normalizes_hocon_like_runtime():
    runtime = WJobBardRuntime.from_conf(
        {
            "name": "example-provider-wclone-dev",
            "image": "us-central1-docker.pkg.dev/example-dev/example/wclone_job_runner:dev",
            "service_account_email": (
                "example-wclone-daemon-dev@example-dev.iam.gserviceaccount.com"
            ),
            "command": ["python"],
            "args": ["-m", "example_wielder.deploy.apps.gcp_ops.wield.gcp_ops_bucket_migration"],
            "env": {
                "WJOBBARD_JOB_KEY": "provider_drive_to_gcs",
                "RETRY_COUNT": 3,
            },
            "secret_env": [
                {
                    "name": "AWS_ACCESS_KEY_ID",
                    "secret": "wclone-aws-source-access-key-id-dev",
                }
            ],
        }
    )

    assert runtime.command == ["python"]
    assert runtime.args == ["-m", "example_wielder.deploy.apps.gcp_ops.wield.gcp_ops_bucket_migration"]
    assert runtime.env["RETRY_COUNT"] == "3"
    assert runtime.secret_env[0].name == "AWS_ACCESS_KEY_ID"


def test_wjobbard_workflow_references_configured_jobs():
    spec = WJobBardSpec(
        provider=WJobBardProvider.GCP,
        action=WieldAction.PLAN,
        scope="gcp_ops/wjobbard",
        stage_tier="dev",
        jobs={"provider_drive_to_gcs": _wclone_job()},
        workflows={
            "cro_raw_mirror": WJobBardWorkflow(
                key="cro_raw_mirror",
                mode=WJobBardWorkflowMode.ORDERED,
                job_keys=["provider_drive_to_gcs"],
            )
        },
        selected_workflows=["cro_raw_mirror"],
    )

    assert spec.effective_job_keys == ["provider_drive_to_gcs"]
    assert spec.effective_workflow_keys == ["cro_raw_mirror"]
    assert spec.effective_run_groups == [
        (WJobBardWorkflowMode.ORDERED, ["provider_drive_to_gcs"], "cro_raw_mirror")
    ]


def test_wjobbard_workflow_run_jobs_can_be_narrower_than_provisioned_jobs():
    spec = WJobBardSpec(
        provider=WJobBardProvider.GCP,
        action=WieldAction.RUN,
        scope="gcp_ops/wjobbard",
        stage_tier="dev",
        jobs={
            "source": _wclone_job_named("source", "example-source-wclone-dev"),
            "fanout": _wclone_job_named("fanout", "example-fanout-wclone-dev"),
        },
        workflows={
            "cro_raw_mirror": WJobBardWorkflow(
                key="cro_raw_mirror",
                mode=WJobBardWorkflowMode.PARALLEL,
                job_keys=["source", "fanout"],
                run_job_keys=["source"],
            )
        },
        selected_workflows=["cro_raw_mirror"],
    )

    assert spec.effective_job_keys == ["source", "fanout"]
    assert spec.effective_run_groups == [
        (WJobBardWorkflowMode.PARALLEL, ["source"], "cro_raw_mirror")
    ]


def test_wjobbard_workflow_rejects_unknown_jobs():
    with pytest.raises(ValidationError, match="references unknown jobs"):
        WJobBardSpec(
            provider=WJobBardProvider.GCP,
            action=WieldAction.PLAN,
            scope="gcp_ops/wjobbard",
            stage_tier="dev",
            jobs={},
            workflows={
                "cro_raw_mirror": WJobBardWorkflow(
                    key="cro_raw_mirror",
                    mode=WJobBardWorkflowMode.PARALLEL,
                    job_keys=["missing_job"],
                )
            },
        )


def test_wjobbard_workflow_rejects_unknown_run_jobs():
    with pytest.raises(ValidationError, match="references unknown run jobs"):
        WJobBardSpec(
            provider=WJobBardProvider.GCP,
            action=WieldAction.PLAN,
            scope="gcp_ops/wjobbard",
            stage_tier="dev",
            jobs={"source": _wclone_job_named("source", "example-source-wclone-dev")},
            workflows={
                "cro_raw_mirror": WJobBardWorkflow(
                    key="cro_raw_mirror",
                    mode=WJobBardWorkflowMode.PARALLEL,
                    job_keys=["source"],
                    run_job_keys=["missing_run_job"],
                )
            },
        )


def test_wjobbard_rejects_duplicate_runtime_names():
    with pytest.raises(ValidationError, match="Runtime names define provider idempotency"):
        WJobBardSpec(
            provider=WJobBardProvider.GCP,
            action=WieldAction.RUN,
            scope="gcp_ops/wjobbard",
            stage_tier="dev",
            jobs={
                "partner_gcp_to_aws": _wclone_job_named("partner_gcp_to_aws", "example-raw-mirror-dev"),
                "provider_drive_to_aws": _wclone_job_named("provider_drive_to_aws", "example-raw-mirror-dev"),
            },
        )


def test_wjobbard_plan_contains_jobs_workflows_and_lifecycle_envelopes():
    spec = WJobBardSpec(
        provider=WJobBardProvider.GCP,
        action=WieldAction.PLAN,
        scope="gcp_ops/wjobbard",
        stage_tier="dev",
        jobs={"provider_drive_to_gcs": _wclone_job()},
        workflows={
            "cro_raw_mirror": WJobBardWorkflow(
                key="cro_raw_mirror",
                mode=WJobBardWorkflowMode.PARALLEL,
                job_keys=["provider_drive_to_gcs"],
            )
        },
    )

    plan = WJobBard.from_spec(spec).plan()

    assert plan["jobs"]["provider_drive_to_gcs"]["job_id"] == "gcp_ops/wjobbard/provider_drive_to_gcs"
    assert plan["jobs"]["provider_drive_to_gcs"]["kind"] == "wcloner"
    assert plan["jobs"]["provider_drive_to_gcs"]["src"] == "gcp_ops.bucket_migration.storage_loci.provider.drive"
    assert plan["jobs"]["provider_drive_to_gcs"]["sink"] == "gcp_ops.bucket_migration.storage_loci.provider.gcs"
    assert plan["workflows"][0]["mode"] == "parallel"
    assert plan["lifecycle_envelopes"][0]["status"] == WJobBardLifecycleStatus.PLANNED.value
    assert plan["local_monitor"]["execution_limit"] == 5


def test_gcp_wjobbard_local_monitor_builds_cloud_run_execution_command():
    spec = WJobBardSpec(
        provider=WJobBardProvider.GCP,
        action=WieldAction.PLAN,
        scope="gcp_ops/wjobbard",
        stage_tier="dev",
        local_monitor=WJobBardLocalMonitor(
            project_id="example-dev",
            region="us-central1",
            execution_limit=3,
        ),
        jobs={"provider_drive_to_gcs": _wclone_job(runtime=_hosted_runtime())},
    )

    records = WJobBard.from_spec(spec).local_monitor(execute=False)

    assert records == [
        {
            "job_key": "provider_drive_to_gcs",
            "job_name": "example-provider-wclone-dev",
            "project_id": "example-dev",
            "region": "us-central1",
            "command": [
                "gcloud",
                "run",
                "jobs",
                "executions",
                "list",
                "--job=example-provider-wclone-dev",
                "--region=us-central1",
                "--project=example-dev",
                "--limit=3",
                "--format=table(name,completionTime,state)",
            ],
        }
    ]


def test_gcp_wjobbard_job_execution_after_filters_recent_cloud_run_executions(monkeypatch):
    spec = WJobBardSpec(
        provider=WJobBardProvider.GCP,
        action=WieldAction.MONITOR,
        scope="gcp_ops/wjobbard",
        stage_tier="dev",
        local_monitor=WJobBardLocalMonitor(
            project_id="example-dev",
            region="us-central1",
            execution_limit=3,
        ),
        jobs={"provider_drive_to_gcs": _wclone_job(runtime=_hosted_runtime())},
    )
    bard = WJobBard.from_spec(spec)

    def fake_run_monitor_command(command, timeout, label, **_kwargs):
        return {
            "command": command,
            "returncode": 0,
            "stdout": json.dumps(
                [
                    {"metadata": {"creationTimestamp": "2026-05-16T11:59:00Z"}, "name": "old"},
                    {"metadata": {"creationTimestamp": "2026-05-16T12:00:01Z"}, "name": "recent"},
                ]
            ),
            "stderr": "",
        }

    monkeypatch.setattr(bard, "_run_monitor_command", fake_run_monitor_command)

    record = bard.job_execution_after(
        "provider_drive_to_gcs",
        started_at=datetime(2026, 5, 16, 12, 0, tzinfo=UTC),
    )

    assert record["job_key"] == "provider_drive_to_gcs"
    assert record["job_name"] == "example-provider-wclone-dev"
    assert record["executions"] == [
        {"metadata": {"creationTimestamp": "2026-05-16T12:00:01Z"}, "name": "recent"}
    ]
    assert record["command"] == [
        "gcloud",
        "run",
        "jobs",
        "executions",
        "list",
        "--job=example-provider-wclone-dev",
        "--region=us-central1",
        "--project=example-dev",
        "--limit=3",
        "--format=json",
    ]


def test_gcp_wjobbard_job_execution_log_evidence_after_reads_execution_logs(monkeypatch):
    spec = WJobBardSpec(
        provider=WJobBardProvider.GCP,
        action=WieldAction.MONITOR,
        scope="gcp_ops/wjobbard",
        stage_tier="dev",
        local_monitor=WJobBardLocalMonitor(
            project_id="example-dev",
            region="us-central1",
            execution_limit=3,
        ),
        jobs={"provider_drive_to_gcs": _wclone_job(runtime=_hosted_runtime())},
    )
    bard = WJobBard.from_spec(spec)
    commands = []

    def fake_run_monitor_command(command, timeout, label, **_kwargs):
        commands.append(command)
        if command[:4] == ["gcloud", "run", "jobs", "executions"]:
            return {
                "command": command,
                "returncode": 0,
                "stdout": json.dumps(
                    [
                        {
                            "metadata": {"creationTimestamp": "2026-05-16T12:00:01Z"},
                            "name": "projects/example-dev/locations/us-central1/jobs/job/executions/recent",
                        }
                    ]
                ),
                "stderr": "",
            }
        return {
            "command": command,
            "returncode": 0,
            "stdout": "provider/raw/file.xlsx classified storage file expected_assay_output_count",
            "stderr": "",
        }

    monkeypatch.setattr(bard, "_run_monitor_command", fake_run_monitor_command)

    record = bard.job_execution_log_evidence_after(
        "provider_drive_to_gcs",
        started_at=datetime(2026, 5, 16, 12, 0, tzinfo=UTC),
        required_texts=["provider/raw/file.xlsx"],
        evidence_markers=["classified storage file", "missing"],
    )

    assert record["execution_name"] == "recent"
    assert record["required_texts"] == ["provider/raw/file.xlsx"]
    assert record["evidence_markers"] == ["classified storage file", "missing"]
    assert commands[-1] == [
        "gcloud",
        "logging",
        "read",
        'labels."run.googleapis.com/execution_name"="recent"',
        "--project=example-dev",
        "--limit=200",
        "--format=json",
    ]


def test_gcp_wjobbard_run_builds_cloud_run_execute_command():
    spec = WJobBardSpec(
        provider=WJobBardProvider.GCP,
        action=WieldAction.APPLY,
        scope="gcp_ops/wjobbard",
        stage_tier="dev",
        local_monitor=WJobBardLocalMonitor(
            project_id="example-dev",
            region="us-central1",
        ),
        jobs={"provider_drive_to_gcs": _wclone_job(runtime=_hosted_runtime())},
    )

    records = WJobBard.from_spec(spec).run(execute=False)

    assert records == [
        {
            "job_key": "provider_drive_to_gcs",
            "job_name": "example-provider-wclone-dev",
            "project_id": "example-dev",
            "region": "us-central1",
            "command": [
                "gcloud",
                "run",
                "jobs",
                "execute",
                "example-provider-wclone-dev",
                "--region=us-central1",
                "--project=example-dev",
                "--async",
                "--format=value(metadata.name)",
            ],
        }
    ]


def test_gcp_wjobbard_run_builds_waiting_cloud_run_execute_command():
    spec = WJobBardSpec(
        provider=WJobBardProvider.GCP,
        action=WieldAction.APPLY,
        scope="gcp_ops/wjobbard",
        stage_tier="dev",
        local_monitor=WJobBardLocalMonitor(
            project_id="example-dev",
            region="us-central1",
        ),
        jobs={"provider_drive_to_gcs": _wclone_job(runtime=_hosted_runtime())},
    )

    records = WJobBard.from_spec(spec).run(execute=False, wait=True)

    assert records[0]["command"] == [
        "gcloud",
        "run",
        "jobs",
        "execute",
        "example-provider-wclone-dev",
        "--region=us-central1",
        "--project=example-dev",
        "--async",
        "--format=value(metadata.name)",
    ]


def test_gcp_wjobbard_run_reuses_live_execution(monkeypatch):
    spec = WJobBardSpec(
        provider=WJobBardProvider.GCP,
        action=WieldAction.RUN,
        scope="gcp_ops/wjobbard",
        stage_tier="dev",
        local_monitor=WJobBardLocalMonitor(
            project_id="example-dev",
            region="us-central1",
        ),
        jobs={"provider_drive_to_gcs": _wclone_job(runtime=_hosted_runtime())},
    )
    bard = WJobBard.from_spec(spec)

    monkeypatch.setattr(
        bard,
        "_alive_execution_names",
        lambda *args, **kwargs: ["example-provider-wclone-dev-live"],
    )

    def fail_if_run_starts(*args, **kwargs):
        raise AssertionError("run must not start a second Cloud Run execution")

    monkeypatch.setattr("subprocess.run", fail_if_run_starts)

    records = bard.run(execute=True, wait=False)

    assert records[0]["execution_name"] == "example-provider-wclone-dev-live"
    assert records[0]["existing_execution"] is True
    assert records[0]["skipped_start"] is True


def test_gcp_wjobbard_run_refuses_multiple_live_executions(monkeypatch):
    spec = WJobBardSpec(
        provider=WJobBardProvider.GCP,
        action=WieldAction.RUN,
        scope="gcp_ops/wjobbard",
        stage_tier="dev",
        local_monitor=WJobBardLocalMonitor(
            project_id="example-dev",
            region="us-central1",
        ),
        jobs={"provider_drive_to_gcs": _wclone_job(runtime=_hosted_runtime())},
    )
    bard = WJobBard.from_spec(spec)

    def fail_if_run_starts(*args, **kwargs):
        raise AssertionError("run must not start a second Cloud Run execution")

    monkeypatch.setattr("subprocess.run", fail_if_run_starts)

    monkeypatch.setattr(
        bard,
        "_alive_execution_names",
        lambda *args, **kwargs: [
            "example-provider-wclone-dev-live-a",
            "example-provider-wclone-dev-live-b",
        ],
    )

    with pytest.raises(RuntimeError, match="multiple live executions"):
        bard.run(execute=True, wait=False)


def test_gcp_wjobbard_treats_non_terminal_execution_as_live():
    assert GCPJobBard._execution_is_alive(
        {
            "returncode": 0,
            "stdout": json.dumps({"status": {"conditions": [], "runningCount": 0}}),
            "stderr": "",
        }
    )


def test_gcp_wjobbard_treats_unknown_execution_status_as_live():
    assert GCPJobBard._execution_is_alive(
        {
            "returncode": 1,
            "stdout": "",
            "stderr": "transient cloud run status read failure",
        }
    )


def test_gcp_wjobbard_treats_terminal_execution_as_not_live():
    assert not GCPJobBard._execution_is_alive(
        {
            "returncode": 0,
            "stdout": json.dumps(
                {
                    "status": {
                        "conditions": [
                            {
                                "type": "Completed",
                                "status": "True",
                            }
                        ]
                    }
                }
            ),
            "stderr": "",
        }
    )


def test_gcp_wjobbard_run_starts_parallel_workflow_jobs_concurrently(monkeypatch):
    spec = WJobBardSpec(
        provider=WJobBardProvider.GCP,
        action=WieldAction.RUN,
        scope="gcp_ops/wjobbard",
        stage_tier="dev",
        local_monitor=WJobBardLocalMonitor(
            project_id="example-dev",
            region="us-central1",
        ),
        jobs={
            "partner_gcp_to_aws": _wclone_job_named("partner_gcp_to_aws", "example-partner-gcp-aws-wclone-dev"),
            "provider_drive_to_aws": _wclone_job_named("provider_drive_to_aws", "example-provider-drive-aws-wclone-dev"),
        },
        workflows={
            "cro_raw_mirror": WJobBardWorkflow(
                key="cro_raw_mirror",
                mode=WJobBardWorkflowMode.PARALLEL,
                job_keys=["partner_gcp_to_aws", "provider_drive_to_aws"],
            )
        },
        selected_workflows=["cro_raw_mirror"],
    )
    bard = WJobBard.from_spec(spec)
    active = 0
    max_active = 0
    started_commands = []

    monkeypatch.setattr(bard, "_alive_execution_names", lambda *args, **kwargs: [])
    monkeypatch.setattr(bard, "_latest_execution_name", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        bard,
        "_wait_for_started_execution_name",
        lambda job_name, **kwargs: f"{job_name}-execution",
    )

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        nonlocal active, max_active
        started_commands.append(command)
        active += 1
        max_active = max(max_active, active)
        time.sleep(0.05)
        active -= 1
        return Completed()

    monkeypatch.setattr("subprocess.run", fake_run)

    records = bard.run(execute=True, wait=False)

    assert [record["job_key"] for record in records] == ["partner_gcp_to_aws", "provider_drive_to_aws"]
    assert [record["execution_name"] for record in records] == [
        "example-partner-gcp-aws-wclone-dev-execution",
        "example-provider-drive-aws-wclone-dev-execution",
    ]
    assert max_active == 2
    assert [command[4] for command in started_commands] == [
        "example-partner-gcp-aws-wclone-dev",
        "example-provider-drive-aws-wclone-dev",
    ]


def test_gcp_wjobbard_run_uses_workflow_run_job_keys(monkeypatch):
    spec = WJobBardSpec(
        provider=WJobBardProvider.GCP,
        action=WieldAction.RUN,
        scope="gcp_ops/wjobbard",
        stage_tier="dev",
        local_monitor=WJobBardLocalMonitor(
            project_id="example-dev",
            region="us-central1",
        ),
        jobs={
            "source": _wclone_job_named("source", "example-source-wclone-dev"),
            "fanout": _wclone_job_named("fanout", "example-fanout-wclone-dev"),
        },
        workflows={
            "cro_raw_mirror": WJobBardWorkflow(
                key="cro_raw_mirror",
                mode=WJobBardWorkflowMode.PARALLEL,
                job_keys=["source", "fanout"],
                run_job_keys=["source"],
            )
        },
        selected_workflows=["cro_raw_mirror"],
    )
    bard = WJobBard.from_spec(spec)
    started_commands = []

    monkeypatch.setattr(bard, "_alive_execution_names", lambda *args, **kwargs: [])
    monkeypatch.setattr(bard, "_latest_execution_name", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        bard,
        "_wait_for_started_execution_name",
        lambda job_name, **kwargs: f"{job_name}-execution",
    )

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        started_commands.append(command)
        return Completed()

    monkeypatch.setattr("subprocess.run", fake_run)

    records = bard.run(execute=True, wait=False)

    assert [record["job_key"] for record in records] == ["source"]
    assert [command[4] for command in started_commands] == ["example-source-wclone-dev"]


def test_gcp_wjobbard_run_can_override_execution_env(monkeypatch):
    spec = WJobBardSpec(
        provider=WJobBardProvider.GCP,
        action=WieldAction.RUN,
        scope="gcp_ops/wjobbard",
        stage_tier="dev",
        local_monitor=WJobBardLocalMonitor(
            project_id="example-dev",
            region="us-central1",
        ),
        jobs={"source": _wclone_job_named("source", "example-source-wclone-dev")},
        selected_jobs=["source"],
    )
    bard = WJobBard.from_spec(spec)
    started_commands = []

    monkeypatch.setattr(bard, "_alive_execution_names", lambda *args, **kwargs: [])
    monkeypatch.setattr(bard, "_latest_execution_name", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        bard,
        "_wait_for_started_execution_name",
        lambda job_name, **kwargs: f"{job_name}-execution",
    )

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        started_commands.append(command)
        return Completed()

    monkeypatch.setattr("subprocess.run", fake_run)

    records = bard.run(
        execute=True,
        wait=False,
        execution_env={"RAW_MIRROR_RUN_ID": "run-123", "RAW_MIRROR_PROVENANCE_JSON": '{"a":1}'},
    )

    assert records[0]["execution_env_keys"] == ["RAW_MIRROR_PROVENANCE_JSON", "RAW_MIRROR_RUN_ID"]
    assert "--update-env-vars=^|||^RAW_MIRROR_RUN_ID=run-123|||RAW_MIRROR_PROVENANCE_JSON={\"a\":1}" in started_commands[0]


def test_gcp_wjobbard_materializes_tfvars_from_validated_context():
    spec = WJobBardSpec(
        provider=WJobBardProvider.GCP,
        action=WieldAction.PLAN,
        scope="gcp_ops/wjobbard",
        stage_tier="dev",
        jobs={"provider_drive_to_gcs": _wclone_job(runtime=_hosted_runtime())},
    )

    tfvars = WJobBard.from_spec(spec).tfvars_plan(
        {
            "configmap": {
                "ECOSYSTEM": "eco",
                "STAGE_TIER": "dev",
                "CONTEXT_CONF": "default_conf",
                "WIELDER_ACTION": "apply",
                "WJOBBARD_JOB_KEY": "do-not-trust-context",
            }
        }
    )

    job = tfvars["jobs"]["provider_drive_to_gcs"]
    assert job["name"] == "example-provider-wclone-dev"
    assert job["env"]["ECOSYSTEM"] == "eco"
    assert job["env"]["WJOBBARD_JOB_KEY"] == "provider_drive_to_gcs"
    assert job["env"]["WJOBBARD_KIND"] == "wcloner"
    assert job["env"]["WJOBBARD_SRC"] == "gcp_ops.bucket_migration.storage_loci.provider.drive"
    assert job["env"]["WJOBBARD_SINK"] == "gcp_ops.bucket_migration.storage_loci.provider.gcs"
    assert tfvars["cron_triggers"]["provider_drive_to_gcs--nightly"]["schedule"] == "0 2 * * *"
    assert tfvars["event_triggers"]["provider_drive_to_gcs--requested"]["topic_name"] == (
        "example-provider-raw-ingestion-dev"
    )


def test_wjobbard_tfvars_context_builds_standard_configmap():
    context = wjobbard_tfvars_context(
        ecosystem="eco",
        stage_tier="dev",
        context_conf="default_conf",
        action=WieldAction.APPLY,
        extra_configmap={"EXTRA": "value"},
    )

    assert context == {
        "configmap": {
            "ECOSYSTEM": "eco",
            "STAGE_TIER": "dev",
            "CONTEXT_CONF": "default_conf",
            "SECURITY": "org",
            "CANARY": "standard",
            "DESTROY": "standard",
            "WIELDER_ACTION": "apply",
            "EXTRA": "value",
        }
    }


def test_wjobbard_tfvars_context_from_conf_reads_standard_wielder_modes():
    class Conf:
        ecosystem = "eco"
        stage_tier = "dev"
        context_conf = "default_conf"
        security = "org"
        canary = "standard"
        destroy = "standard"

    context = wjobbard_tfvars_context_from_conf(
        Conf(),
        action=WieldAction.APPLY,
        extra_configmap={"EXTRA": "value"},
    )

    assert context == {
        "configmap": {
            "ECOSYSTEM": "eco",
            "STAGE_TIER": "dev",
            "CONTEXT_CONF": "default_conf",
            "SECURITY": "org",
            "CANARY": "standard",
            "DESTROY": "standard",
            "WIELDER_ACTION": "apply",
            "EXTRA": "value",
        }
    }


def test_wjobbard_runtime_configmap_from_conf_reads_standard_wielder_modes():
    class Conf:
        ecosystem = "eco"
        stage_tier = "dev"
        context_conf = "default_conf"
        security = "org"
        canary = "standard"
        destroy = "standard"

    runtime = WJobBardRuntimeConfigmap.from_conf(Conf(), action=WieldAction.APPLY)

    assert runtime.to_configmap(extra_configmap={"EXTRA": "value"}) == {
        "ECOSYSTEM": "eco",
        "STAGE_TIER": "dev",
        "CONTEXT_CONF": "default_conf",
        "SECURITY": "org",
        "CANARY": "standard",
        "DESTROY": "standard",
        "WIELDER_ACTION": "apply",
        "EXTRA": "value",
    }


def test_wjobbard_runtime_configmap_reads_canonical_job_environment():
    runtime = WJobBardRuntimeConfigmap.from_configmap(
        {
            "ECOSYSTEM": "eco",
            "STAGE_TIER": "dev",
            "CONTEXT_CONF": "default_conf",
            "SECURITY": "org",
            "CANARY": "standard",
            "WIELDER_ACTION": "apply",
            "WJOBBARD_JOB_KEY": "provider_drive_to_gcs",
            "WJOBBARD_KIND": "wcloner",
            "WJOBBARD_SRC": "gcp_ops.bucket_migration.storage_loci.provider.drive",
            "WJOBBARD_SINK": "gcp_ops.bucket_migration.storage_loci.provider.gcs",
            "WJOBBARD_ENTRYPOINT_MODULE": "example_data.apps.provider.ingestion.raw_mirror.provider_gcp_mirror",
        }
    )

    assert runtime.ecosystem == "eco"
    assert runtime.action == WieldAction.APPLY
    assert runtime.require_entrypoint_module(allowed_prefixes=("example_data.",)) == (
        "example_data.apps.provider.ingestion.raw_mirror.provider_gcp_mirror"
    )
    assert runtime.to_configmap()["WJOBBARD_JOB_KEY"] == "provider_drive_to_gcs"
    assert runtime.to_configmap()["WJOBBARD_KIND"] == "wcloner"
    assert runtime.to_configmap()["WJOBBARD_ENTRYPOINT_MODULE"] == (
        "example_data.apps.provider.ingestion.raw_mirror.provider_gcp_mirror"
    )


def test_wjobbard_runtime_configmap_supports_legacy_entrypoint_key():
    runtime = WJobBardRuntimeConfigmap.from_configmap(
        {
            "ECOSYSTEM": "eco",
            "STAGE_TIER": "dev",
            "CONTEXT_CONF": "default_conf",
            "WCLONE_ENTRYPOINT_MODULE": "example_data.apps.provider.ingestion.raw_mirror.provider_gcp_mirror",
        },
        fallback_entrypoint_keys=("WCLONE_ENTRYPOINT_MODULE",),
    )

    assert runtime.entrypoint_module == "example_data.apps.provider.ingestion.raw_mirror.provider_gcp_mirror"


def test_wjobbard_runtime_configmap_rejects_wrong_payload_prefix():
    runtime = WJobBardRuntimeConfigmap.from_configmap(
        {
            "ECOSYSTEM": "eco",
            "STAGE_TIER": "dev",
            "CONTEXT_CONF": "default_conf",
            "WJOBBARD_ENTRYPOINT_MODULE": "example_wielder.deploy.apps.gcp_ops.wield.gcp_ops_bucket_migration",
        }
    )

    with pytest.raises(ValueError, match="must start with one of"):
        runtime.require_entrypoint_module(allowed_prefixes=("example_data.",))


def test_gcp_wjobbard_tfvars_context_rejects_unknown_keys():
    bard = WJobBard.from_spec(
        WJobBardSpec(
            provider=WJobBardProvider.GCP,
            action=WieldAction.PLAN,
            scope="gcp_ops/wjobbard",
            stage_tier="dev",
        )
    )

    with pytest.raises(ValidationError):
        bard.tfvars_plan({"configmap": {}, "unknown": "value"})


def test_gcp_wjobbard_tfvars_requires_runtime_for_selected_jobs():
    bard = WJobBard.from_spec(
        WJobBardSpec(
            provider=WJobBardProvider.GCP,
            action=WieldAction.PLAN,
            scope="gcp_ops/wjobbard",
            stage_tier="dev",
            jobs={"provider_drive_to_gcs": _wclone_job()},
        )
    )

    with pytest.raises(ValueError, match="requires runtime"):
        bard.tfvars_plan({"configmap": {}})


def test_wjobbard_cloud_apply_is_explicitly_deferred():
    bard = WJobBard.from_spec(
        WJobBardSpec(
            provider=WJobBardProvider.GCP,
            action=WieldAction.APPLY,
            scope="gcp_ops/wjobbard",
            stage_tier="dev",
        )
    )

    with pytest.raises(NotImplementedError, match="Cloud Run/Scheduler milestone"):
        bard.apply()


def _wclone_job(
    input_event_types: list[str] | None = None,
    output_event_types: list[str] | None = None,
    runtime: WJobBardRuntime | None = None,
) -> WJobBardJob:
    return WJobBardJob(
        key="provider_drive_to_gcs",
        stage_tier="dev",
        provider=WJobBardProvider.GCP,
        kind=WJobBardTargetKind.WCLONER,
        src="gcp_ops.bucket_migration.storage_loci.provider.drive",
        sink="gcp_ops.bucket_migration.storage_loci.provider.gcs",
        triggers={
            "nightly": WJobBardTrigger(
                key="nightly",
                trigger_type=WJobBardTriggerType.CRON,
                schedule="0 2 * * *",
                input_event_type="schedule.tick",
            ),
            "requested": WJobBardTrigger(
                key="requested",
                trigger_type=WJobBardTriggerType.EVENT,
                topic_ref="example-provider-raw-ingestion-dev",
                input_event_type="raw_mirror.requested",
            ),
        },
        input_event_types=input_event_types
        if input_event_types is not None
        else ["schedule.tick", "raw_mirror.requested"],
        output_event_types=output_event_types
        if output_event_types is not None
        else ["raw_mirror.completed"],
        lifecycle_topic_ref="example-wjobbard-lifecycle-dev",
        runtime=runtime,
    )


def _wclone_job_named(key: str, runtime_name: str) -> WJobBardJob:
    job = _wclone_job(runtime=_hosted_runtime())
    return job.model_copy(
        update={
            "key": key,
            "kind": WJobBardTargetKind.WCLONER,
            "src": f"gcp_ops.bucket_migration.storage_loci.{key}.src",
            "sink": f"gcp_ops.bucket_migration.storage_loci.{key}.sink",
            "runtime": job.runtime.model_copy(update={"name": runtime_name}),
        }
    )


def _hosted_runtime() -> WJobBardRuntime:
    return WJobBardRuntime(
        name="example-provider-wclone-dev",
        image="us-central1-docker.pkg.dev/example-dev/example/example-control-runtime:dev",
        service_account_email="example-wclone-daemon-dev@example-dev.iam.gserviceaccount.com",
        command=["python"],
        args=["-m", "example_wielder.deploy.apps.gcp_ops.wield.gcp_ops_bucket_migration"],
        env={"WJOBBARD_JOB_KEY": "do-not-trust-runtime"},
        secret_env=[
            WJobBardSecretEnv(
                name="AWS_ACCESS_KEY_ID",
                secret="wclone-aws-source-access-key-id-dev",
            )
        ],
    )
