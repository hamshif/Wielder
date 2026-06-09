import logging
import os
import pathlib
import fnmatch
import re
import uuid
import io
import hashlib
import datetime
import json
import subprocess
import tempfile
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import boto3
from botocore.exceptions import ClientError
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from rich.console import Console
from rich.tree import Tree
from tabulate import tabulate
from tqdm import tqdm

import wielder.util.util as wu
from wielder.util.boto3_session_cache import boto3_client
from wielder.util.google_drive import service_login
from wielder.util.util import get_aws_session
from wielder.wield.enumerator import RuntimeEnv, WieldAction, local_deployments
from wielder.wield.project import WielderProject

# todo if we decide on that, add dependencies to be installed automatically

DEFAULT_REGION = "us-east-2"


@dataclass(frozen=True)
class BucketeerWalkEntry:
    """Object-store equivalent of one os.walk directory row."""

    key: str
    dirnames: tuple[str, ...]
    filenames: tuple[str, ...]
    recursive_file_count: int
    recursive_dir_count: int


@dataclass(frozen=True)
class GoogleDrivePermissionEnsureResult:
    """Result of planning or applying one Google Drive permission."""

    file_id: str
    role: str
    permission_type: str
    email: str | None
    action: str
    status: str
    permission_id: str | None = None
    previous_role: str | None = None


@dataclass(frozen=True)
class GoogleDriveBucketEnsureResult:
    """Result of planning or applying one Google Shared Drive bucket."""

    bucket_name: str
    action: str
    status: str
    drive_id: str | None = None

    def __bool__(self):
        return self.drive_id is not None


@dataclass(frozen=True)
class BucketEnsureResult:
    """Result of planning or applying one cloud object-store bucket."""

    bucket_name: str
    action: str
    status: str
    exists: bool

    def __bool__(self):
        return self.exists


def _plain_conf(value):
    if hasattr(value, "as_plain_ordered_dict"):
        return value.as_plain_ordered_dict()
    return value


class WRcloneBucketeerConfig(BaseModel):
    """Pydantic contract for a Bucketeer backed by an rclone remote."""

    model_config = ConfigDict(extra="forbid")

    rclone_remote: str
    rclone_config_path: str
    common_flags: list[str] = Field(default_factory=list)
    wclone_configs: list[dict[str, Any]] = Field(default_factory=list)
    configure_on_init: bool = True

    @classmethod
    def from_conf(cls, conf) -> "WRcloneBucketeerConfig":
        return cls.model_validate(_plain_conf(conf))

    @field_validator("rclone_remote", "rclone_config_path")
    @classmethod
    def require_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value

    @field_validator("rclone_remote")
    @classmethod
    def reject_unsafe_remote_token(cls, value: str) -> str:
        if any(char in value for char in [":", ",", "[", "]", "\\"]):
            raise ValueError(f"unsafe rclone remote token [{value}]")
        return value

    @field_validator("rclone_config_path")
    @classmethod
    def reject_windows_config_path(cls, value: str) -> str:
        if "\\" in value:
            raise ValueError(f"Refusing rclone config path with backslash: {value}")
        return value

    @field_validator("common_flags")
    @classmethod
    def reject_empty_flags(cls, values: list[str]) -> list[str]:
        empty_flags = [value for value in values if not str(value).strip()]
        if empty_flags:
            raise ValueError("rclone common_flags must not contain empty values")
        return values

    @model_validator(mode="after")
    def validate_wclone_configs(self):
        for configuration in self.wclone_configs:
            if not isinstance(_plain_conf(configuration), dict):
                raise ValueError("wclone_configs entries must be mapping objects")
        return self


class Bucketeer(ABC):
    """
    Provider-neutral bucket interface for object-like storage.

    Bucketeer implementations expose a common key-based API over S3, GCS,
    Google Shared Drive, and local dev buckets. Capabilities include bucket
    creation/inspection, object upload/download/delete, prefix listing,
    tree rendering, object existence checks, sync/copy helpers, shell-style
    glob matching, regex matching, and plan/apply-aware bulk deletion.

    Public key-oriented methods should accept and return normalized POSIX-style
    object keys relative to the bucket root, such as ``partner/Gargamel.txt``.
    Some provider-native list calls return direct child names rather than full
    keys; use ``object_keys_by_prefix`` when callers need normalized full keys.
    """

    def __init__(self, conf):
        self.conf = conf

    @abstractmethod
    def create_bucket(self, bucket_name, region=None):
        pass

    @abstractmethod
    def cli_upload_file(self, source, bucket_name, dest, is_text=False):
        pass

    @abstractmethod
    def upload_file(self, source, bucket_name, dest, is_text=False, replace=False):
        pass

    @abstractmethod
    def upload_string(self, string_data, bucket_name, dest):
        pass

    @abstractmethod
    def upload_directory(self, source, bucket_name, prefix):
        pass

    @abstractmethod
    def sync_directory(self, source, bucket_name, prefix):
        """
        Idempotent recursive upload. Scans the destination prefix and selectively uploads
        only local files that are missing from the destination, skipping identical filenames.
        """
        pass

    @abstractmethod
    def read_object_stream(self, bucket_name, key, name):
        """Yields an in-memory reading stream of the blob natively as a context manager."""
        pass

    @abstractmethod
    def download_object(self, bucket_name, key, name, dest='/tmp'):
        pass

    @abstractmethod
    def cli_download_object(self, bucket_name, key, dest):
        pass

    @abstractmethod
    def download_objects(self, bucket_name, keys, dest='/tmp'):
        pass

    @abstractmethod
    def download_objects_flat_by_key(self, bucket_name, root_key='', dest='/tmp'):
        pass

    @abstractmethod
    def download_objects_tree_by_key(self, bucket_name, root_key='', dest='/tmp'):
        pass

    def download_objects_by_key(self, bucket_name, root_key='', dest='/tmp'):
        """
        Legacy prefix download entrypoint. Prefer the explicit flat/tree variants.
        """
        return self.download_objects_flat_by_key(bucket_name, root_key, dest)

    @abstractmethod
    def delete_file(self, bucket_name, file_name):
        pass

    @abstractmethod
    def delete_bucket(self, bucket_name):
        pass

    @abstractmethod
    def get_bucket_names(self):
        pass

    def bucket_exists(self, bucket_name):
        """Generic bucket existence check for providers that expose bucket names."""
        return bucket_name in self.get_bucket_names()

    def get_bucket_id(self, bucket_name):
        """
        Return the provider-native bucket identifier when one exists.

        Object stores generally use the bucket name as the addressable ID. Providers
        with a distinct native ID, such as Google Shared Drive, should override this.
        """
        return bucket_name if self.bucket_exists(bucket_name) else None

    def ensure_bucket(self, bucket_name, region=None, action=WieldAction.APPLY):
        """
        Idempotently plan or create a bucket-like destination.

        Provider implementations should override this when the native API has
        provider-specific existence or creation semantics.
        """
        action = action if isinstance(action, WieldAction) else WieldAction(str(action))
        exists = self.bucket_exists(bucket_name)
        if exists:
            return BucketEnsureResult(bucket_name=str(bucket_name), action=action.value, status="exists", exists=True)
        if action != WieldAction.APPLY:
            return BucketEnsureResult(bucket_name=str(bucket_name), action=action.value, status="would_create", exists=False)
        created = self.create_bucket(bucket_name, region=region)
        if not created:
            raise RuntimeError(f"Failed to create bucket [bucket={bucket_name}, region={region}]")
        return BucketEnsureResult(bucket_name=str(bucket_name), action=action.value, status="created", exists=True)

    def ensure_permissions(self, file_id, permissions, send_notification_email=False, action=WieldAction.APPLY):
        raise NotImplementedError(f"{self.__class__.__name__} does not implement ensure_permissions().")

    @abstractmethod
    def get_object_names(self, bucket_name, prefix=''):
        pass

    @abstractmethod
    def object_exists(self, bucket_name, prefix, object_name):
        pass

    @abstractmethod
    def bucket_sync(self, src_bucket, dest_bucket, src_prefix, dest_prefix):
        pass

    @abstractmethod
    def list_files_by_key(self, bucket_name, root_key):
        pass

    def iter_files_by_key(self, bucket_name, root_key):
        yield from self.list_files_by_key(bucket_name, root_key)

    @abstractmethod
    def ensure_prefix(self, bucket_name, prefix):
        pass

    def object_exists_by_key(self, bucket_name: str, object_key: str):
        prefix, object_name = object_key.rsplit('/', 1) if '/' in object_key else ('', object_key)
        return self.object_exists(bucket_name, prefix, object_name)

    def object_uri_by_key(self, bucket_name: str, object_key: str) -> str:
        return f"{bucket_name}/{self.normalize_object_key(object_key)}"

    def object_view_url_by_key(self, bucket_name: str, object_key: str) -> str:
        return self.object_uri_by_key(bucket_name, object_key)

    def object_state_by_key(self, bucket_name: str, object_key: str, uri: str | None = None) -> dict:
        normalized_key = self.normalize_object_key(object_key)
        exists = self.object_exists_by_key(bucket_name, normalized_key)
        return {
            "provider": self.__class__.__name__,
            "bucket": str(bucket_name),
            "key": normalized_key,
            "uri": uri or self.object_uri_by_key(bucket_name, normalized_key),
            "exists": exists,
            "checked_at": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
        }

    def assert_object_exists_by_key(self, bucket_name: str, object_key: str, uri: str | None = None) -> dict:
        state = self.object_state_by_key(bucket_name, object_key, uri=uri)
        if not state["exists"]:
            raise RuntimeError(f"Expected object does not exist: {state['uri']}")
        return state

    def assert_object_absent_by_key(self, bucket_name: str, object_key: str, uri: str | None = None) -> dict:
        state = self.object_state_by_key(bucket_name, object_key, uri=uri)
        if state["exists"]:
            raise RuntimeError(f"Expected object to be deleted but it still exists: {state['uri']}")
        return state

    def delete_object_if_exists_by_key(
        self,
        bucket_name: str,
        object_key: str,
        uri: str | None = None,
        action: WieldAction | str = WieldAction.APPLY,
    ) -> dict:
        action = action if isinstance(action, WieldAction) else WieldAction(str(action))
        state = self.object_state_by_key(bucket_name, object_key, uri=uri)
        deleted = False
        if state["exists"] and action == WieldAction.APPLY:
            self.delete_file(bucket_name=bucket_name, file_name=state["key"])
            deleted = True
        return {**state, "action": action.value, "deleted": deleted}

    def normalize_object_key(self, raw_key: str) -> str:
        return _normalize_object_key(raw_key)

    def join_object_key(self, *parts: str) -> str:
        normalized_parts = [_normalize_object_key(str(part)) for part in parts if str(part).strip().strip("/")]
        if not normalized_parts:
            return ""
        return pathlib.PurePosixPath(*normalized_parts).as_posix()

    def relative_object_key(self, object_key: str, root_key: str) -> str:
        normalized_object_key = _normalize_object_key(object_key)
        normalized_root_key = _normalize_object_key(root_key)
        if not normalized_root_key:
            return normalized_object_key
        root_parts = pathlib.PurePosixPath(normalized_root_key).parts
        object_parts = pathlib.PurePosixPath(normalized_object_key).parts
        if object_parts[: len(root_parts)] != root_parts:
            raise ValueError(f"Object key [{object_key}] is not under root key [{root_key}].")
        return pathlib.PurePosixPath(*object_parts[len(root_parts):]).as_posix()

    def walk_tree(
        self,
        bucket_name: str,
        root_key: str = '',
        max_depth: int | None = None,
    ) -> list[BucketeerWalkEntry]:
        normalized_root_key = self.normalize_object_key(root_key)
        object_keys = sorted(self.get_object_names(bucket_name, normalized_root_key))
        return _walk_object_keys(object_keys, normalized_root_key, max_depth=max_depth)

    def render_tree(
        self,
        bucket_name: str,
        root_key: str = '',
        max_depth: int = 6,
        include_files: bool = False,
        max_children_per_node: int = 80,
    ) -> str:
        return _render_directory_tree(
            entries=self.walk_tree(bucket_name=bucket_name, root_key=root_key),
            bucket=bucket_name,
            root_key=root_key,
            max_depth=max_depth,
            include_files=include_files,
            max_children_per_node=max_children_per_node,
        )

    def upload_string_if_missing(self, string_data, bucket_name, dest):
        if self.object_exists_by_key(bucket_name, dest):
            return False
        self.upload_string(string_data, bucket_name, dest)
        return True

    def object_keys_by_prefix(self, bucket_name: str, root_key: str = '', *, recursive: bool = False) -> list[str]:
        """
        Return normalized full object keys under ``root_key``.

        With ``recursive=False``, only direct file children of ``root_key`` are
        returned. With ``recursive=True``, files below nested prefixes are also
        returned. This method is the normalized listing primitive for matching
        helpers because providers differ: S3/GCS generally list full keys, while
        Google Drive folder listings may return child names.
        """
        normalized_root_key = self.normalize_object_key(root_key)
        listed_keys = (
            list(self.iter_files_by_key(bucket_name, normalized_root_key))
            if recursive
            else list(self.get_object_names(bucket_name, normalized_root_key))
        )
        object_keys = [
            self._normalized_listed_object_key(normalized_root_key, listed_key)
            for listed_key in listed_keys
        ]
        if not recursive:
            object_keys = [
                key
                for key in object_keys
                if self._is_direct_child_object_key(normalized_root_key, key)
            ]
        return sorted(set(object_keys))

    def glob_keys(self, bucket_name, pattern, recursive=False):
        """
        Return object keys matching a shell-style glob pattern.

        ``pattern`` is matched against normalized full object keys, for example
        ``partner/Gargamel--*.txt``. The static prefix before the first wildcard is
        used to limit provider listing scope before applying ``fnmatch``.
        """
        static_prefix = pattern.split('*', 1)[0].split('?', 1)[0]
        if static_prefix and '/' in static_prefix and not static_prefix.endswith('/'):
            static_prefix = static_prefix[:static_prefix.rfind('/') + 1]
        return sorted(
            key
            for key in self.object_keys_by_prefix(bucket_name, static_prefix, recursive=recursive)
            if fnmatch.fnmatch(key, pattern)
        )

    def _normalized_listed_object_key(self, root_key: str, listed_key: str) -> str:
        """Convert a provider-listed key or child name into a normalized full object key."""
        normalized_root_key = self.normalize_object_key(root_key)
        normalized_listed_key = self.normalize_object_key(listed_key)
        if not normalized_root_key:
            return normalized_listed_key
        if normalized_listed_key == normalized_root_key or normalized_listed_key.startswith(f"{normalized_root_key}/"):
            return normalized_listed_key
        return self.join_object_key(normalized_root_key, normalized_listed_key)

    def _is_direct_child_object_key(self, root_key: str, object_key: str) -> bool:
        """Return whether ``object_key`` is a direct file child of ``root_key``."""
        normalized_root_key = self.normalize_object_key(root_key)
        normalized_object_key = self.normalize_object_key(object_key)
        if not normalized_root_key:
            return "/" not in normalized_object_key
        if normalized_object_key == normalized_root_key:
            return True
        if not normalized_object_key.startswith(f"{normalized_root_key}/"):
            return False
        return "/" not in normalized_object_key[len(normalized_root_key) + 1:]

    def object_keys_matching_regex(
        self,
        bucket_name: str,
        root_key: str,
        regex: str | re.Pattern[str],
        *,
        recursive: bool = False,
        match_basename: bool = True,
    ) -> list[str]:
        """
        Return object keys under ``root_key`` whose name or key matches ``regex``.

        By default the regex is applied to each basename, which is the common
        cleanup use case. Set ``match_basename=False`` to match the full
        normalized key, including prefix path components.
        """
        compiled = re.compile(regex) if isinstance(regex, str) else regex
        object_keys = self.object_keys_by_prefix(bucket_name, root_key, recursive=recursive)
        return sorted(
            key
            for key in object_keys
            if compiled.search(key.rsplit("/", 1)[-1] if match_basename else key)
        )

    def delete_objects_matching_regex(
        self,
        bucket_name: str,
        root_key: str,
        regex: str | re.Pattern[str],
        *,
        recursive: bool = False,
        match_basename: bool = True,
        action: WieldAction | str = WieldAction.APPLY,
    ) -> list[str]:
        """
        Delete regex-matched object keys and return the matched keys.

        In ``plan`` and other non-apply actions, no objects are deleted; the
        method only returns what would be deleted. In ``apply``, each matched
        key is passed to the provider's ``delete_file`` implementation.
        """
        action = action if isinstance(action, WieldAction) else WieldAction(str(action))
        keys = self.object_keys_matching_regex(
            bucket_name=bucket_name,
            root_key=root_key,
            regex=regex,
            recursive=recursive,
            match_basename=match_basename,
        )
        if action != WieldAction.APPLY:
            return keys
        for key in keys:
            self.delete_file(bucket_name=bucket_name, file_name=key)
        return keys


