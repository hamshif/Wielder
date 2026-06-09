import pytest
from pydantic import ValidationError

from wielder.util.wargus import (
    AWSArgus,
    GCPArgus,
    GoogleWorkspaceArgus,
    LocalArgus,
    WArgus,
    WArgusGroup,
    WArgusPayloadSource,
    WArgusPayloadSourceType,
    WArgusProvider,
    WArgusSecurityHood,
    WArgusSecret,
    WArgusSpec,
)
from wielder.wield.enumerator import WieldAction


@pytest.mark.parametrize(
    ("provider", "expected_class"),
    [
        (WArgusProvider.GCP, GCPArgus),
        (WArgusProvider.GOOGLE_WORKSPACE, GoogleWorkspaceArgus),
        (WArgusProvider.AWS, AWSArgus),
        (WArgusProvider.LOCAL, LocalArgus),
    ],
)
def test_wargus_factory_returns_provider_implementation(provider, expected_class):
    argus = WArgus.from_provider(provider=provider, action=WieldAction.PLAN)

    assert isinstance(argus, expected_class)
    assert argus.provider == provider


def test_wargus_operations_are_explicitly_not_implemented():
    argus = WArgus.from_provider(provider="aws", action=WieldAction.PLAN)

    with pytest.raises(NotImplementedError, match="AWSArgus.plan is not implemented yet"):
        argus.plan()
    with pytest.raises(NotImplementedError, match="AWSArgus.populate_secret_versions is not implemented yet"):
        argus.populate_secret_versions()


def test_wargus_security_hood_defaults_to_org():
    argus = WArgus.from_provider(provider="gcp", action=WieldAction.PLAN)

    assert argus.spec.security_hood == WArgusSecurityHood.ORG
    assert argus.spec.security_hood.name_fragment == ""


def test_wargus_non_org_security_hood_has_name_fragment():
    spec = WArgusSpec(
        provider=WArgusProvider.GCP,
        action=WieldAction.PLAN,
        security_hood=WArgusSecurityHood.BREAK_GLASS,
    )

    assert spec.security_hood.name_fragment == "break-glass"


def test_wargus_secret_requires_stage_tier_suffix():
    with pytest.raises(ValidationError, match="must include stage_tier suffix"):
        WArgusSecret(
            name="wclone-aws-source-secret-access-key",
            stage_tier="dev",
            compartment="wclone",
        )


def test_wargus_group_requires_stage_tier_suffix():
    with pytest.raises(ValidationError, match="must include stage_tier suffix"):
        WArgusGroup(
            email="workspace-wclone-secret-operators@example.com",
            stage_tier="dev",
            compartment="wclone",
        )


def test_wargus_spec_accepts_classified_secret_and_workspace_group():
    secret = WArgusSecret(
        name="wclone-aws-source-secret-access-key-dev",
        stage_tier="dev",
        compartment="wclone",
        payload_source=WArgusPayloadSource(
            source_type=WArgusPayloadSourceType.ENV,
            reference="AWS_SECRET_ACCESS_KEY",
        ),
        runtime_readers=["serviceAccount:workspace-wclone-daemon-dev@workspace-dev.iam.gserviceaccount.com"],
        operator_groups=["group:workspace-wclone-secret-operators-dev@example.com"],
    )
    group = WArgusGroup(
        email="workspace-wclone-secret-operators-dev@example.com",
        name="Workspace WClone Secret Operators dev",
        description="Human WClone secret operators.",
        stage_tier="dev",
        compartment="wclone",
    )

    spec = WArgusSpec(
        provider=WArgusProvider.GCP,
        action=WieldAction.PLAN,
        project_id="workspace-dev",
        organization_slug="workspace",
        secrets=[secret],
        groups=[group],
    )

    assert spec.secrets[0].name == "wclone-aws-source-secret-access-key-dev"
    assert spec.groups[0].email == "workspace-wclone-secret-operators-dev@example.com"
    assert spec.groups[0].name == "Workspace WClone Secret Operators dev"


class _FakeGoogleHttpError(Exception):
    def __init__(self, status):
        self.resp = type("Response", (), {"status": status})()


class _FakeGoogleRequest:
    def __init__(self, callback):
        self.callback = callback

    def execute(self):
        return self.callback()


class _FakeGoogleGroups:
    def __init__(self, existing):
        self.existing = existing
        self.inserted = []

    def get(self, groupKey):
        def callback():
            if groupKey not in self.existing:
                raise _FakeGoogleHttpError(404)
            return self.existing[groupKey]

        return _FakeGoogleRequest(callback)

    def insert(self, body):
        def callback():
            self.existing[body["email"]] = body
            self.inserted.append(body)
            return body

        return _FakeGoogleRequest(callback)


