from dataclasses import dataclass
import logging
import os
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

from wielder.util.credential_helper import aws_mfa_cred_as_boto3_session_kwargs
from wielder.util.util import get_aws_session


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class S3Uri:
    bucket: str
    key: str


def parse_s3_uri(uri: str) -> S3Uri:
    parsed = urlparse(str(uri))
    if parsed.scheme != "s3" or not parsed.netloc:
        raise ValueError(f"Expected an s3:// URI, got [{uri}].")
    return S3Uri(bucket=parsed.netloc, key=parsed.path.lstrip("/"))


class AWSActions:
    """
    Small boto3-backed action surface for Wielder scripts that used to shell out
    to the AWS CLI. The resolved Wielder conf still owns credential and region
    selection through get_aws_session(conf).
    """

    def __init__(self, conf):
        self.conf = conf
        self._session = _get_aws_session(conf)
        self._region_name = _aws_region_name(conf)
        self._clients = {}

    def client(self, service_name: str):
        if service_name not in self._clients:
            self._clients[service_name] = self._session.client(
                service_name,
                region_name=str(self._region_name) if self._region_name else None,
            )
        return self._clients[service_name]

    def s3_uri_exists(self, uri: str) -> bool:
        parsed = parse_s3_uri(uri)
        s3 = self.client("s3")
        if not parsed.key or str(uri).endswith("/"):
            response = s3.list_objects_v2(
                Bucket=parsed.bucket,
                Prefix=parsed.key,
                MaxKeys=1,
            )
            return bool(response.get("Contents", []))

        try:
            s3.head_object(Bucket=parsed.bucket, Key=parsed.key)
            return True
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchKey", "NotFound"}:
                raise

        response = s3.list_objects_v2(
            Bucket=parsed.bucket,
            Prefix=f"{parsed.key.rstrip('/')}/",
            MaxKeys=1,
        )
        return bool(response.get("Contents", []))

    def ecr_image_exists(self, repository_name: str, image_tag: str) -> bool:
        try:
            response = self.client("ecr").describe_images(
                repositoryName=str(repository_name),
                imageIds=[{"imageTag": str(image_tag)}],
            )
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"ImageNotFoundException", "RepositoryNotFoundException", "RepositoryNotFound"}:
                return False
            raise
        return bool(response.get("imageDetails", []))


_MISSING = object()


def _raw_conf_value(conf, key: str):
    try:
        return getattr(conf, key)
    except Exception:
        try:
            return conf.get(key)
        except Exception:
            return _MISSING


def _conf_value(conf, keys: tuple[str, ...], default: str | None = None) -> str | None:
    for key in keys:
        value = _raw_conf_value(conf, key)
        if value is _MISSING:
            continue
        if value is not None and str(value).strip():
            return str(value)
    return default


def _aws_region_name(conf) -> str | None:
    return _conf_value(conf, ("aws_region", "aws_zone", "image_repo_zone"))


def _has_canonical_aws_session_fields(conf) -> bool:
    return all(_raw_conf_value(conf, key) is not _MISSING for key in ("aws_cred_role", "aws_profile", "aws_zone"))


def _get_aws_session(conf):
    if _has_canonical_aws_session_fields(conf):
        return get_aws_session(conf)

    role = _conf_value(conf, ("aws_cred_role", "cred_role"), "")
    profile_name = _conf_value(conf, ("aws_profile", "cred_profile"), "")
    region_name = _aws_region_name(conf)
    session_kwargs = aws_mfa_cred_as_boto3_session_kwargs(role)
    if not session_kwargs and profile_name and not _has_runtime_aws_credentials():
        session_kwargs["profile_name"] = profile_name
    if region_name:
        session_kwargs["region_name"] = region_name
    return boto3.Session(**session_kwargs)


def _has_runtime_aws_credentials() -> bool:
    return any(
        os.environ.get(key)
        for key in (
            "AWS_ACCESS_KEY_ID",
            "AWS_CONTAINER_CREDENTIALS_FULL_URI",
            "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
            "AWS_WEB_IDENTITY_TOKEN_FILE",
        )
    )