class AWSBucketeer(Bucketeer):
    """
    A convenience interface for working with AWS buckets.
    This wrapper object was created mainly to retain the AMI session.
    We use MFA for development and the code is per process.
    It currently supports AWS S3.
    """

    def list_files_by_key(self, bucket_name, root_key):
        return self.get_object_names(bucket_name, root_key)

    def __init__(self, conf=None, auth=True, env_credentials=None, region=None):

        super().__init__(conf)
        self.region = region or (conf.get("aws_zone", None) if conf is not None else None) or DEFAULT_REGION

        if env_credentials:
            if "AWS_ACCESS_KEY_ID" in env_credentials:
                session = boto3.Session(
                    aws_access_key_id=env_credentials["AWS_ACCESS_KEY_ID"],
                    aws_secret_access_key=env_credentials["AWS_SECRET_ACCESS_KEY"],
                    aws_session_token=env_credentials["AWS_SESSION_TOKEN"],
                    region_name=self.region,
                )
            else:
                os.environ.update(env_credentials)
                session = boto3.Session(region_name=self.region)
            self.s3 = session.resource('s3').meta.client
        elif auth:
            session = get_aws_session(conf)
            self.s3 = session.resource('s3').meta.client
        else:
            logging.info('Direct auth not needed, getting default client.')
            self.s3 = boto3_client(service_name='s3')

    def object_uri_by_key(self, bucket_name: str, object_key: str) -> str:
        return f"s3://{bucket_name}/{self.normalize_object_key(object_key)}"

    def object_view_url_by_key(self, bucket_name: str, object_key: str) -> str:
        key = quote(self.normalize_object_key(object_key), safe="/")
        return (
            f"https://s3.console.aws.amazon.com/s3/object/{bucket_name}"
            f"?region={self.region}&bucketType=general&prefix={key}"
        )

    def create_bucket(self, bucket_name, region=None):
        """Create an S3 bucket in a specified region

        If a region is not specified, the bucket is created in the S3 default
        region (us-east-1).

        :param bucket_name: Bucket to create
        :param region: String region to create bucket in, e.g., 'us-east-2'
        :return: True if bucket created, else False
        """
        try:
            if region is None:
                region = self.region

            if region == "us-east-1":
                response = self.s3.create_bucket(Bucket=bucket_name)
            else:
                location = {'LocationConstraint': region}
                response = self.s3.create_bucket(Bucket=bucket_name,
                                                 CreateBucketConfiguration=location)
            print(response)
        except ClientError as e:
            logging.error(e)
            return False
        return True

    def ensure_bucket(self, bucket_name, region=None, action=WieldAction.APPLY):
        action = action if isinstance(action, WieldAction) else WieldAction(str(action))
        try:
            exists = self.bucket_exists(bucket_name)
        except ClientError as exc:
            raise RuntimeError(f"Failed to inspect AWS S3 bucket [bucket={bucket_name}]: {exc}") from exc

        if exists:
            logging.info(f"[{action.value}] AWS S3 bucket already exists [bucket={bucket_name}]")
            return BucketEnsureResult(bucket_name=str(bucket_name), action=action.value, status="exists", exists=True)

        if action != WieldAction.APPLY:
            logging.info(f"[{action.value}] Would create AWS S3 bucket [bucket={bucket_name}]")
            return BucketEnsureResult(bucket_name=str(bucket_name), action=action.value, status="would_create", exists=False)

        created = self.create_bucket(bucket_name, region=region)
        if not created:
            raise RuntimeError(f"Failed to create AWS S3 bucket [bucket={bucket_name}, region={region or self.region}]")
        logging.info(f"[{action.value}] Created AWS S3 bucket [bucket={bucket_name}, region={region or self.region}]")
        return BucketEnsureResult(bucket_name=str(bucket_name), action=action.value, status="created", exists=True)

    def bucket_exists(self, bucket_name):
        try:
            self.s3.head_bucket(Bucket=bucket_name)
            return True
        except ClientError as e:
            error_code = str(e.response.get("Error", {}).get("Code", ""))
            if error_code in {"404", "NoSuchBucket", "NotFound"}:
                return False
            if error_code in {"301", "PermanentRedirect", "403", "AccessDenied"}:
                logging.warning(f"Treating bucket [{bucket_name}] as existing after head_bucket returned [{error_code}].")
                return True
            raise

    def ensure_prefix(self, bucket_name, prefix):
        """AWS S3 natively supports zero-byte directory stubs for nested keys, 
        but creating them explicitly is not required. S3 objects act as flat databases."""
        return True

    def cli_upload_file(self, source, bucket_name, dest, is_text=False):

        _cmd = f'aws s3 cp {source} "s3://{bucket_name}/{dest}" --profile {self.conf.aws_cli_profile}'

        if is_text:
            _cmd += ' --content-type "text/plain"'

        logging.info(f'Running command:\n{_cmd}')
        #would work in Windows?
        os.system(_cmd)

    def upload_file(self, source, bucket_name, dest, is_text=False, replace=False):

        with wu.open_data_path(source, "rb") as f:
            if is_text:
                self.s3.upload_fileobj(f, bucket_name, dest, ExtraArgs={'ContentType': 'text/plain'})
            else:
                self.s3.upload_fileobj(f, bucket_name, dest)

    def upload_string(self, string_data, bucket_name, dest):
        """Standard in-memory byte transfer explicitly to native S3."""
        self.s3.put_object(Body=string_data.encode('utf-8'), Bucket=bucket_name, Key=dest)

    def upload_directory(self, source, bucket_name, prefix):

        for root, dirs, files in wu.walk(source):
            for file in files:

                sub = root.replace(source, '')

                if sub == '/':
                    sub = ''
                else:
                    sub = f'{sub}/'

                dest = f'{prefix}{sub}{file}'
                print(dest)
                self.s3.upload_file(os.path.join(root, file), bucket_name, dest)

    def sync_directory(self, source, bucket_name, prefix):
        source_path = pathlib.Path(source).expanduser().resolve()
        if not source_path.is_dir():
            raise ValueError(f"AWSBucketeer.sync_directory expected a directory source, got: {source}")

        prefix = str(prefix).strip("/")
        uploaded_count = 0
        skipped_count = 0

        for local_path in sorted(source_path.rglob("*")):
            if not local_path.is_file():
                continue

            relative_key = local_path.relative_to(source_path).as_posix()
            dest_key = f"{prefix}/{relative_key}" if prefix else relative_key
            local_size = local_path.stat().st_size
            should_upload = True

            try:
                remote_head = self.s3.head_object(Bucket=bucket_name, Key=dest_key)
                remote_size = int(remote_head.get("ContentLength", -1))
                remote_etag = str(remote_head.get("ETag", "")).strip('"')
                if remote_size == local_size:
                    if not remote_etag or "-" in remote_etag or remote_etag == self._file_md5(local_path):
                        should_upload = False
            except ClientError as e:
                error_code = str(e.response.get("Error", {}).get("Code", ""))
                if error_code not in {"404", "NoSuchKey", "NotFound"}:
                    raise

            if should_upload:
                self.s3.upload_file(str(local_path), bucket_name, dest_key)
                uploaded_count += 1
            else:
                skipped_count += 1

        logging.info(
            "Synced local directory [%s] to [s3://%s/%s]: uploaded=[%d], skipped=[%d].",
            source_path,
            bucket_name,
            prefix,
            uploaded_count,
            skipped_count,
        )
        return True

    @staticmethod
    def _file_md5(path: pathlib.Path) -> str:
        digest = hashlib.md5()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @contextmanager
    def read_object_stream(self, bucket_name, key, name):
        full_key = f"{key}/{name}" if name else key
        response = self.s3.get_object(Bucket=bucket_name, Key=full_key)
        stream = io.TextIOWrapper(response["Body"], encoding="utf-8")
        try:
            yield stream
        finally:
            stream.close()

    def download_object(self, bucket_name, key, name, dest='/tmp'):
        """
        Download a chunk of objects

        :param key:
        :param name: the object's full key
        :param dest: local destination prefix
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """
        try:

            # print(name)

            # create nested directory structure
            wu.makedirs(dest, exist_ok=True)

            # save file with full path locally
            self.s3.download_file(bucket_name, f'{key}/{name}', f'{dest}/{name}')

        except ClientError as e:
            logging.error(e)
            # return False
        return True

    def cli_download_object(self, bucket_name, key, dest):

        _cmd = f'aws s3 cp "s3://{bucket_name}/{key}" {dest} --profile {self.conf.aws_cli_profile}'
        logging.info(f'Running command:\n{_cmd}')
        os.system(_cmd)

    def download_objects(self, bucket_name, keys, dest='/tmp'):
        """
        Download a chunk of objects

        :param keys:
        :param dest: local destination prefix
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """

        for key in tqdm(keys):

            obj_key_prefix = key[:key.rindex('/')]

            obj_name = key.split('/')[-1]
            logging.debug(f'obj_key_prefix: {obj_key_prefix}\nobj_name: {obj_name}')

            ok = self.download_object(bucket_name, obj_key_prefix, obj_name, dest)
            if not ok:
                return False

        return True

    def download_objects_flat_by_key(self, bucket_name, root_key='', dest='/tmp'):
        """
        Download objects below a key prefix directly into dest by basename.

        :param dest: local destination prefix
        :param root_key:
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """

        names = self.get_object_names(bucket_name, root_key)
        return self.download_objects(bucket_name, names, dest)

    def download_objects_tree_by_key(self, bucket_name, root_key='', dest='/tmp'):
        """
        Download objects below a key prefix into dest preserving relative paths.

        :param dest: local destination prefix
        :param root_key:
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """

        root_key = root_key.strip("/")
        object_keys = self.get_object_names(bucket_name, root_key)
        wu.makedirs(dest, exist_ok=True)

        for object_key in tqdm(object_keys):
            if root_key and object_key.startswith(f"{root_key}/"):
                relative_key = object_key[len(root_key) + 1:]
            else:
                relative_key = object_key

            local_path = os.path.join(dest, relative_key)
            wu.makedirs(os.path.dirname(local_path), exist_ok=True)
            self.s3.download_file(bucket_name, object_key, local_path)

        return True

    def download_objects_by_key(self, bucket_name, root_key='', dest='/tmp'):
        return self.download_objects_flat_by_key(bucket_name, root_key, dest)

    def delete_file(self, bucket_name, file_name):
        """Delete an S3 object
        :param file_name:
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """
        try:

            self.s3.delete_object(
                Bucket=bucket_name,
                Key=file_name
            )

        except ClientError as e:
            logging.error(e)
            return False
        return True

    def delete_objects(self, bucket_name, prefix=''):
        """Empty an S3 bucket

        :param prefix:
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """
        try:

            names = self.get_object_names(bucket_name, prefix)

            obs = [{'Key': n} for n in names]

            self.s3.delete_objects(
                Bucket=bucket_name,
                Delete={
                    'Objects': obs
                }
            )

        except ClientError as e:
            logging.error(e)
            return False
        return True

    def delete_bucket(self, bucket_name):
        """Delete an S3 bucket by emptying it and deleting the empty bucket.

        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """
        try:

            self.delete_objects(bucket_name)
            self.s3.delete_bucket(Bucket=bucket_name)

        except ClientError as e:
            logging.error(e)
            return False
        return True

    def get_bucket_names(self):
        """
        Retrieve a list of existing buckets.
        :return: list of bucket names
        """

        bucket_names = []

        response = self.s3.list_buckets()

        # Output the bucket names
        print('Existing buckets:')
        for bucket in response['Buckets']:
            bucket_names.append(bucket["Name"])
            print(f'  {bucket["Name"]}')

        return bucket_names

    def get_object_names(self, bucket_name, prefix=''):

        try:

            paginator = self.s3.get_paginator('list_objects_v2')
            response = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

            object_names = []

            for responses in response:
                s3objects = responses.get('Contents', [])
                for obj in s3objects:
                    object_name = obj["Key"].rstrip()
                    logging.debug(f'Object name: {object_name}')
                    object_names.append(object_name)

            return object_names

        except KeyError as e:
            logging.error(e)
            logging.info(f"No objects in key {prefix}")
            return []

    def object_exists(self, bucket_name, prefix, object_name):

        object_names = self.get_object_names(
            bucket_name=bucket_name,
            prefix=prefix
        ) or []

        if f'{prefix}/{object_name}' in object_names:
            return True

        return False

    def bucket_sync(self, source, dest, src_prefix, dest_prefix=None):

        if dest_prefix is None:
            dest_prefix = src_prefix

        _cmd = f'aws s3 sync "s3://{source}/{src_prefix}" "s3://{dest}/{dest_prefix}" --profile {self.conf.aws_cli_profile}'
        logging.info(f'Running command:\n{_cmd}')
        os.system(_cmd)

    def glob_keys(self, bucket_name, pattern, recursive=False):
        return super().glob_keys(bucket_name, pattern, recursive=recursive)


