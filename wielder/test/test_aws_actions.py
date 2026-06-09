from types import SimpleNamespace

from botocore.exceptions import ClientError

from wielder.util import aws_actions
from wielder.util.aws_actions import AWSActions, parse_s3_uri


class FakeSession:
    def __init__(self, clients):
        self.clients = clients
        self.calls = []

    def client(self, service_name, region_name=None):
        self.calls.append((service_name, region_name))
        return self.clients[service_name]


class FakeS3:
    def __init__(self, head_errors=None, list_response=None):
        self.head_errors = head_errors or {}
        self.list_response = list_response or {}
        self.head_calls = []
        self.list_calls = []

    def head_object(self, **kwargs):
        self.head_calls.append(kwargs)
        error_code = self.head_errors.get(kwargs["Key"])
        if error_code:
            raise ClientError(
                {"Error": {"Code": error_code, "Message": error_code}},
                "HeadObject",
            )
        return {}

    def list_objects_v2(self, **kwargs):
        self.list_calls.append(kwargs)
        return self.list_response


class FakeECR:
    def __init__(self, response=None, error_code=None):
        self.response = response or {"imageDetails": [{"imageDigest": "sha256:x"}]}
        self.error_code = error_code
        self.calls = []

    def describe_images(self, **kwargs):
        self.calls.append(kwargs)
        if self.error_code:
            raise ClientError(
                {"Error": {"Code": self.error_code, "Message": self.error_code}},
                "DescribeImages",
            )
        return self.response


def _conf():
    return SimpleNamespace(
        aws_region="us-east-2",
        aws_zone="us-east-2",
        aws_profile="",
        aws_cred_role="",
    )


def test_parse_s3_uri_requires_s3_scheme():
    parsed = parse_s3_uri("s3://bucket/path/to/object")

    assert parsed.bucket == "bucket"
    assert parsed.key == "path/to/object"


def test_aws_actions_use_configured_wielder_session(monkeypatch):
    fake_s3 = FakeS3()
    fake_session = FakeSession({"s3": fake_s3})
    monkeypatch.setattr(aws_actions, "get_aws_session", lambda conf: fake_session)
    actions = AWSActions(_conf())

    assert actions.s3_uri_exists("s3://bucket/object") is True
    assert fake_session.calls == [("s3", "us-east-2")]


def test_aws_actions_s3_uri_exists_checks_objects_and_prefixes(monkeypatch):
    fake_s3 = FakeS3(
        head_errors={"prefix": "404"},
        list_response={"Contents": [{"Key": "prefix/child"}]},
    )
    monkeypatch.setattr(
        aws_actions,
        "get_aws_session",
        lambda conf: FakeSession({"s3": fake_s3}),
    )
    actions = AWSActions(_conf())

    assert actions.s3_uri_exists("s3://bucket/object") is True
    assert actions.s3_uri_exists("s3://bucket/prefix") is True
    assert actions.s3_uri_exists("s3://bucket/prefix/") is True

    assert fake_s3.head_calls == [
        {"Bucket": "bucket", "Key": "object"},
        {"Bucket": "bucket", "Key": "prefix"},
    ]
    assert fake_s3.list_calls == [
        {"Bucket": "bucket", "Prefix": "prefix/", "MaxKeys": 1},
        {"Bucket": "bucket", "Prefix": "prefix/", "MaxKeys": 1},
    ]


def test_aws_actions_ecr_image_exists_uses_boto_client(monkeypatch):
    fake_ecr = FakeECR()
    monkeypatch.setattr(
        aws_actions,
        "get_aws_session",
        lambda conf: FakeSession({"ecr": fake_ecr}),
    )

    assert AWSActions(_conf()).ecr_image_exists("workspace/app", "dev") is True

    assert fake_ecr.calls == [
        {
            "repositoryName": "workspace/app",
            "imageIds": [{"imageTag": "dev"}],
        }
    ]


def test_aws_actions_ecr_image_exists_returns_false_for_missing_image(monkeypatch):
    fake_ecr = FakeECR(error_code="ImageNotFoundException")
    monkeypatch.setattr(
        aws_actions,
        "get_aws_session",
        lambda conf: FakeSession({"ecr": fake_ecr}),
    )

    assert AWSActions(_conf()).ecr_image_exists("workspace/app", "dev") is False


def test_aws_actions_accepts_narrow_ecr_push_conf(monkeypatch):
    created = {}
    fake_ecr = FakeECR()

    def fake_session(**kwargs):
        created["kwargs"] = kwargs
        return FakeSession({"ecr": fake_ecr})

    monkeypatch.delenv("AWS_CONTAINER_CREDENTIALS_FULL_URI", raising=False)
    monkeypatch.delenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI", raising=False)
    monkeypatch.delenv("AWS_WEB_IDENTITY_TOKEN_FILE", raising=False)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.setattr(aws_actions, "aws_mfa_cred_as_boto3_session_kwargs", lambda role: {})
    monkeypatch.setattr(aws_actions.boto3, "Session", fake_session)

    actions = AWSActions(SimpleNamespace(image_repo_zone="us-east-1", cred_profile="operator"))

    assert actions.ecr_image_exists("workspace/app", "dev") is True
    assert created["kwargs"] == {"profile_name": "operator", "region_name": "us-east-1"}


def test_aws_actions_prefers_runtime_credentials_over_profile(monkeypatch):
    created = {}

    def fake_session(**kwargs):
        created["kwargs"] = kwargs
        return FakeSession({"ecr": FakeECR()})

    monkeypatch.setenv("AWS_CONTAINER_CREDENTIALS_FULL_URI", "http://169.254.170.23/creds")
    monkeypatch.setattr(aws_actions, "aws_mfa_cred_as_boto3_session_kwargs", lambda role: {})
    monkeypatch.setattr(aws_actions.boto3, "Session", fake_session)

    actions = AWSActions(SimpleNamespace(image_repo_zone="us-east-1", cred_profile="operator"))

    assert actions.ecr_image_exists("workspace/app", "dev") is True
    assert created["kwargs"] == {"region_name": "us-east-1"}
