from types import SimpleNamespace

from wielder.util import util


def test_get_aws_session_uses_ambient_credentials_when_mfa_cache_is_empty(monkeypatch):
    calls = []

    monkeypatch.setattr(util, "aws_mfa_cred_as_boto3_session_kwargs", lambda role: {})
    monkeypatch.setattr(util.boto3, "Session", lambda **kwargs: calls.append(kwargs) or object())

    util.get_aws_session(
        SimpleNamespace(
            aws_cred_role="role-a",
            aws_profile="",
            aws_zone="us-east-1",
        )
    )

    assert calls == [{"profile_name": None, "region_name": "us-east-1"}]


def test_get_aws_session_prefers_cached_mfa_credentials(monkeypatch):
    calls = []

    monkeypatch.setattr(
        util,
        "aws_mfa_cred_as_boto3_session_kwargs",
        lambda role: {
            "aws_access_key_id": "key",
            "aws_secret_access_key": "secret",
            "aws_session_token": "token",
        },
    )
    monkeypatch.setattr(util.boto3, "Session", lambda **kwargs: calls.append(kwargs) or object())

    util.get_aws_session(
        SimpleNamespace(
            aws_cred_role="role-a",
            aws_profile="profile-a",
            aws_zone="us-east-1",
        )
    )

    assert calls == [
        {
            "aws_access_key_id": "key",
            "aws_secret_access_key": "secret",
            "aws_session_token": "token",
            "region_name": "us-east-1",
        }
    ]