class GCSBucketeer(Bucketeer):
    """
    A native Google Cloud Storage Bucketeer.

    This is intentionally separate from GoogleBucketeer, which maps to Google
    Workspace Shared Drives.
    """

    def __init__(self, conf=None, auth=True):
        super().__init__(conf)
        try:
            from google.cloud import storage
        except ImportError as exc:
            raise ImportError(
                "GCSBucketeer requires the `google-cloud-storage` package. "
                "Install Wielder with its current dependencies before using the gcp_gcs ecosystem."
            ) from exc

        self.storage = storage
        project = conf.get("gcp.project", None) if conf is not None else None
        self.client = storage.Client(project=project)
        self.buckets_root = conf.get("buckets_root", "gs://") if conf is not None else "gs://"

    def _bucket(self, bucket_name):
        return self.client.bucket(bucket_name)

    def object_uri_by_key(self, bucket_name: str, object_key: str) -> str:
        return f"gs://{bucket_name}/{self.normalize_object_key(object_key)}"

    def object_view_url_by_key(self, bucket_name: str, object_key: str) -> str:
        key = quote(self.normalize_object_key(object_key), safe="/")
        return f"https://console.cloud.google.com/storage/browser/_details/{bucket_name}/{key}"

    def list_files_by_key(self, bucket_name, root_key):
        return self.get_object_names(bucket_name, root_key)

    def create_bucket(self, bucket_name, region=None):
        try:
            location = region
            if location is None and self.conf is not None:
                location = self.conf.get("gcp.location", None)
            if location is None:
                location = "US"

            bucket = self._bucket(bucket_name)
            self.client.create_bucket(bucket, location=location)
            return True
        except Exception as exc:
            logging.error(exc)
            return False

    def bucket_exists(self, bucket_name):
        return self.client.lookup_bucket(bucket_name) is not None

    def ensure_bucket(self, bucket_name, region=None, action=WieldAction.APPLY):
        action = action if isinstance(action, WieldAction) else WieldAction(str(action))
        try:
            exists = self.bucket_exists(bucket_name)
        except Exception as exc:
            raise RuntimeError(f"Failed to inspect GCS bucket [bucket={bucket_name}]: {exc}") from exc

        if exists:
            logging.info(f"[{action.value}] GCS bucket already exists [bucket={bucket_name}]")
            return BucketEnsureResult(bucket_name=str(bucket_name), action=action.value, status="exists", exists=True)

        if action != WieldAction.APPLY:
            logging.info(f"[{action.value}] Would create GCS bucket [bucket={bucket_name}]")
            return BucketEnsureResult(bucket_name=str(bucket_name), action=action.value, status="would_create", exists=False)

        created = self.create_bucket(bucket_name, region=region)
        if not created:
            raise RuntimeError(f"Failed to create GCS bucket [bucket={bucket_name}, location={region}]")
        logging.info(f"[{action.value}] Created GCS bucket [bucket={bucket_name}, location={region}]")
        return BucketEnsureResult(bucket_name=str(bucket_name), action=action.value, status="created", exists=True)

    def ensure_prefix(self, bucket_name, prefix):
        return True

    def cli_upload_file(self, source, bucket_name, dest, is_text=False):
        dest_key = self.normalize_object_key(dest)
        _cmd = f'gcloud storage cp "{source}" "gs://{bucket_name}/{dest_key}"'
        if is_text:
            _cmd += ' --content-type "text/plain"'
        logging.info(f'Running command:\n{_cmd}')
        os.system(_cmd)

    def upload_file(self, source, bucket_name, dest, is_text=False, replace=False):
        dest_key = self.normalize_object_key(dest)
        blob = self._bucket(bucket_name).blob(dest_key)
        content_type = "text/plain" if is_text else None
        blob.upload_from_filename(str(source), content_type=content_type)
        return True

    def upload_string(self, string_data, bucket_name, dest):
        dest_key = self.normalize_object_key(dest)
        self._bucket(bucket_name).blob(dest_key).upload_from_string(string_data)
        return True

    def upload_directory(self, source, bucket_name, prefix):
        return self.sync_directory(source, bucket_name, prefix)

    def sync_directory(self, source, bucket_name, prefix):
        source_path = pathlib.Path(source).expanduser().resolve()
        if not source_path.is_dir():
            raise ValueError(f"GCSBucketeer.sync_directory expected a directory source, got: {source}")

        prefix = self.normalize_object_key(prefix)
        bucket = self._bucket(bucket_name)
        remote_sizes = {blob.name: int(blob.size or 0) for blob in self.client.list_blobs(bucket_name, prefix=prefix)}
        uploaded_count = 0
        skipped_count = 0

        for local_path in sorted(source_path.rglob("*")):
            if not local_path.is_file():
                continue

            relative_key = local_path.relative_to(source_path).as_posix()
            dest_key = self.join_object_key(prefix, relative_key)
            if remote_sizes.get(dest_key) == local_path.stat().st_size:
                skipped_count += 1
                continue

            bucket.blob(dest_key).upload_from_filename(str(local_path))
            uploaded_count += 1

        logging.info(
            "Synced local directory [%s] to [gs://%s/%s]: uploaded=[%d], skipped=[%d].",
            source_path,
            bucket_name,
            prefix,
            uploaded_count,
            skipped_count,
        )
        return True

    @contextmanager
    def read_object_stream(self, bucket_name, key, name=None):
        object_key = self.join_object_key(key, name) if name else self.normalize_object_key(key)
        stream = io.StringIO(self._bucket(bucket_name).blob(object_key).download_as_text())
        try:
            yield stream
        finally:
            stream.close()

    def download_object(self, bucket_name, key, name, dest='/tmp'):
        object_key = self.join_object_key(key, name) if name else self.normalize_object_key(key)
        dest_path = pathlib.Path(dest)
        dest_path.mkdir(parents=True, exist_ok=True)
        target = dest_path / pathlib.PurePosixPath(object_key).name
        self._bucket(bucket_name).blob(object_key).download_to_filename(str(target))
        return True

    def cli_download_object(self, bucket_name, key, dest):
        object_key = self.normalize_object_key(key)
        _cmd = f'gcloud storage cp "gs://{bucket_name}/{object_key}" "{dest}"'
        logging.info(f'Running command:\n{_cmd}')
        os.system(_cmd)

    def download_objects(self, bucket_name, keys, dest='/tmp'):
        for key in tqdm(keys):
            self.download_object(bucket_name, key, None, dest=dest)
        return True

    def download_objects_flat_by_key(self, bucket_name, root_key='', dest='/tmp'):
        return self.download_objects(bucket_name, self.get_object_names(bucket_name, root_key), dest)

    def download_objects_tree_by_key(self, bucket_name, root_key='', dest='/tmp'):
        root_key = self.normalize_object_key(root_key)
        dest_path = pathlib.Path(dest)
        dest_path.mkdir(parents=True, exist_ok=True)

        for object_key in tqdm(self.get_object_names(bucket_name, root_key)):
            if root_key and object_key.startswith(f"{root_key}/"):
                relative_key = object_key[len(root_key) + 1:]
            else:
                relative_key = object_key
            target = dest_path.joinpath(*pathlib.PurePosixPath(relative_key).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            self._bucket(bucket_name).blob(object_key).download_to_filename(str(target))

        return True

    def download_objects_by_key(self, bucket_name, root_key='', dest='/tmp'):
        return self.download_objects_flat_by_key(bucket_name, root_key, dest)

    def delete_file(self, bucket_name, file_name):
        self._bucket(bucket_name).blob(self.normalize_object_key(file_name)).delete()
        return True

    def delete_objects(self, bucket_name, prefix=''):
        for blob in self.client.list_blobs(bucket_name, prefix=self.normalize_object_key(prefix)):
            blob.delete()
        return True

    def delete_bucket(self, bucket_name):
        bucket = self._bucket(bucket_name)
        for blob in self.client.list_blobs(bucket_name):
            blob.delete()
        bucket.delete()
        return True

    def get_bucket_names(self):
        return [bucket.name for bucket in self.client.list_buckets()]

    def get_object_names(self, bucket_name, prefix=''):
        normalized_prefix = self.normalize_object_key(prefix)
        return [blob.name for blob in self.client.list_blobs(bucket_name, prefix=normalized_prefix)]

    def object_exists(self, bucket_name, prefix, object_name):
        object_key = self.join_object_key(prefix, object_name)
        return self._bucket(bucket_name).blob(object_key).exists(self.client)

    def bucket_sync(self, src_bucket, dest_bucket, src_prefix, dest_prefix):
        source_prefix = self.normalize_object_key(src_prefix)
        target_prefix = self.normalize_object_key(dest_prefix)
        source_bucket = self._bucket(src_bucket)
        target_bucket = self._bucket(dest_bucket)

        for source_blob in self.client.list_blobs(src_bucket, prefix=source_prefix):
            if source_prefix and source_blob.name.startswith(f"{source_prefix}/"):
                relative_key = source_blob.name[len(source_prefix) + 1:]
            else:
                relative_key = source_blob.name
            target_key = self.join_object_key(target_prefix, relative_key)
            source_bucket.copy_blob(source_blob, target_bucket, target_key)

        return True

    def glob_keys(self, bucket_name, pattern, recursive=False):
        return super().glob_keys(bucket_name, pattern, recursive=recursive)


class GoogleBucketeer(Bucketeer):
    """
    A mock bucket object
    The class emulates a cloud bucket by performing similar functionality on
    A directory
    """

    def list_files_by_key(self, bucket_name, root_key):
        return list(self.iter_files_by_key(bucket_name, root_key))

    def __init__(self, conf=None, auth=True):

        super().__init__(conf)

        self.service = service_login(conf)

    def object_uri_by_key(self, bucket_name: str, object_key: str) -> str:
        return f"Google Shared Drive: {bucket_name}/{self.normalize_object_key(object_key)}"

    def object_view_url_by_key(self, bucket_name: str, object_key: str) -> str:
        normalized_key = self.normalize_object_key(object_key)
        prefix, object_name = normalized_key.rsplit("/", 1) if "/" in normalized_key else ("", normalized_key)
        parent_id = self.ensure_prefix(bucket_name, prefix, action=WieldAction.PLAN)
        if not parent_id:
            return self.object_uri_by_key(bucket_name, normalized_key)
        file_ids = self._get_file_ids_by_name(object_name, parent_id)
        if file_ids:
            return f"https://drive.google.com/file/d/{file_ids[0]}/view"
        return f"https://drive.google.com/drive/folders/{parent_id}"

    def _get_folder_id(self, folder_name, parent_id="root"):
        """ Recursive lookup: fetches the UUID of a child folder specifically within a parent UUID """
        query = f"name='{folder_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        folder_list = self.service.files().list(q=query, spaces="drive", fields="nextPageToken, files(id, name, mimeType)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        files = folder_list.get('files', [])
        if not files:
            return None
        return files[0]['id']

    def get_size_format(b, factor=1024, suffix="B"):
        """
        Scale bytes to its proper byte format
        e.g:
            1253656 => '1.20MB'
            1253656678 => '1.17GB'
        """
        for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
            if b < factor:
                return f"{b:.2f}{unit}{suffix}"
            b /= factor
        return f"{b:.2f}Y{suffix}"

    def list_files(self, items):
        """given items returned by Google Drive API, prints them in a tabular way"""
        if not items:
            return "No files available."
        else:
            rows = []
            for item in items:
                id = item["id"]
                name = item["name"]
                try:
                    parents = item["parents"]
                except:
                    parents = "N/A"
                try:
                    size = self.get_size_format(int(item["size"]))
                except:
                    size = "N/A"
                mime_type = item["mimeType"]
                modified_time = item["modifiedTime"]
                rows.append((id, name, parents, size, mime_type, modified_time))
            return tabulate(rows, headers=["ID", "Name", "Parents", "Size", "Type", "Modified Time"])

    def get_bucket_names(self):
        """Returns a list of all Shared Drives available to the authenticated service."""
        response = self.service.drives().list().execute()
        return [drive['name'] for drive in response.get('drives', [])]

    def bucket_exists(self, bucket_name):
        """Checks if a Shared Drive exactly matching the bucket_name exists."""
        folder_id = self._configured_folder_id(bucket_name)
        if folder_id:
            try:
                item = self.service.files().get(
                    fileId=folder_id,
                    fields="id, mimeType, trashed",
                    supportsAllDrives=True,
                ).execute()
            except HttpError:
                return False
            return (
                item.get("mimeType") == "application/vnd.google-apps.folder"
                and not item.get("trashed", False)
            )
        return self.get_bucket_id(bucket_name) is not None

    def get_bucket_id(self, bucket_name):
        """Returns the Shared Drive ID for an exact bucket_name match, or None."""
        query = f"name='{bucket_name}'"
        page_token = None
        while True:
            response = self.service.drives().list(
                q=query,
                fields="nextPageToken, drives(id, name)",
                pageToken=page_token,
            ).execute()
            for drive in response.get('drives', []):
                if drive.get('name') == bucket_name and drive.get('id'):
                    return drive.get('id')
            page_token = response.get("nextPageToken")
            if not page_token:
                return None

    def create_bucket(self, bucket_name, region=None):
        """Creates a Google Workspace Shared Drive natively substituting the S3 concept."""
        request_id = str(uuid.uuid4())
        body = {'name': bucket_name}
        try:
            drive = self.service.drives().create(
                requestId=request_id,
                body=body,
                fields="id, name",
            ).execute()
            logging.info(f"Shared Drive '{bucket_name}' natively provisioned with ID: {drive.get('id')}")
            return drive
        except Exception as e:
            logging.error(f"Failed to bootstrap Google Shared Drive '{bucket_name}': {e}")
            return False

    def ensure_bucket(self, bucket_name, region=None, action=WieldAction.APPLY):
        """
        Idempotently plan or create a Google Workspace Shared Drive.

        :return: GoogleDriveBucketEnsureResult. It is truthy when a drive_id is
            available and falsey when PLAN detected missing state without mutation.
        """
        action = self._coerce_permission_action(action)
        try:
            drive_id = self.get_bucket_id(bucket_name)
        except HttpError as error:
            raise RuntimeError(f"Failed to inspect Google Shared Drive [bucket={bucket_name}]: {error}") from error

        if drive_id:
            logging.info(f"[{action.value}] Google Shared Drive already exists [bucket={bucket_name}, drive_id={drive_id}]")
            return GoogleDriveBucketEnsureResult(
                bucket_name=str(bucket_name),
                action=action.value,
                status="exists",
                drive_id=str(drive_id),
            )

        if action != WieldAction.APPLY:
            logging.info(f"[{action.value}] Would create Google Shared Drive [bucket={bucket_name}]")
            return GoogleDriveBucketEnsureResult(
                bucket_name=str(bucket_name),
                action=action.value,
                status="would_create",
            )

        created = self.create_bucket(bucket_name, region=region)
        if not created:
            raise RuntimeError(f"Failed to create Google Shared Drive [bucket={bucket_name}]")
        drive_id = created.get("id") if isinstance(created, dict) else None
        if not drive_id:
            drive_id = self.get_bucket_id(bucket_name)
        if not drive_id:
            raise RuntimeError(f"Created Google Shared Drive but could not resolve ID [bucket={bucket_name}]")
        logging.info(f"[{action.value}] Created Google Shared Drive [bucket={bucket_name}, drive_id={drive_id}]")
        return GoogleDriveBucketEnsureResult(
            bucket_name=str(bucket_name),
            action=action.value,
            status="created",
            drive_id=str(drive_id),
        )

    def ensure_permission(
        self,
        file_id,
        role,
        permission_type,
        email=None,
        send_notification_email=False,
        action=WieldAction.APPLY,
    ):
        """
        Idempotently grant a Google Drive permission to a file, folder, or Shared Drive root.

        :param file_id: Google Drive file/folder ID or Shared Drive ID.
        :param role: Google Drive role, e.g. reader, writer.
        :param permission_type: Google Drive permission type, e.g. user, group, domain.
        :param email: Email address for user/group permissions.
        :param send_notification_email: Whether Google should email the grantee.
        :param action: Wielder action. PLAN reports intended changes, APPLY mutates.
        :return: GoogleDrivePermissionEnsureResult.
        """
        action = self._coerce_permission_action(action)
        permission_body = {
            "role": str(role),
            "type": str(permission_type),
        }
        if email:
            permission_body["emailAddress"] = str(email)

        context = self._permission_context(file_id=file_id, permission=permission_body)
        try:
            matching_permission = self._find_permission(
                file_id=file_id,
                permission_type=permission_body["type"],
                email=permission_body.get("emailAddress"),
            )
        except HttpError as error:
            raise RuntimeError(f"Failed to inspect {context}: {error}") from error

        if matching_permission:
            permission_id = matching_permission["id"]
            if matching_permission.get("role") == permission_body["role"]:
                logging.info(f"[{action.value}] Google Drive permission already satisfies plan: {context}")
                return GoogleDrivePermissionEnsureResult(
                    file_id=str(file_id),
                    role=permission_body["role"],
                    permission_type=permission_body["type"],
                    email=permission_body.get("emailAddress"),
                    action=action.value,
                    status="exists",
                    permission_id=permission_id,
                )
            if action != WieldAction.APPLY:
                logging.info(
                    f"[{action.value}] Would update Google Drive permission: "
                    f"{context}; current_role=[{matching_permission.get('role')}]"
                )
                return GoogleDrivePermissionEnsureResult(
                    file_id=str(file_id),
                    role=permission_body["role"],
                    permission_type=permission_body["type"],
                    email=permission_body.get("emailAddress"),
                    action=action.value,
                    status="would_update",
                    permission_id=permission_id,
                    previous_role=matching_permission.get("role"),
                )
            try:
                updated = self.service.permissions().update(
                    fileId=file_id,
                    permissionId=permission_id,
                    body={"role": permission_body["role"]},
                    supportsAllDrives=True,
                ).execute()
                logging.info(
                    f"[{action.value}] Updated Google Drive permission: "
                    f"{context}; previous_role=[{matching_permission.get('role')}]"
                )
                return GoogleDrivePermissionEnsureResult(
                    file_id=str(file_id),
                    role=permission_body["role"],
                    permission_type=permission_body["type"],
                    email=permission_body.get("emailAddress"),
                    action=action.value,
                    status="updated",
                    permission_id=updated.get("id", permission_id),
                    previous_role=matching_permission.get("role"),
                )
            except HttpError as error:
                raise RuntimeError(
                    f"Failed to update Google Drive permission: {context}; "
                    f"permission_id=[{permission_id}]; previous_role=[{matching_permission.get('role')}]: {error}"
                ) from error

        if action != WieldAction.APPLY:
            logging.info(f"[{action.value}] Would grant Google Drive permission: {context}")
            return GoogleDrivePermissionEnsureResult(
                file_id=str(file_id),
                role=permission_body["role"],
                permission_type=permission_body["type"],
                email=permission_body.get("emailAddress"),
                action=action.value,
                status="would_create",
            )

        try:
            created = self.service.permissions().create(
                fileId=file_id,
                body=permission_body,
                supportsAllDrives=True,
                sendNotificationEmail=send_notification_email,
            ).execute()
            logging.info(f"[{action.value}] Granted Google Drive permission: {context}")
            return GoogleDrivePermissionEnsureResult(
                file_id=str(file_id),
                role=permission_body["role"],
                permission_type=permission_body["type"],
                email=permission_body.get("emailAddress"),
                action=action.value,
                status="created",
                permission_id=created.get("id"),
            )
        except HttpError as error:
            if error.resp.status == 409:
                matching_permission = self._find_permission(
                    file_id=file_id,
                    permission_type=permission_body["type"],
                    email=permission_body.get("emailAddress"),
                )
                if matching_permission:
                    logging.info(f"[{action.value}] Google Drive permission already exists after conflict: {context}")
                    return GoogleDrivePermissionEnsureResult(
                        file_id=str(file_id),
                        role=permission_body["role"],
                        permission_type=permission_body["type"],
                        email=permission_body.get("emailAddress"),
                        action=action.value,
                        status="exists",
                        permission_id=matching_permission.get("id"),
                        previous_role=matching_permission.get("role"),
                    )
            raise RuntimeError(f"Failed to grant Google Drive permission: {context}: {error}") from error

    def ensure_permissions(self, file_id, permissions, send_notification_email=False, action=WieldAction.APPLY):
        """
        Idempotently grant a list of Google Drive permissions.

        Each item may be a dict-like object with role/type/emailAddress or
        role/type/email fields, or a tuple of (role, type, email).
        """
        action = self._coerce_permission_action(action)
        results = []
        for permission in permissions:
            role, permission_type, email = self._normalize_permission(permission)
            results.append(
                self.ensure_permission(
                    file_id=file_id,
                    role=role,
                    permission_type=permission_type,
                    email=email,
                    send_notification_email=send_notification_email,
                    action=action,
                )
            )
        return results

    def _find_permission(self, file_id, permission_type, email=None):
        page_token = None
        while True:
            response = self.service.permissions().list(
                fileId=file_id,
                supportsAllDrives=True,
                fields="nextPageToken, permissions(id, role, type, emailAddress, domain)",
                pageToken=page_token,
            ).execute()
            for permission in response.get("permissions", []):
                if permission.get("type") != permission_type:
                    continue
                if email and permission.get("emailAddress") != email:
                    continue
                return permission
            page_token = response.get("nextPageToken")
            if not page_token:
                return None

    def _normalize_permission(self, permission):
        if isinstance(permission, tuple):
            if len(permission) != 3:
                raise ValueError(f"Expected permission tuple of (role, type, email), got: {permission}")
            return permission

        role = permission.get("role")
        permission_type = permission.get("type")
        email = permission.get("emailAddress", permission.get("email"))
        if not role or not permission_type:
            raise ValueError(f"Google Drive permission requires role and type: {permission}")
        return str(role), str(permission_type), str(email) if email else None

    def _coerce_permission_action(self, action):
        if isinstance(action, WieldAction):
            return action
        return WieldAction(str(action))

    def _permission_context(self, file_id, permission):
        context = (
            f"file_id=[{file_id}] role=[{permission.get('role')}] "
            f"type=[{permission.get('type')}]"
        )
        if permission.get("emailAddress"):
            context = f"{context} email=[{permission.get('emailAddress')}]"
        return context

    def delete_bucket(self, bucket_name):
        """Finds and natively purges the Shared Drive exactly matching the bucket_name."""
        query = f"name='{bucket_name}'"
        response = self.service.drives().list(q=query).execute()
        drives = response.get('drives', [])
        
        if not drives:
            logging.warning(f"Cannot teardown Drive '{bucket_name}', not found.")
            return False
            
        for drive in drives:
            try:
                self.service.drives().delete(driveId=drive['id']).execute()
                logging.info(f"Purged Google Shared Drive: '{bucket_name}' (ID: {drive['id']})")
            except Exception as e:
                logging.error(f"Failed to delete Google Shared Drive '{bucket_name}': {e}")
                return False
        return True

    def cli_upload_file(self, source, bucket_name, dest, is_text=False):
        pass

    def create_folder(self, folder_name, parent_id="root"):
        """ Create a folder and returns the folder ID """
        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }

            file = self.service.files().create(body=file_metadata, fields='id', supportsAllDrives=True).execute()
            return file.get('id')

        except HttpError as error:
            print(f'An error occurred: {error}')
            return None

    def ensure_prefix(self, bucket_name, prefix, action=WieldAction.APPLY):
        """
        Recursively maps a nested UNIX NoSQL key string (e.g. 'biolab/reports/pdf') 
        onto the Google Workspace topology, drilling down and creating missing intermediate 
        folder UUIDs dynamically.
        """
        action = self._coerce_permission_action(action)
        # 1. Resolve Root Bucket UUID natively from PyHocon, a configured folder URL/id, or dynamically from Google API.
        bucket_id = self._configured_folder_id(bucket_name)
        if not bucket_id:
            # Fallback to dynamically sourcing the UUID directly from the Cloud API
            try:
                response = self.service.drives().list().execute()
                drives = response.get('drives', [])
                matched_drives = [d for d in drives if d['name'] == bucket_name]
            except HttpError as error:
                raise RuntimeError(f"Failed to inspect Google Shared Drive [{bucket_name}]: {error}") from error
            
            if not matched_drives:
                raise Exception(f"Google Shared Drive '{bucket_name}' not found statically in PyHocon tracking OR natively within the active Cloud Workspace!")
                
            bucket_id = matched_drives[0]['id']
            
        current_parent = bucket_id
        
        # 2. Walk the prefix topology
        if prefix:
            parts = [p for p in str(prefix).split('/') if p]
            for part in parts:
                try:
                    child_id = self._get_folder_id(part, current_parent)
                except HttpError as error:
                    raise RuntimeError(
                        f"Failed to inspect Google Drive prefix part "
                        f"[bucket={bucket_name}, prefix={prefix}, part={part}, parent_id={current_parent}]: {error}"
                    ) from error
                if not child_id:
                    if action != WieldAction.APPLY:
                        logging.info(
                            f"[{action.value}] Would create Google Drive prefix part "
                            f"[bucket={bucket_name}, prefix={prefix}, part={part}, parent_id={current_parent}]"
                        )
                        return None
                    child_id = self.create_folder(part, current_parent)
                    if not child_id:
                        raise RuntimeError(
                            f"Failed to create Google Drive prefix part "
                            f"[bucket={bucket_name}, prefix={prefix}, part={part}, parent_id={current_parent}]"
                        )
                    logging.info(
                        f"[{action.value}] Created Google Drive prefix part "
                        f"[bucket={bucket_name}, prefix={prefix}, part={part}, folder_id={child_id}]"
                    )
                current_parent = child_id
                
        return current_parent

    def _configured_folder_id(self, bucket_name):
        try:
            configured = self.conf.buckets.google_drive[bucket_name]
        except Exception:
            configured = bucket_name
        return self._drive_folder_id_from_text(str(configured))

    def _drive_folder_id_from_text(self, value):
        text = str(value).strip()
        if not text:
            return None
        match = re.search(r"/folders/([^/?#]+)", text)
        if match:
            return match.group(1)
        if re.fullmatch(r"[A-Za-z0-9_-]{20,}", text):
            return text
        return None

    def upload_file(self, source, bucket_name, dest, is_text=False, replace=False):
        # Dest is natively the full NoSQL key (e.g., 'biolab/files/report.pdf')
        dest = dest.strip('/')
        if '/' in dest:
            prefix, file_name = dest.rsplit('/', 1)
        else:
            prefix = ""
            file_name = dest
            
        folder_id = self.ensure_prefix(bucket_name, prefix)
        if replace:
            existing_file_ids = self._get_file_ids_by_name(file_name, folder_id)
            if existing_file_ids:
                file = MediaFileUpload(f'{source}', resumable=True)
                updated_file = self.service.files().update(
                    fileId=existing_file_ids[0],
                    media_body=file,
                    fields='id, name, webViewLink',
                    supportsAllDrives=True,
                ).execute()
                for duplicate_file_id in existing_file_ids[1:]:
                    self.service.files().delete(fileId=duplicate_file_id, supportsAllDrives=True).execute()
                print("File updated, id:", updated_file.get("id"))
                if updated_file.get("webViewLink"):
                    print("File link:", updated_file.get("webViewLink"))
                return updated_file
        
        file = MediaFileUpload(f'{source}', resumable=True)

        file_metadata = {'name': file_name, "parents": [folder_id]}
        file = self.service.files().create(
            body=file_metadata,
            media_body=file,
            fields='id, name, webViewLink',
            supportsAllDrives=True,
        ).execute()
        print("File created, id:", file.get("id"))
        if file.get("webViewLink"):
            print("File link:", file.get("webViewLink"))

        return file

    def upload_string(self, string_data, bucket_name, dest):
        dest = self.normalize_object_key(dest)
        prefix, file_name = dest.rsplit('/', 1) if '/' in dest else ("", dest)
        folder_id = self.ensure_prefix(bucket_name, prefix)
        media = MediaIoBaseUpload(io.BytesIO(string_data.encode("utf-8")), mimetype="text/plain", resumable=True)
        file_metadata = {'name': file_name, "parents": [folder_id]}
        self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True,
        ).execute()
        return True

    def upload_directory(self, source, bucket_name, prefix):
        print(f"Executing GoogleBucketeer.upload_directory: Cannot blindly push directory - use sync_directory for recursive uploads.")
        pass
        
    def sync_directory(self, source, bucket_name, dest_prefix):
        """
        Recursively uploads a local directory to Google Drive.
        Uses idempotent caching to avoid duplicate uploads of identical filenames.
        """
        import os
        from wielder.util.util import DirContext
        
        source_dir = os.path.abspath(source)
        if not os.path.isdir(source_dir):
            print(f"Source {source_dir} is not a valid directory.")
            return False
            
        print(f"Syncing local directory {source_dir} -> Google Drive bucket {bucket_name} at prefix {dest_prefix}")
        
        uploaded_count = 0
        skipped_count = 0
        
        # Traverse local tree
        for root, dirs, files in os.walk(source_dir):
            if not files:
                continue
                
            # Calculate the relative offset from the source root to build the remote topology
            rel_path = os.path.relpath(root, source_dir)
            
            # Construct the exact NoSQL logical prefix for this specific branch
            if rel_path == ".":
                branch_prefix = dest_prefix
            else:
                branch_prefix = f"{dest_prefix}/{rel_path}".replace("\\", "/")
                
            # Ensure the specific remote directory wrapper exists and fetch its UUID
            branch_id = self.ensure_prefix(bucket_name, branch_prefix)
            
            # Query the Google API once for this specific branch to get all existing file names
            query = f"'{branch_id}' in parents and trashed=false"
            folder_list = self.service.files().list(q=query, spaces="drive", fields="nextPageToken, files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
            
            existing_files = {item['name'] for item in folder_list.get('files', [])}
            
            # Selectively upload local files
            for file_name in files:
                local_file = os.path.join(root, file_name)
                
                if file_name in existing_files:
                    print(f"  [SKIP] {file_name} already exists in {branch_prefix}")
                    skipped_count += 1
                else:
                    print(f"  [UPLOAD] {file_name} -> {branch_prefix}")
                    # Directly upload explicitly to the pre-resolved UUID using native payload mapping
                    file_media = MediaFileUpload(local_file, resumable=True)
                    file_metadata = {'name': file_name, "parents": [branch_id]}
                    self.service.files().create(body=file_metadata, media_body=file_media, fields='id', supportsAllDrives=True).execute()
                    uploaded_count += 1
                    
        print(f"Sync Complete: {uploaded_count} Uploaded, {skipped_count} Skipped.")
        return True

    @contextmanager
    def read_object_stream(self, bucket_name, key, name):
        # TODO: Implement in-memory stream natively for GCP Storage
        raise NotImplementedError("GoogleBucketeer native byte-streaming not explicitly implemented yet.")

    def download_object(self, bucket_name, key, name, dest='/tmp'):
        object_key = self.join_object_key(key, name) if name else self.normalize_object_key(key)
        prefix, object_name = object_key.rsplit('/', 1) if '/' in object_key else ("", object_key)
        parent_id = self.ensure_prefix(bucket_name, prefix, action=WieldAction.PLAN)
        if not parent_id:
            raise FileNotFoundError(f"Google Drive prefix not found [bucket={bucket_name}, prefix={prefix}]")
        file_ids = self._get_file_ids_by_name(object_name, parent_id)
        if not file_ids:
            raise FileNotFoundError(f"Google Drive object not found [bucket={bucket_name}, key={object_key}]")

        wu.makedirs(dest, exist_ok=True)
        target = pathlib.Path(dest) / object_name
        if target.exists():
            target.unlink()
        request = self.service.files().get_media(fileId=file_ids[0], supportsAllDrives=True)
        with target.open("wb") as handle:
            downloader = MediaIoBaseDownload(handle, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        return True

    def cli_download_object(self, bucket_name, key, dest):
        pass

    def download_objects(self, bucket_name, names, dest='/tmp'):
        """

        Copies a list of files to a destination to mimic downloading objects

        :param dest: local destination prefix
        :param names: list of files
        :param bucket_name: Bucket
        :return: True
        """

        wu.makedirs(dest, exist_ok=True)

        for name in names:

            dest1 = f'{dest}/{name}'

            wu.remove(dest1)

            src = f'{bucket_name}/{name}'
            wu.copyfile(src, dest)

    def download_objects_flat_by_key(self, bucket_name, root_key='', dest='/tmp'):
        """
        Copies files below a prefix directly into dest by basename.

        :param dest: local destination prefix
        :param root_key:
        :param bucket_name: Bucket
        :return: True
        """
        object_names = self.get_object_names(bucket_name, root_key)
        wu.makedirs(dest, exist_ok=True)

        for object_name in object_names:
            if hasattr(object_name, "name"):
                object_name = str(object_name.name)
            else:
                object_name = str(object_name).rstrip("/")
                object_name = object_name.split("/")[-1]
            src = f'{self.buckets_root}/{bucket_name}/{root_key}/{object_name}'
            if wu.isfile(src):
                wu.copy(src, dest)

        return True

    def download_objects_tree_by_key(self, bucket_name, root_key='', dest='/tmp'):
        """
        Copies A directory emulating download of a chunk of objects from cloud bucket

        :param dest: local destination prefix
        :param root_key:
        :param bucket_name: Bucket
        :return: True
        """
        wu.rmtree(dest, ignore_errors=True)
        wu.copytree(f'{self.buckets_root}/{bucket_name}/{root_key}', dest)

        return True

    def download_objects_by_key(self, bucket_name, root_key='', dest='/tmp'):
        return self.download_objects_tree_by_key(bucket_name, root_key, dest)

    def delete_file(self, bucket_name, file_name):
        """Delete a Google Shared Drive object by semantic key."""
        object_key = self.normalize_object_key(file_name)
        prefix, object_name = object_key.rsplit('/', 1) if '/' in object_key else ("", object_key)
        parent_id = self.ensure_prefix(bucket_name, prefix, action=WieldAction.PLAN)
        if not parent_id:
            return True
        for file_id in self._get_file_ids_by_name(object_name, parent_id):
            self.service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
        return True

    def delete_objects(self, bucket_name, prefix=''):
        """Empty a local Dir emulating a bucket

        :param prefix:
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """
        wu.rmtree(f'{self.buckets_root}/{bucket_name}/{prefix}', ignore_errors=True)

        return True



    def get_object_names(self, bucket_name, prefix=''):
        parent_id = self.ensure_prefix(bucket_name, self.normalize_object_key(prefix), action=WieldAction.PLAN)
        if not parent_id:
            return []
        page_token = None
        names = []
        while True:
            response = self.service.files().list(
                q=f"'{parent_id}' in parents and trashed=false",
                spaces="drive",
                fields="nextPageToken, files(name)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageToken=page_token,
            ).execute()
            names.extend(item["name"] for item in response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                return names

    def get_object_names_recursive(self, bucket_name, prefix=''):
        return list(self.iter_files_by_key(bucket_name, prefix))

    def iter_file_records_by_name_suffix(self, bucket_name, suffix, root_key=''):
        bucket_id = self.get_bucket_id(bucket_name)
        if not bucket_id:
            raise RuntimeError(f"Google Shared Drive [{bucket_name}] does not exist.")
        root_key = self.normalize_object_key(root_key)
        metadata_cache = {bucket_id: {"id": bucket_id, "name": "", "parents": []}}
        page_token = None
        seen = 0
        while True:
            response = self.service.files().list(
                q=(
                    f"name contains '{suffix}' and trashed=false "
                    "and mimeType!='application/vnd.google-apps.folder'"
                ),
                corpora="drive",
                driveId=bucket_id,
                spaces="drive",
                fields="nextPageToken, files(id, name, parents, mimeType)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageToken=page_token,
            ).execute()
            for item in response.get("files", []):
                if not str(item.get("name", "")).endswith(str(suffix)):
                    continue
                key = self._drive_item_key(item, bucket_id, metadata_cache)
                if root_key and key != root_key and not key.startswith(f"{root_key}/"):
                    continue
                seen += 1
                logging.info("Matched Google Drive suffix [%s] object [%d]: %s", suffix, seen, key)
                yield {"id": item["id"], "key": key, "name": item["name"]}
            page_token = response.get("nextPageToken")
            if not page_token:
                return

    def iter_files_by_name_suffix(self, bucket_name, suffix, root_key=''):
        for record in self.iter_file_records_by_name_suffix(bucket_name, suffix, root_key=root_key):
            yield record["key"]

    def delete_file_id(self, file_id):
        self.service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
        return True

    def _drive_item_key(self, item, bucket_id, metadata_cache):
        parts = [item["name"]]
        parent_id = (item.get("parents") or [None])[0]
        while parent_id and parent_id != bucket_id:
            parent = self._drive_file_metadata(parent_id, metadata_cache)
            parent_name = parent.get("name")
            if parent_name:
                parts.append(parent_name)
            parent_id = (parent.get("parents") or [None])[0]
        return self.join_object_key(*reversed(parts))

    def _drive_file_metadata(self, file_id, metadata_cache):
        if file_id not in metadata_cache:
            metadata_cache[file_id] = self.service.files().get(
                fileId=file_id,
                fields="id, name, parents, mimeType",
                supportsAllDrives=True,
            ).execute()
        return metadata_cache[file_id]

    def iter_files_by_key(self, bucket_name, root_key):
        root_key = self.normalize_object_key(root_key)
        parent_id = self.ensure_prefix(bucket_name, root_key, action=WieldAction.PLAN)
        if not parent_id:
            return
        stats = {"folders": 0, "files": 0}
        yield from self._iter_object_names_recursive(parent_id, root_key, stats)
        logging.info(
            "Finished Google Drive recursive listing [bucket=%s, prefix=%s, folders=%d, files=%d].",
            bucket_name,
            root_key,
            stats["folders"],
            stats["files"],
        )

    def _iter_object_names_recursive(self, parent_id, parent_key, stats=None):
        stats = stats if stats is not None else {"folders": 0, "files": 0}
        stats["folders"] += 1
        if stats["folders"] == 1 or stats["folders"] % 100 == 0:
            logging.info(
                "Walking Google Drive folder [folders=%d, files=%d, key=%s].",
                stats["folders"],
                stats["files"],
                parent_key or "/",
            )
        page_token = None
        while True:
            response = self.service.files().list(
                q=f"'{parent_id}' in parents and trashed=false",
                spaces="drive",
                fields="nextPageToken, files(id, name, mimeType)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageToken=page_token,
            ).execute()
            for item in response.get("files", []):
                item_key = self.join_object_key(parent_key, item["name"])
                if item.get("mimeType") == "application/vnd.google-apps.folder":
                    yield from self._iter_object_names_recursive(item["id"], item_key, stats)
                else:
                    stats["files"] += 1
                    if stats["files"] % 1000 == 0:
                        logging.info(
                            "Listed Google Drive files [folders=%d, files=%d, latest=%s].",
                            stats["folders"],
                            stats["files"],
                            item_key,
                        )
                    yield item_key
            page_token = response.get("nextPageToken")
            if not page_token:
                return

    def object_exists(self, bucket_name, prefix, object_name):
        parent_id = self.ensure_prefix(bucket_name, self.normalize_object_key(prefix), action=WieldAction.PLAN)
        if not parent_id:
            return False
        return bool(self._get_file_ids_by_name(str(object_name), parent_id))

    def _get_file_ids_by_name(self, file_name, parent_id):
        query = (
            f"name='{str(file_name)}' and '{parent_id}' in parents "
            "and mimeType!='application/vnd.google-apps.folder' and trashed=false"
        )
        page_token = None
        file_ids = []
        while True:
            response = self.service.files().list(
                q=query,
                spaces="drive",
                fields="nextPageToken, files(id)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageToken=page_token,
            ).execute()
            file_ids.extend(item["id"] for item in response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                return file_ids

    def bucket_sync(self, src_bucket, dest_bucket, src_prefix, dest_prefix):
        # TODO: Fill function
        pass

    def glob_keys(self, bucket_name, pattern, recursive=False):
        return super().glob_keys(bucket_name, pattern, recursive=recursive)


class DevBucketeer(Bucketeer):
    """
    A mock bucket object
    The class emulates a cloud bucket by performing similar functionality on
    A directory
    """

    def __init__(self, conf=None):

        super().__init__(conf)

        self.buckets_root = conf.buckets_root
            
        self.default_bucket = conf.namespace_bucket

    def object_uri_by_key(self, bucket_name: str, object_key: str) -> str:
        return f"{self.buckets_root}/{bucket_name}/{self.normalize_object_key(object_key)}"

    def bucket_exists(self, bucket_name):
        """Validates if the local mockup Drive directory evaluates as active natively."""
        return bucket_name in self.get_bucket_names()

    def create_bucket(self, bucket_name, region=None):
        """Create a local directory to emulate cloud bucket behavior

        :param bucket_name: Bucket to create
        :param region: Ignored but kept to save interface compatibility
        :return: True if bucket created, else False
        """
        wu.makedirs(f'{self.buckets_root}/{bucket_name}', exist_ok=True)

        return True

    def ensure_prefix(self, bucket_name, prefix):
        """Natively converts the abstract NoSQL key into a physical UNIX directory trace."""
        wu.makedirs(f'{self.buckets_root}/{bucket_name}/{prefix}', exist_ok=True)
        return True

    def cli_upload_file(self, source, bucket_name, dest, is_text=False):
        pass

    def upload_file(self, source, bucket_name, dest, is_text=False, replace=False):

        dir_key = dest[:dest.rfind('/')] if '/' in dest else ''
        self.ensure_prefix(bucket_name, dir_key)

        wu.copy(source, f'{self.buckets_root}/{bucket_name}/{dest}')

    def upload_string(self, string_data, bucket_name, dest):
        """Dumps purely in-memory logical strings securely natively utilizing standard OS overrides."""
        dir_key = dest[:dest.rfind('/')] if '/' in dest else ''
        self.ensure_prefix(bucket_name, dir_key)

        full_path = f'{self.buckets_root}/{bucket_name}/{dest}'
        with wu.wu_open(full_path, "w") as f:
            f.write(string_data)

    def upload_string_if_missing(self, string_data, bucket_name, dest):
        dir_key = dest[:dest.rfind('/')] if '/' in dest else ''
        self.ensure_prefix(bucket_name, dir_key)
        full_path = f'{self.buckets_root}/{bucket_name}/{dest}'
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            fd = os.open(full_path, flags)
        except FileExistsError:
            return False

        with os.fdopen(fd, "w") as stream:
            stream.write(string_data)
        return True

    def upload_directory(self, source, bucket_name, prefix):

        wu.copytree(source, f'{self.buckets_root}/{bucket_name}/{prefix}')

    def sync_directory(self, source, bucket_name, prefix):
        import shutil
        dest = f'{self.buckets_root}/{bucket_name}/{prefix}'
        wu.makedirs(dest, exist_ok=True)
        shutil.copytree(source, dest, dirs_exist_ok=True)

    @contextmanager
    def read_object_stream(self, bucket_name, key, name=None):
        """Yields an OS-portable read-only memory stream for the object."""
        if name:
            full_path = f'{self.buckets_root}/{bucket_name}/{key}/{name}'
        else:
            full_path = f'{self.buckets_root}/{bucket_name}/{key}'
            
        with wu.wu_open(full_path, "r") as f:
            yield f

    def download_object(self, bucket_name, key, name, dest='/tmp'):
        """
        Pretend to download a file by copying

        :param key: the object's full key
        :param name: the object's last key
        :param dest: local destination prefix
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """
        try:

            print(name)

            # create nested directory structure
            wu.makedirs(dest, exist_ok=True)
            src = f'{self.buckets_root}/{bucket_name}/{key}/{name}'

            if wu.isfile(src):

                stale = f'{dest}/{name}'
                wu.remove(stale)

                wu.copy(src, dest)

        except Exception as e:
            logging.error(e)
            return False
        return True

    def list_files_by_key(self, bucket_name, root_key):
        """
        Pretend to download a file by copying

        :param root_key: the object's full key
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """
        try:

            src = f'{self.buckets_root}/{bucket_name}/{root_key}'

            if wu.isdir(src):
                return wu.get_files_in_dir(src)

        except Exception as e:
            logging.error(e)
            return False
        return True

    def cli_download_object(self, bucket_name, key, dest):
        pass

    def download_objects(self, bucket_name, names, dest='/tmp'):
        """

        Copies a list of files to a destination to mimic downloading objects

        :param dest: local destination prefix
        :param names: list of files
        :param bucket_name: Bucket
        :return: True
        """

        wu.makedirs(dest, exist_ok=True)

        for name in names:

            dest1 = f'{dest}/{name}'

            wu.remove(dest1)

            src = f'{bucket_name}/{name}'
            wu.copyfile(src, dest)

    def download_objects_flat_by_key(self, bucket_name, root_key='', dest='/tmp'):
        """
        Copies files below a prefix directly into dest by basename.

        :param dest: local destination prefix
        :param root_key:
        :param bucket_name: Bucket
        :return: True
        """
        object_names = self.get_object_names(bucket_name, root_key)
        wu.makedirs(dest, exist_ok=True)

        for object_name in object_names:
            source_path = f'{self.buckets_root}/{bucket_name}/{object_name}'
            if not wu.isfile(source_path):
                continue
            stale = f'{dest}/{object_name.split("/")[-1]}'
            wu.remove(stale)
            wu.copy(source_path, dest)

        return True

    def download_objects_tree_by_key(self, bucket_name, root_key='', dest='/tmp'):
        """
        Copies A directory emulating download of a chunk of objects from cloud bucket

        :param dest: local destination prefix
        :param root_key:
        :param bucket_name: Bucket
        :return: True
        """
        wu.rmtree(dest, ignore_errors=True)
        wu.copytree(f'{self.buckets_root}/{bucket_name}/{root_key}', dest)

        return True

    def download_objects_by_key(self, bucket_name, root_key='', dest='/tmp'):
        return self.download_objects_tree_by_key(bucket_name, root_key, dest)

    def delete_file(self, bucket_name, file_name):
        """Delete a file to emulate deleting a bucket object
        :param file_name:
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """
        target = f'{self.buckets_root}/{bucket_name}/{file_name}'
        if wu.isdir(target):
            wu.rmtree(target, ignore_errors=True)
            return True
        if wu.exists(target):
            wu.remove(target, ignore_errors=True)

        return True

    def delete_objects(self, bucket_name, prefix=''):
        """Empty a local Dir emulating a bucket

        :param prefix:
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """
        wu.rmtree(f'{self.buckets_root}/{bucket_name}/{prefix}', ignore_errors=True)

        return True

    def delete_bucket(self, bucket_name):
        """Delete an S3 bucket by emptying it and deleting the empty bucket.

        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """

        wu.rmtree(f'{self.buckets_root}/{bucket_name}', ignore_errors=True)

        return True

    def get_bucket_names(self):
        """
        Retrieve a list of existing buckets.
        :return: list of bucket names
        """

        bucket_names = [p.name for p in pathlib.Path(f'{self.buckets_root}').iterdir() if p.is_dir()]

        return bucket_names

    def get_object_names(self, bucket_name, prefix=''):

        try:
            base_dir = wu.convert_to_unix_path(f'{self.buckets_root}/{bucket_name}')
            target_dir = wu.convert_to_unix_path(f'{base_dir}/{prefix}')
            
            # S3 seamlessly returns paths matching the prefix across unbounded directory nesting natively.
            search_dir = wu.dirname(target_dir) if not wu.isdir(target_dir) else target_dir
            
            if not wu.exists(search_dir):
                return []
                
            object_names = []
            for root, dirs, files in wu.walk(search_dir):
                root_unix = wu.convert_to_unix_path(root)
                for f in files:
                    full_path = f"{root_unix}/{f}"
                    if full_path.startswith(base_dir + "/"):
                        rel_path = full_path[len(base_dir) + 1:]
                        if prefix == '' or rel_path.startswith(prefix):
                            object_names.append(rel_path)

            return object_names

        except Exception as e:
            logging.error(e)
            logging.info(f"No objects in key {prefix}")
            return []

    def object_exists(self, bucket_name, prefix, object_name):

        object_names = self.get_object_names(
            bucket_name=bucket_name,
            prefix=prefix
        ) or []

        target_key = f"{prefix}/{object_name}" if prefix else object_name
        if target_key in object_names:
            return True

        return False

    def bucket_sync(self, src_bucket, dest_bucket, src_prefix, dest_prefix):
        # TODO: Fill function
        pass

    def glob_keys(self, bucket_name, pattern, recursive=False):
        return super().glob_keys(bucket_name, pattern, recursive=recursive)


class WRcloneBucketeer(Bucketeer):
    """Bucketeer implementation backed by an rclone remote and WClone config."""

    def __init__(self, conf=None, rclone_conf=None, action: WieldAction | str = WieldAction.APPLY):
        super().__init__(conf)
        selected_conf = rclone_conf if rclone_conf is not None else self._rclone_conf_from_project_conf(conf)
        self.config = WRcloneBucketeerConfig.from_conf(selected_conf)
        self.rclone_remote = self.config.rclone_remote
        self.rclone_config_path = pathlib.Path(self.config.rclone_config_path).expanduser()
        if self.config.configure_on_init:
            self.configure(action=action)

    @staticmethod
    def _rclone_conf_from_project_conf(conf):
        if conf is None:
            raise ValueError("WRcloneBucketeer requires rclone_conf or a project conf with wrclone_bucketeer settings.")
        for key in [
            "wielder.wrclone_bucketeer",
            "wielder.rclone_bucketeer",
            "wrclone_bucketeer",
            "rclone_bucketeer",
        ]:
            try:
                value = conf.get(key, None)
            except Exception:
                value = None
            if value is not None:
                return value
        raise ValueError(
            "WRcloneBucketeer config not found. Expected `wielder.wrclone_bucketeer` "
            "or an explicit rclone_conf payload."
        )

    def configure(self, action: WieldAction | str = WieldAction.APPLY) -> None:
        action = action if isinstance(action, WieldAction) else WieldAction(str(action))
        if not self.config.wclone_configs:
            return
        from wielder.util.wcloner import WCloneToolConfiguration, WCloner

        WCloner.configure_rclone(
            [
                WCloneToolConfiguration.model_validate(_plain_conf(configuration))
                for configuration in self.config.wclone_configs
            ],
            action=action,
        )

    def object_uri_by_key(self, bucket_name: str, object_key: str) -> str:
        object_path = self.join_object_key(bucket_name, object_key)
        return f"{self.rclone_remote}:{object_path}"

    def create_bucket(self, bucket_name, region=None):
        self.run_checked(["rclone", "mkdir", self._uri(bucket_name), "--config", str(self.rclone_config_path)])
        return True

    def bucket_exists(self, bucket_name):
        result = subprocess.run(
            ["rclone", "lsjson", self._uri(bucket_name), "--max-depth", "1", "--config", str(self.rclone_config_path)],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def ensure_prefix(self, bucket_name, prefix):
        self.run_checked(["rclone", "mkdir", self._uri(bucket_name, prefix), "--config", str(self.rclone_config_path)])
        return True

    def cli_upload_file(self, source, bucket_name, dest, is_text=False):
        return self.upload_file(source=source, bucket_name=bucket_name, dest=dest, is_text=is_text)

    def upload_file(self, source, bucket_name, dest, is_text=False, replace=False):
        command = [
            "rclone",
            "copyto",
            str(pathlib.Path(source).expanduser()),
            self._uri(bucket_name, dest),
            "--config",
            str(self.rclone_config_path),
            *self.config.common_flags,
        ]
        self.run_checked(command)
        return True

    def upload_string(self, string_data, bucket_name, dest):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as stream:
            stream.write(string_data)
            temp_path = stream.name
        try:
            return self.upload_file(temp_path, bucket_name, dest, is_text=True, replace=True)
        finally:
            pathlib.Path(temp_path).unlink(missing_ok=True)

    def upload_directory(self, source, bucket_name, prefix):
        command = [
            "rclone",
            "copy",
            str(pathlib.Path(source).expanduser()),
            self._uri(bucket_name, prefix),
            "--config",
            str(self.rclone_config_path),
            *self.config.common_flags,
        ]
        self.run_checked(command)
        return True

    def sync_directory(self, source, bucket_name, prefix):
        command = [
            "rclone",
            "sync",
            str(pathlib.Path(source).expanduser()),
            self._uri(bucket_name, prefix),
            "--config",
            str(self.rclone_config_path),
            *self.config.common_flags,
        ]
        self.run_checked(command)
        return True

    @contextmanager
    def read_object_stream(self, bucket_name, key, name=None):
        payload = self.capture_checked(
            ["rclone", "cat", self._uri(bucket_name, self.join_object_key(key, name or "")), "--config", str(self.rclone_config_path)]
        )
        stream = io.StringIO(payload)
        try:
            yield stream
        finally:
            stream.close()

    def download_object(self, bucket_name, key, name, dest='/tmp'):
        target_dir = pathlib.Path(dest).expanduser()
        target_dir.mkdir(parents=True, exist_ok=True)
        source_key = self.join_object_key(key, name)
        target_path = target_dir / pathlib.PurePosixPath(name).name
        self.run_checked(
            [
                "rclone",
                "copyto",
                self._uri(bucket_name, source_key),
                target_path.as_posix(),
                "--config",
                str(self.rclone_config_path),
                *self.config.common_flags,
            ]
        )
        return True

    def cli_download_object(self, bucket_name, key, dest):
        target = pathlib.Path(dest).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        self.run_checked(
            ["rclone", "copyto", self._uri(bucket_name, key), target.as_posix(), "--config", str(self.rclone_config_path)]
        )
        return True

    def download_objects(self, bucket_name, keys, dest='/tmp'):
        for key in keys:
            prefix, name = key.rsplit('/', 1) if '/' in key else ('', key)
            self.download_object(bucket_name, prefix, name, dest=dest)
        return True

    def download_objects_flat_by_key(self, bucket_name, root_key='', dest='/tmp'):
        return self.download_objects(bucket_name, self.get_object_names(bucket_name, root_key), dest=dest)

    def download_objects_tree_by_key(self, bucket_name, root_key='', dest='/tmp'):
        pathlib.Path(dest).expanduser().mkdir(parents=True, exist_ok=True)
        self.run_checked(
            [
                "rclone",
                "copy",
                self._uri(bucket_name, root_key),
                pathlib.Path(dest).expanduser().as_posix(),
                "--config",
                str(self.rclone_config_path),
                *self.config.common_flags,
            ]
        )
        return True

    def delete_file(self, bucket_name, file_name):
        self.run_checked(["rclone", "deletefile", self._uri(bucket_name, file_name), "--config", str(self.rclone_config_path)])
        return True

    def delete_objects(self, bucket_name, prefix=''):
        self.run_checked(["rclone", "purge", self._uri(bucket_name, prefix), "--config", str(self.rclone_config_path)])
        return True

    def delete_bucket(self, bucket_name):
        return self.delete_objects(bucket_name, "")

    def get_bucket_names(self):
        output = self.capture_checked(
            ["rclone", "lsf", f"{self.rclone_remote}:", "--dirs-only", "--format", "p", "--config", str(self.rclone_config_path)]
        )
        return sorted(line.strip().strip("/") for line in output.splitlines() if line.strip())

    def get_object_names(self, bucket_name, prefix=''):
        normalized_prefix = self.normalize_object_key(prefix)
        output = self.capture_checked(
            [
                "rclone",
                "lsjson",
                self._uri(bucket_name, normalized_prefix),
                "--recursive",
                "--files-only",
                "--config",
                str(self.rclone_config_path),
            ]
        )
        entries = json.loads(output or "[]")
        object_names = []
        for entry in entries:
            if entry.get("IsDir"):
                continue
            relative_path = str(entry.get("Path") or entry.get("Name") or "").strip("/")
            if not relative_path:
                continue
            object_names.append(self.join_object_key(normalized_prefix, relative_path))
        return sorted(set(object_names))

    def object_exists(self, bucket_name, prefix, object_name):
        return self.join_object_key(prefix, object_name) in self.get_object_names(bucket_name, prefix)

    def bucket_sync(self, src_bucket, dest_bucket, src_prefix, dest_prefix):
        self.run_checked(
            [
                "rclone",
                "sync",
                self._uri(src_bucket, src_prefix),
                self._uri(dest_bucket, dest_prefix),
                "--config",
                str(self.rclone_config_path),
                *self.config.common_flags,
            ]
        )
        return True

    def list_files_by_key(self, bucket_name, root_key):
        return self.get_object_names(bucket_name, root_key)

    def _uri(self, bucket_name: str, object_key: str = "") -> str:
        bucket = self.normalize_object_key(str(bucket_name))
        key = self.normalize_object_key(str(object_key or ""))
        object_path = self.join_object_key(bucket, key)
        return f"{self.rclone_remote}:{object_path}"

    def run_checked(self, command: list[str]) -> subprocess.CompletedProcess:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                "rclone command failed "
                f"[returncode={result.returncode}]: {' '.join(command)}\n{result.stderr.strip()}"
            )
        return result

    def capture_checked(self, command: list[str]) -> str:
        return self.run_checked(command).stdout


RcloneBucketeer = WRcloneBucketeer


def get_bucketeer(conf, runtime_env=RuntimeEnv.MAC, bucket_env=RuntimeEnv.AWS):
    """
    Factory method for standardizing bucket access e.g. S3 boto3 client, GCP Client, Local Directory to simulate bucket,
     depending on the combination of runtime environment and deploy environment.
    :param conf: project config
    :param runtime_env: Where this code is running
    :param bucket_env: Where the bucket is.
    :return: a Bucketeer object wrapping buckets or local mock buckets
    """

    if runtime_env.value in local_deployments:
        auth = True
    else:
        auth = False

    if bucket_env == RuntimeEnv.AWS:
        return AWSBucketeer(conf, auth=auth)
    else:
        return DevBucketeer(conf)


def _normalize_object_key(raw_key: str) -> str:
    key = raw_key.strip().strip("/")
    if key in {"", "."}:
        return ""
    if "\\" in key:
        raise ValueError(f"Refusing non-POSIX object key with backslash: {raw_key}")
    path = pathlib.PurePosixPath(key)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise ValueError(f"Refusing unsafe object key: {raw_key}")
    return path.as_posix()


def _walk_object_keys(
    object_keys: list[str],
    root_key: str = "",
    max_depth: int | None = None,
) -> list[BucketeerWalkEntry]:
    normalized_root_key = _normalize_object_key(root_key)
    root_parts = pathlib.PurePosixPath(normalized_root_key).parts if normalized_root_key else ()
    children_by_dir: dict[tuple[str, ...], set[str]] = {}
    files_by_dir: dict[tuple[str, ...], set[str]] = {}
    recursive_file_counts: dict[tuple[str, ...], int] = {}

    root_tuple = tuple(root_parts)
    children_by_dir.setdefault(root_tuple, set())
    files_by_dir.setdefault(root_tuple, set())
    recursive_file_counts.setdefault(root_tuple, 0)

    for object_key in object_keys:
        key = _normalize_object_key(object_key)
        parts = pathlib.PurePosixPath(key).parts
        if root_parts and parts[: len(root_parts)] != root_parts:
            continue
        if len(parts) <= len(root_parts):
            continue

        file_parent = tuple(parts[:-1])
        files_by_dir.setdefault(file_parent, set()).add(parts[-1])
        children_by_dir.setdefault(file_parent, set())

        for depth in range(len(root_parts), len(parts)):
            parent = tuple(parts[:depth])
            recursive_file_counts[parent] = recursive_file_counts.get(parent, 0) + 1
            children_by_dir.setdefault(parent, set())
            files_by_dir.setdefault(parent, set())
            if depth < len(parts) - 1:
                children_by_dir[parent].add(parts[depth])

    recursive_dir_counts = _count_recursive_dirs(children_by_dir.keys(), root_parts)
    return [
        BucketeerWalkEntry(
            key=pathlib.PurePosixPath(*directory).as_posix() if directory else "",
            dirnames=tuple(sorted(children_by_dir.get(directory, set()))),
            filenames=tuple(sorted(files_by_dir.get(directory, set()))),
            recursive_file_count=recursive_file_counts.get(directory, 0),
            recursive_dir_count=recursive_dir_counts.get(directory, 0),
        )
        for directory in sorted(children_by_dir)
        if max_depth is None or len(directory) <= max_depth
    ]


def _render_directory_tree(
    entries: list[BucketeerWalkEntry],
    bucket: str,
    root_key: str = "",
    max_depth: int = 6,
    include_files: bool = False,
    max_children_per_node: int = 80,
) -> str:
    normalized_root_key = _normalize_object_key(root_key)
    entry_by_key = {entry.key: entry for entry in entries}
    root_entry = entry_by_key.get(normalized_root_key)
    if root_entry is None:
        tree = Tree(f"{bucket} [0 dirs]")
        tree.add(f"{normalized_root_key or '.'} [0 dirs]")
        console = Console(record=True, color_system=None, file=io.StringIO(), width=240, force_jupyter=False)
        console.print(tree, highlight=False, markup=False)
        return console.export_text(styles=False).rstrip()

    tree = Tree(f"{bucket} [{len(entries)} dirs]")
    parent_tree = _add_root_key_nodes(tree, normalized_root_key, root_entry.recursive_dir_count)
    _append_directory_tree_nodes(
        parent_tree=parent_tree,
        entry_by_key=entry_by_key,
        parent_key=normalized_root_key,
        max_depth=max_depth,
        include_files=include_files,
        max_children_per_node=max_children_per_node,
    )
    console = Console(record=True, color_system=None, file=io.StringIO(), width=240, force_jupyter=False)
    console.print(tree, highlight=False, markup=False)
    return console.export_text(styles=False).rstrip()


def _add_root_key_nodes(tree: Tree, root_key: str, recursive_dir_count: int) -> Tree:
    parent_tree = tree
    root_parts = pathlib.PurePosixPath(root_key).parts if root_key else ()
    for index, part in enumerate(root_parts):
        label = f"{part} [{recursive_dir_count} dirs]" if index == len(root_parts) - 1 else part
        parent_tree = parent_tree.add(label)
    return parent_tree


def _append_directory_tree_nodes(
    parent_tree: Tree,
    entry_by_key: dict[str, BucketeerWalkEntry],
    parent_key: str,
    max_depth: int,
    include_files: bool,
    max_children_per_node: int,
) -> None:
    parent_entry = entry_by_key[parent_key]
    child_names = parent_entry.dirnames[:max_children_per_node]
    omitted_dir_count = max(0, len(parent_entry.dirnames) - len(child_names))

    for child_name in child_names:
        child_key = _join_key(parent_key, child_name)
        child_depth = _key_depth(child_key)
        if child_depth > max_depth:
            continue
        child_entry = entry_by_key[child_key]
        child_tree = parent_tree.add(f"{child_name} [{child_entry.recursive_dir_count} dirs]")
        _append_directory_tree_nodes(
            parent_tree=child_tree,
            entry_by_key=entry_by_key,
            parent_key=child_key,
            max_depth=max_depth,
            include_files=include_files,
            max_children_per_node=max_children_per_node,
        )

    if omitted_dir_count:
        parent_tree.add(f"... [{omitted_dir_count} directories omitted]")

    if include_files and _key_depth(parent_key) < max_depth:
        filenames = parent_entry.filenames[:max_children_per_node]
        for filename in filenames:
            parent_tree.add(filename)
        omitted_file_count = max(0, len(parent_entry.filenames) - len(filenames))
        if omitted_file_count:
            parent_tree.add(f"... [{omitted_file_count} files omitted]")


def _join_key(parent_key: str, child_name: str) -> str:
    if not parent_key:
        return child_name
    return pathlib.PurePosixPath(parent_key, child_name).as_posix()


def _key_depth(key: str) -> int:
    if not key:
        return 0
    return len(pathlib.PurePosixPath(key).parts)


def _count_recursive_dirs(
    directories,
    root_parts: tuple[str, ...],
) -> dict[tuple[str, ...], int]:
    recursive_dir_counts: dict[tuple[str, ...], int] = {tuple(directory): 0 for directory in directories}
    for directory in recursive_dir_counts:
        for depth in range(len(root_parts), len(directory)):
            ancestor = directory[:depth]
            if ancestor in recursive_dir_counts:
                recursive_dir_counts[ancestor] += 1
    return recursive_dir_counts


def get_ecosystem_bucketeer(conf, bucketeer_type=None, **bucketeer_kwargs):
    """
    Ecosystem native factory method for standardizing bucket access based on the parsed active ecosystem.
    :param conf: project configuration dict natively bridging the target ecosystem state
    :param bucketeer_type: Optional explicit identifier to override the topology (e.g., AWS service writing to Google Drive)
    :return: a Bucketeer object resolving directly against the core ecosystem topology
    """

    ecosystem = conf.ecosystem

    if not bucketeer_type:
        bucketeer_type = conf.get("wielder.bucketeer", None)
        if not bucketeer_type:
            try:
                bucketeer_type = conf.wielder.ecosystem_map[ecosystem].bucketeer
            except Exception:
                raise ValueError(
                    f"Ecosystem topology '{ecosystem}' does not declare a bucketeer.\n"
                    "Set `wielder.bucketeer` in the ecosystem manifest, or provide the legacy "
                    f"`wielder.ecosystem_map.{ecosystem}.bucketeer` entry explicitly."
                )

    match bucketeer_type:
        case 'DevBucketeer':
            return DevBucketeer(conf)
        case 'AWSBucketeer':
            return AWSBucketeer(conf, auth=False, **bucketeer_kwargs)
        case 'GCSBucketeer':
            return GCSBucketeer(conf, auth=True, **bucketeer_kwargs)
        case 'GoogleBucketeer':
            return GoogleBucketeer(conf, auth=True, **bucketeer_kwargs)
        case 'WRcloneBucketeer' | 'RcloneBucketeer':
            return WRcloneBucketeer(conf, **bucketeer_kwargs)
        case _:
            raise ValueError(f"Unrecognized bucketeer class '{bucketeer_type}' requested.")


def get_provider_bucketeer(conf, provider: str, **bucketeer_kwargs):
    """Factory accessor for explicit storage provider surfaces."""
    match str(provider):
        case "local":
            return DevBucketeer(conf)
        case "s3":
            return AWSBucketeer(conf, auth=True, region=str(conf.aws.region), **bucketeer_kwargs)
        case "gcs":
            return GCSBucketeer(conf, auth=True, **bucketeer_kwargs)
        case "google_drive":
            return GoogleBucketeer(conf, auth=True, **bucketeer_kwargs)
        case "rclone":
            return WRcloneBucketeer(conf, **bucketeer_kwargs)
        case _:
            raise ValueError(f"Unrecognized storage provider [{provider}] requested.")
