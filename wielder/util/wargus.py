"""Wielder-native security guardian interfaces.

WArgus is intentionally a thin provider-dispatch surface at this stage. Durable
cloud resources still belong to Terraform/provisioning; WArgus will own runtime
security operations such as secret value pumping and group verification.
"""

import logging
import os
import subprocess
from abc import ABC
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wielder.util.credential_helper import require_aws_mfa_cred
from wielder.wield.enumerator import WieldAction


logger = logging.getLogger(__name__)
GOOGLE_WORKSPACE_GROUP_SCOPES = [
    "https://www.googleapis.com/auth/admin.directory.group",
]


class WArgusProvider(str, Enum):
    GCP = "gcp"
    GOOGLE_WORKSPACE = "google_workspace"
    AWS = "aws"
    LOCAL = "local"


class WArgusSecurityHood(str, Enum):
    ORG = "org"
    RESTRICTED = "restricted"
    BREAK_GLASS = "break_glass"

    @property
    def name_fragment(self) -> str:
        if self == WArgusSecurityHood.ORG:
            return ""
        return self.value.replace("_", "-")


class WArgusPayloadSourceType(str, Enum):
    ENV = "env"
    FILE = "file"
    COMMAND = "command"
    AWS_MFA = "aws_mfa"


class WArgusPayloadSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: WArgusPayloadSourceType
    reference: str

    @field_validator("reference")
    @classmethod
    def require_reference(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("payload source reference must not be empty")
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in payload source reference [{value}]")
        return value


class WArgusSecret(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    stage_tier: str
    classification: str = "secret"
    compartment: str
    payload_source: WArgusPayloadSource | None = None
    runtime_readers: list[str] = Field(default_factory=list)
    operator_groups: list[str] = Field(default_factory=list)
    break_glass_groups: list[str] = Field(default_factory=list)

    @field_validator("name", "stage_tier", "classification", "compartment")
    @classmethod
    def require_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in WArgus value [{value}]")
        return value

    @field_validator("runtime_readers", "operator_groups", "break_glass_groups")
    @classmethod
    def reject_empty_principals(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError("principal values must not be empty")
        return values

    @model_validator(mode="after")
    def require_stage_tier_in_secret_name(self):
        if not self.name.endswith(f"-{self.stage_tier}"):
            raise ValueError(
                f"secret name [{self.name}] must include stage_tier suffix [-{self.stage_tier}]"
            )
        return self


class WArgusGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    stage_tier: str
    name: str | None = None
    description: str = ""
    classification: str = "security_group"
    compartment: str
    create: bool = True
    owners: list[str] = Field(default_factory=list)
    members: list[str] = Field(default_factory=list)

    @field_validator("email", "stage_tier", "classification", "compartment", "description")
    @classmethod
    def require_nonempty(cls, value: str) -> str:
        if value is not None and not value.strip() and value != "":
            raise ValueError("value must not be empty")
        return value

    @field_validator("name")
    @classmethod
    def require_nonempty_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("group name must not be empty")
        return value

    @field_validator("owners", "members")
    @classmethod
    def reject_empty_members(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError("group member values must not be empty")
        return values

    @model_validator(mode="after")
    def require_stage_tier_in_group_name(self):
        local_part = self.email.split("@", maxsplit=1)[0]
        if not local_part.endswith(f"-{self.stage_tier}"):
            raise ValueError(
                f"group [{self.email}] must include stage_tier suffix [-{self.stage_tier}]"
            )
        return self


class WArgusSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: WArgusProvider
    action: WieldAction
    security_hood: WArgusSecurityHood = WArgusSecurityHood.ORG
    project_id: str | None = None
    organization_slug: str | None = None
    secrets: list[WArgusSecret] = Field(default_factory=list)
    groups: list[WArgusGroup] = Field(default_factory=list)
    local_root: str | None = None
    google_credentials_path: str | None = None
    aws_mfa_role: str | None = None

    @field_validator(
        "project_id",
        "organization_slug",
        "local_root",
        "google_credentials_path",
        "aws_mfa_role",
    )
    @classmethod
    def reject_backslashes(cls, value: str | None) -> str | None:
        if value is not None and "\\" in value:
            raise ValueError(f"backslash is not allowed in WArgus spec value [{value}]")
        return value

    @field_validator("local_root", "google_credentials_path")
    @classmethod
    def expand_local_paths(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return Path(value).expanduser().as_posix()


class WArgus(ABC):
    provider: WArgusProvider

    def __init__(self, spec: WArgusSpec):
        self.spec = spec

    @classmethod
    def from_spec(cls, spec: WArgusSpec) -> "WArgus":
        match spec.provider:
            case WArgusProvider.GCP:
                return GCPArgus(spec)
            case WArgusProvider.GOOGLE_WORKSPACE:
                return GoogleWorkspaceArgus(spec)
            case WArgusProvider.AWS:
                return AWSArgus(spec)
            case WArgusProvider.LOCAL:
                return LocalArgus(spec)
            case _:
                raise ValueError(f"Unsupported WArgus provider [{spec.provider}]")

    @classmethod
    def from_provider(
        cls,
        provider: WArgusProvider | Literal["gcp", "google_workspace", "aws", "local"],
        action: WieldAction,
        **kwargs,
    ) -> "WArgus":
        spec = WArgusSpec(provider=WArgusProvider(provider), action=action, **kwargs)
        return cls.from_spec(spec)

    def show(self):
        raise NotImplementedError(f"{self.__class__.__name__}.show is not implemented yet.")

    def plan(self):
        raise NotImplementedError(f"{self.__class__.__name__}.plan is not implemented yet.")

    def apply(self):
        raise NotImplementedError(f"{self.__class__.__name__}.apply is not implemented yet.")

    def ensure_secret_containers(self):
        raise NotImplementedError(
            f"{self.__class__.__name__}.ensure_secret_containers is not implemented yet."
        )

    def populate_secret_versions(self):
        raise NotImplementedError(
            f"{self.__class__.__name__}.populate_secret_versions is not implemented yet."
        )

    def verify_groups(self):
        raise NotImplementedError(f"{self.__class__.__name__}.verify_groups is not implemented yet.")

    def ensure_groups(self):
        raise NotImplementedError(f"{self.__class__.__name__}.ensure_groups is not implemented yet.")


class GCPArgus(WArgus):
    provider = WArgusProvider.GCP

    def show(self):
        return self._describe_secrets()

    def plan(self):
        secrets = self._describe_secrets()
        logger.info("GCP Argus secret-version plan: %s", [secret["name"] for secret in secrets])
        return secrets

    def apply(self):
        return self.populate_secret_versions()

    def populate_secret_versions(self):
        if not self.spec.project_id:
            raise RuntimeError("GCPArgus requires project_id to populate Secret Manager versions.")

        results = []
        for secret in self.spec.secrets:
            payload = self._payload_for_secret(secret)
            command = [
                "gcloud",
                "secrets",
                "versions",
                "add",
                secret.name,
                "--project",
                self.spec.project_id,
                "--data-file=-",
                "--quiet",
            ]
            logger.info("Adding Secret Manager version for [%s] in project [%s].", secret.name, self.spec.project_id)
            try:
                proc = subprocess.run(
                    command,
                    input=payload,
                    check=False,
                    text=True,
                    capture_output=True,
                )
            except FileNotFoundError as exc:
                raise RuntimeError("gcloud is required to populate GCP Secret Manager versions.") from exc

            if proc.returncode != 0:
                raise RuntimeError(
                    f"Failed to add Secret Manager version for [{secret.name}]: {proc.stderr.strip()}"
                )

            message = (proc.stdout or proc.stderr).strip()
            if message:
                logger.info("Secret Manager version response for [%s]: %s", secret.name, message)
            results.append({"name": secret.name, "status": "version_added"})

        return results

    def _describe_secrets(self):
        return [
            {
                "name": secret.name,
                "classification": secret.classification,
                "compartment": secret.compartment,
                "payload_source_type": (
                    secret.payload_source.source_type.value if secret.payload_source is not None else None
                ),
                "payload_source_reference": (
                    secret.payload_source.reference if secret.payload_source is not None else None
                ),
                "payload": "[redacted]",
            }
            for secret in self.spec.secrets
        ]

    def _payload_for_secret(self, secret: WArgusSecret) -> str:
        if secret.payload_source is None:
            raise RuntimeError(f"Secret [{secret.name}] is missing payload_source.")

        source = secret.payload_source
        match source.source_type:
            case WArgusPayloadSourceType.ENV:
                value = os.environ.get(source.reference)
                if value is None:
                    raise RuntimeError(f"Environment variable [{source.reference}] is missing for [{secret.name}].")
                return value
            case WArgusPayloadSourceType.FILE:
                source_path = Path(source.reference).expanduser()
                if not source_path.exists():
                    raise RuntimeError(f"Payload source file [{source_path}] is missing for [{secret.name}].")
                return source_path.read_text()
            case WArgusPayloadSourceType.COMMAND:
                proc = subprocess.run(
                    source.reference,
                    shell=True,
                    check=False,
                    text=True,
                    capture_output=True,
                )
                if proc.returncode != 0:
                    raise RuntimeError(
                        f"Payload source command failed for [{secret.name}]: {proc.stderr.strip()}"
                    )
                return proc.stdout.rstrip("\n")
            case WArgusPayloadSourceType.AWS_MFA:
                if not self.spec.aws_mfa_role:
                    raise RuntimeError("AWS MFA payload sources require aws_mfa_role in WArgusSpec.")
                credentials = require_aws_mfa_cred(self.spec.aws_mfa_role)
                if source.reference not in credentials:
                    raise RuntimeError(
                        f"AWS MFA credential key [{source.reference}] is missing for role [{self.spec.aws_mfa_role}]."
                    )
                return credentials[source.reference]
            case _:
                raise ValueError(f"Unsupported payload source type [{source.source_type}].")


class GoogleWorkspaceArgus(WArgus):
    provider = WArgusProvider.GOOGLE_WORKSPACE

    def __init__(self, spec: WArgusSpec, directory_service: Any | None = None):
        super().__init__(spec)
        self._directory_service = directory_service

    def show(self):
        return self._describe_groups()

    def plan(self):
        groups = self._describe_groups()
        logger.info("Google Workspace Argus group plan: %s", [group["email"] for group in groups])
        return groups

    def apply(self):
        return self.ensure_groups()

    def verify_groups(self):
        service = self._get_directory_service()
        missing = []
        for group in self.spec.groups:
            if not self._group_exists(service, group.email):
                missing.append(group.email)
        if missing:
            raise RuntimeError(f"Missing Google Workspace groups: {missing}")
        return self._describe_groups()

    def ensure_groups(self):
        service = self._get_directory_service()
        results = []
        for group in self.spec.groups:
            if self._group_exists(service, group.email):
                logger.info("Google Workspace group already exists: %s", group.email)
                results.append({"email": group.email, "status": "exists"})
                continue

            if not group.create:
                raise RuntimeError(f"Google Workspace group [{group.email}] is missing and create=false.")

            body = {
                "email": group.email,
                "name": group.name or group.email.split("@", maxsplit=1)[0],
                "description": group.description,
            }
            service.groups().insert(body=body).execute()
            logger.info("Created Google Workspace group: %s", group.email)
            results.append({"email": group.email, "status": "created"})
        return results

    def _describe_groups(self):
        return [
            {
                "email": group.email,
                "name": group.name or group.email.split("@", maxsplit=1)[0],
                "description": group.description,
                "classification": group.classification,
                "compartment": group.compartment,
                "create": group.create,
            }
            for group in self.spec.groups
        ]

    def _get_directory_service(self):
        if self._directory_service is not None:
            return self._directory_service

        if not self.spec.google_credentials_path:
            raise RuntimeError(
                "GoogleWorkspaceArgus requires google_credentials_path in config. "
                "Place credentials.json there or override google_credentials_path in the active context_conf."
            )

        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        credentials_root = Path(self.spec.google_credentials_path).expanduser()
        token_key = credentials_root / "argus-admin-directory-token.json"
        credentials_key = credentials_root / "credentials.json"
        if not credentials_key.exists():
            raise RuntimeError(
                f"Google Workspace OAuth client file is missing: {credentials_key}. "
                "Create/download a Google OAuth desktop client credentials.json for an admin account."
            )

        creds = None
        if token_key.exists():
            creds = Credentials.from_authorized_user_file(
                token_key.as_posix(),
                GOOGLE_WORKSPACE_GROUP_SCOPES,
            )
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_key.as_posix(),
                    GOOGLE_WORKSPACE_GROUP_SCOPES,
                )
                creds = flow.run_local_server(port=0)
            token_key.parent.mkdir(parents=True, exist_ok=True)
            token_key.write_text(creds.to_json())

        self._directory_service = build("admin", "directory_v1", credentials=creds)
        return self._directory_service

    def _group_exists(self, service, email: str) -> bool:
        try:
            service.groups().get(groupKey=email).execute()
            return True
        except Exception as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status == 404:
                return False
            if status == 403 and "admin.googleapis.com" in str(exc):
                raise RuntimeError(
                    f"Failed to verify Google Workspace group [{email}] because Admin SDK API "
                    "is disabled for the OAuth client project. Enable it with: "
                    "gcloud services enable admin.googleapis.com --project <project_id>"
                ) from exc
            raise RuntimeError(f"Failed to verify Google Workspace group [{email}]: {exc}") from exc


class AWSArgus(WArgus):
    provider = WArgusProvider.AWS


class LocalArgus(WArgus):
    provider = WArgusProvider.LOCAL
