from wielder.util import credential_helper


def test_aws_mfa_cred_as_subprocess_env_removes_profile(monkeypatch):
    monkeypatch.setattr(
        credential_helper,
        "get_aws_mfa_cred",
        lambda role: {
            "AWS_ACCESS_KEY_ID": "key",
            "AWS_SECRET_ACCESS_KEY": "secret",
            "AWS_SESSION_TOKEN": "token",
            "AWS_SECURITY_TOKEN": "token",
        },
    )

    env = credential_helper.aws_mfa_cred_as_subprocess_env(
        "role-a",
        base_env={"AWS_PROFILE": "profile-a", "PATH": "/bin"},
    )

    assert env["AWS_ACCESS_KEY_ID"] == "key"
    assert env["AWS_SECRET_ACCESS_KEY"] == "secret"
    assert env["AWS_SESSION_TOKEN"] == "token"
    assert env["AWS_SECURITY_TOKEN"] == "token"
    assert env["PATH"] == "/bin"
    assert "AWS_PROFILE" not in env


def test_aws_mfa_cred_as_boto3_session_kwargs(monkeypatch):
    monkeypatch.setattr(
        credential_helper,
        "get_aws_mfa_cred",
        lambda role: {
            "AWS_ACCESS_KEY_ID": "key",
            "AWS_SECRET_ACCESS_KEY": "secret",
            "AWS_SESSION_TOKEN": "token",
            "AWS_SECURITY_TOKEN": "token",
        },
    )

    assert credential_helper.aws_mfa_cred_as_boto3_session_kwargs("role-a") == {
        "aws_access_key_id": "key",
        "aws_secret_access_key": "secret",
        "aws_session_token": "token",
    }
