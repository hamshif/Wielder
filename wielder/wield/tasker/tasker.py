"""Abstract Wielder task manager contract.

Tasker is intentionally small. It gives Wielder scripts a provider-neutral
surface for external task systems while provider identity and credentials stay
owned by resolved configuration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _plain_conf(value: Any) -> Any:
    if hasattr(value, "as_plain_ordered_dict"):
        return value.as_plain_ordered_dict()
    return value


def _conf_list(value: Any) -> list:
    if value is None:
        return []
    return list(value)


class WTaskerProvider(str, Enum):
    MONDAY = "monday"


WIELDER_TASKER_NOMENCLATURE = {
    "task_principal_context": {
        "monday": "me/account",
    },
    "task_space": {
        "monday": "workspace",
    },
    "task_board": {
        "monday": "board",
    },
}


class WTaskBoard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    task_space_id: str | None = None
    task_space_name: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "name", "task_space_id", "task_space_name")
    @classmethod
    def validate_token(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.strip():
            raise ValueError("WTaskBoard values must not be empty")
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in WTaskBoard value [{value}]")
        return value


class WTaskSpace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "name")
    @classmethod
    def validate_token(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("WTaskSpace values must not be empty")
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in WTaskSpace value [{value}]")
        return value


WTaskWorkspace = WTaskSpace


class WMondayTaskerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_url: str = "https://api.monday.com/v2"
    api_version: str = "2026-01"
    token: str = ""
    workspace_name: str = "Engineering"
    workspace_membership_kind: Literal["all", "member"] = "all"
    workspace_ids: list[str] = Field(default_factory=list)
    board_limit: int = 500
    workspace_limit: int = 100
    timeout_seconds: int = 30

    @field_validator("api_url", "api_version", "token", "workspace_name")
    @classmethod
    def validate_string(cls, value: str) -> str:
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in Monday tasker value [{value}]")
        return value.strip()

    @field_validator("workspace_ids")
    @classmethod
    def validate_workspace_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError("Monday workspace ids must not be empty")
            if "\\" in value:
                raise ValueError(f"backslash is not allowed in Monday workspace id [{value}]")
        return values

    @field_validator("board_limit", "workspace_limit", "timeout_seconds")
    @classmethod
    def validate_positive_int(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Monday tasker numeric values must be positive")
        return value

    @classmethod
    def from_conf(cls, monday_conf: Any | None) -> "WMondayTaskerConfig":
        if not monday_conf:
            return cls()
        monday = dict(_plain_conf(monday_conf))
        monday["workspace_ids"] = [str(value) for value in _conf_list(monday.get("workspace_ids"))]
        return cls.model_validate(monday)

    def require_token(self) -> str:
        if not self.token:
            raise ValueError(
                "Monday tasker token is missing. Put tasker.monday.token in the active secrets.conf."
            )
        return self.token


class WTaskerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: WTaskerProvider
    scope: str = "tasker"
    task_space_name: str = "Engineering"
    monday: WMondayTaskerConfig = Field(default_factory=WMondayTaskerConfig)

    @field_validator("scope", "task_space_name")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("WTasker values must not be empty")
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in WTasker value [{value}]")
        return value

    @classmethod
    def from_conf(cls, tasker_conf: Any) -> "WTaskerSpec":
        tasker = dict(_plain_conf(tasker_conf))
        spec_keys = {"provider", "scope", "task_space_name", "monday"}
        spec_conf = {key: value for key, value in tasker.items() if key in spec_keys}
        spec_conf["monday"] = WMondayTaskerConfig.from_conf(spec_conf.get("monday"))
        return cls.model_validate(spec_conf)


class WTasker(ABC):
    provider: WTaskerProvider

    def __init__(self, spec: WTaskerSpec):
        self.spec = spec

    @classmethod
    def from_spec(cls, spec: WTaskerSpec) -> "WTasker":
        match spec.provider:
            case WTaskerProvider.MONDAY:
                from wielder.wield.tasker.wmonday import WMondayTasker

                return WMondayTasker(spec)
            case _:
                raise ValueError(f"Unsupported WTasker provider [{spec.provider}]")

    @classmethod
    def from_provider(
        cls,
        provider: WTaskerProvider | Literal["monday"],
        **kwargs,
    ) -> "WTasker":
        return cls.from_spec(WTaskerSpec(provider=WTaskerProvider(provider), **kwargs))

    @classmethod
    def from_conf(cls, tasker_conf: Any) -> "WTasker":
        return cls.from_spec(WTaskerSpec.from_conf(tasker_conf))

    def plan(self) -> dict[str, Any]:
        return {
            "provider": self.spec.provider.value,
            "scope": self.spec.scope,
            "nomenclature": WIELDER_TASKER_NOMENCLATURE,
            "task_space_name": self.spec.task_space_name,
            "monday": {
                "api_url": self.spec.monday.api_url,
                "api_version": self.spec.monday.api_version,
                "workspace_name": self.spec.monday.workspace_name,
                "workspace_membership_kind": self.spec.monday.workspace_membership_kind,
                "workspace_ids": self.spec.monday.workspace_ids,
                "board_limit": self.spec.monday.board_limit,
                "workspace_limit": self.spec.monday.workspace_limit,
                "timeout_seconds": self.spec.monday.timeout_seconds,
                "token_configured": bool(self.spec.monday.token),
            },
        }

    @abstractmethod
    def tasker_context(self) -> dict[str, Any]:
        """Return generic task-principal context for the active task-manager credential."""

    @abstractmethod
    def list_task_spaces(self) -> list[WTaskSpace]:
        """Return task spaces visible to the authenticated task-manager principal."""

    @abstractmethod
    def list_task_space_boards(self, task_space_name: str) -> list[WTaskBoard]:
        """Return boards visible under the named Wielder task space."""

    def account_context(self) -> dict[str, Any]:
        return self.tasker_context()
