"""Generic cloud identity contracts."""

import logging
import threading
import time
import urllib.parse
import urllib.request
from abc import ABC
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


logger = logging.getLogger(__name__)
GCP_METADATA_IDENTITY_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"
)


class WCloudSurface(str, Enum):
    AWS = "aws"
    GCP = "gcp"


class WCloudIdentity(BaseModel, ABC):
    model_config = ConfigDict(extra="forbid")

    identity_type: str

    @classmethod
    def from_conf(cls, value) -> "WCloudIdentity":
        if isinstance(value, WCloudIdentity):
            return value
        identity_type = str(value.get("identity_type", "")).strip()
        if identity_type == "gcp_metadata_aws_web_identity":
            return GCPMetadataAWSWebIdentity.model_validate(value)
        raise ValueError(f"Unsupported WCloudIdentity identity_type [{identity_type}].")

    @property
    def lives_on_surface(self) -> WCloudSurface:
        raise NotImplementedError

    @property
    def known_to_surface(self) -> WCloudSurface:
        raise NotImplementedError

    def materialize_env(self) -> dict[str, str]:
        raise NotImplementedError


class GCPMetadataAWSWebIdentity(WCloudIdentity):
    identity_type: Literal["gcp_metadata_aws_web_identity"]
    role_arn: str
    audience: str
    token_file: str
    region: str
    session_name: str
    refresh_interval_seconds: int

    @property
    def lives_on_surface(self) -> WCloudSurface:
        return WCloudSurface.GCP

    @property
    def known_to_surface(self) -> WCloudSurface:
        return WCloudSurface.AWS

    @field_validator("role_arn", "audience", "token_file", "region", "session_name")
    @classmethod
    def require_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("GCPMetadataAWSWebIdentity values must not be empty")
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in GCPMetadataAWSWebIdentity value [{value}]")
        return value

    @field_validator("refresh_interval_seconds")
    @classmethod
    def validate_refresh_interval(cls, value: int) -> int:
        if value < 0:
            raise ValueError("GCPMetadataAWSWebIdentity refresh_interval_seconds must be nonnegative")
        return value

    def materialize_env(self) -> dict[str, str]:
        self.start_refresh()
        return {
            "AWS_ROLE_ARN": self.role_arn,
            "AWS_WEB_IDENTITY_TOKEN_FILE": str(Path(self.token_file).expanduser()),
            "AWS_ROLE_SESSION_NAME": self.session_name,
            "AWS_REGION": self.region,
            "AWS_DEFAULT_REGION": self.region,
        }

    def start_refresh(self) -> None:
        self.write_token_file()
        if self.refresh_interval_seconds == 0:
            return

        def refresh_loop() -> None:
            while True:
                time.sleep(self.refresh_interval_seconds)
                try:
                    self.write_token_file()
                    logger.info("Refreshed WCloudIdentity token file [%s].", self.token_file)
                except Exception:
                    logger.exception("Failed to refresh WCloudIdentity token file [%s].", self.token_file)

        threading.Thread(target=refresh_loop, daemon=True).start()

    def write_token_file(self) -> None:
        token_file = Path(self.token_file).expanduser()
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(self.token())
        token_file.chmod(0o600)

    def token(self) -> str:
        query = urllib.parse.urlencode({"audience": self.audience, "format": "full"})
        request = urllib.request.Request(
            f"{GCP_METADATA_IDENTITY_URL}?{query}",
            headers={"Metadata-Flavor": "Google"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            token = response.read().decode("utf-8").strip()
        if not token:
            raise RuntimeError("GCP metadata identity endpoint returned an empty token.")
        return token