class _FakeGoogleDirectoryService:
    def __init__(self, existing=None):
        self.groups_resource = _FakeGoogleGroups(existing or {})

    def groups(self):
        return self.groups_resource


def test_google_workspace_argus_plan_lists_configured_groups():
    spec = WArgusSpec(
        provider=WArgusProvider.GOOGLE_WORKSPACE,
        action=WieldAction.PLAN,
        groups=[
            WArgusGroup(
                email="workspace-wclone-secret-operators-dev@example.com",
                name="Workspace WClone Secret Operators dev",
                stage_tier="dev",
                compartment="wclone",
            )
        ],
    )

    plan = GoogleWorkspaceArgus(spec).plan()

    assert plan == [
        {
            "email": "workspace-wclone-secret-operators-dev@example.com",
            "name": "Workspace WClone Secret Operators dev",
            "description": "",
            "classification": "security_group",
            "compartment": "wclone",
            "create": True,
        }
    ]


def test_google_workspace_argus_apply_creates_missing_group():
    service = _FakeGoogleDirectoryService()
    spec = WArgusSpec(
        provider=WArgusProvider.GOOGLE_WORKSPACE,
        action=WieldAction.APPLY,
        groups=[
            WArgusGroup(
                email="workspace-wclone-secret-operators-dev@example.com",
                name="Workspace WClone Secret Operators dev",
                description="Human WClone secret operators.",
                stage_tier="dev",
                compartment="wclone",
            )
        ],
    )

    result = GoogleWorkspaceArgus(spec, directory_service=service).apply()

    assert result == [
        {
            "email": "workspace-wclone-secret-operators-dev@example.com",
            "status": "created",
        }
    ]
    assert service.groups_resource.inserted[0]["email"] == (
        "workspace-wclone-secret-operators-dev@example.com"
    )


def test_gcp_argus_plan_redacts_payload_source_values():
    spec = WArgusSpec(
        provider=WArgusProvider.GCP,
        action=WieldAction.PLAN,
        project_id="workspace-dev",
        secrets=[
            WArgusSecret(
                name="wclone-aws-source-access-key-id-dev",
                stage_tier="dev",
                compartment="wclone",
                payload_source=WArgusPayloadSource(
                    source_type=WArgusPayloadSourceType.ENV,
                    reference="AWS_ACCESS_KEY_ID",
                ),
            )
        ],
    )

    plan = GCPArgus(spec).plan()

    assert plan == [
        {
            "name": "wclone-aws-source-access-key-id-dev",
            "classification": "secret",
            "compartment": "wclone",
            "payload_source_type": "env",
            "payload_source_reference": "AWS_ACCESS_KEY_ID",
            "payload": "[redacted]",
        }
    ]


def test_gcp_argus_apply_adds_secret_manager_versions_without_logging_payload(monkeypatch):
    calls = []
    monkeypatch.setenv("WARGUS_TEST_SECRET", "super-secret-value")

    def fake_run(command, input, check, text, capture_output):
        calls.append(
            {
                "command": command,
                "input": input,
                "check": check,
                "text": text,
                "capture_output": capture_output,
            }
        )
        return type("CompletedProcess", (), {"returncode": 0, "stdout": "Created version [1].", "stderr": ""})()

    monkeypatch.setattr("wielder.util.wargus.subprocess.run", fake_run)
    spec = WArgusSpec(
        provider=WArgusProvider.GCP,
        action=WieldAction.APPLY,
        project_id="workspace-dev",
        secrets=[
            WArgusSecret(
                name="wclone-aws-source-access-key-id-dev",
                stage_tier="dev",
                compartment="wclone",
                payload_source=WArgusPayloadSource(
                    source_type=WArgusPayloadSourceType.ENV,
                    reference="WARGUS_TEST_SECRET",
                ),
            )
        ],
    )

    result = GCPArgus(spec).apply()

    assert result == [{"name": "wclone-aws-source-access-key-id-dev", "status": "version_added"}]
    assert calls == [
        {
            "command": [
                "gcloud",
                "secrets",
                "versions",
                "add",
                "wclone-aws-source-access-key-id-dev",
                "--project",
                "workspace-dev",
                "--data-file=-",
                "--quiet",
            ],
            "input": "super-secret-value",
            "check": False,
            "text": True,
            "capture_output": True,
        }
    ]
