"""Bucket event observation surfaces for Wielder workflows."""

import json
import subprocess
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from urllib.parse import quote_plus

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _plain_conf(value):
    if hasattr(value, "as_plain_ordered_dict"):
        return value.as_plain_ordered_dict()
    return value


class WBucketEventProvider(str, Enum):
    AWS_S3_EVENTBRIDGE = "aws_s3_eventbridge"


class WBucketEventRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cro: str
    detail_type: str
    rule_name: str
    log_group_name: str

    @field_validator("cro", "detail_type", "rule_name", "log_group_name")
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("WBucketEventRoute values must not be empty")
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in WBucketEventRoute value [{value}]")
        return value


class WBucketEventConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: WBucketEventProvider
    bucket: str
    aws_region: str | None = None
    aws_profile: str = ""
    routes: dict[str, WBucketEventRoute] = Field(default_factory=dict)

    @classmethod
    def from_conf(cls, conf) -> "WBucketEventConfig":
        data = dict(_plain_conf(conf))
        if hasattr(conf, "routes"):
            data["routes"] = {
                str(route_key): _plain_conf(route_conf)
                for route_key, route_conf in conf.routes.items()
            }
        return cls.model_validate(data)

    @field_validator("bucket", "aws_region", "aws_profile")
    @classmethod
    def validate_token(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in WBucketEventConfig value [{value}]")
        return value

    @model_validator(mode="after")
    def validate_provider_contract(self):
        if not self.routes:
            raise ValueError("WBucketEventConfig routes must not be empty")
        if self.provider == WBucketEventProvider.AWS_S3_EVENTBRIDGE and not self.aws_region:
            raise ValueError("AWS S3 EventBridge bucket events require aws_region")
        return self


class WBucketEventSurface:
    def __init__(self, config: WBucketEventConfig) -> None:
        self.config = config

    @classmethod
    def from_conf(cls, conf) -> "WBucketEventSurface":
        config = WBucketEventConfig.from_conf(conf)
        match config.provider:
            case WBucketEventProvider.AWS_S3_EVENTBRIDGE:
                return WAwsS3EventBridgeBucketEvents(config)
        raise ValueError(f"Unsupported WBucketEvent provider [{config.provider}]")

    def preflight_report(self) -> dict[str, Any]:
        raise NotImplementedError

    def poll_events(
        self,
        expected_keys: set[str],
        *,
        started_at: datetime,
        event_timeout: int,
        detail_type: str,
    ) -> dict[str, dict[str, Any]]:
        raise NotImplementedError


class WAwsS3EventBridgeBucketEvents(WBucketEventSurface):
    def aws_command(self, *args: str) -> list[str]:
        command = ["aws", *args, "--region", str(self.config.aws_region), "--no-cli-pager"]
        if self.config.aws_profile:
            command.extend(["--profile", self.config.aws_profile])
        return command

    def _run_json(self, *args: str) -> dict[str, Any]:
        result = subprocess.run(self.aws_command(*args), check=True, text=True, capture_output=True)
        if not result.stdout.strip():
            return {}
        return json.loads(result.stdout)

    def _route_for(self, cro: str, detail_type: str) -> WBucketEventRoute:
        for route in self.config.routes.values():
            if route.cro == cro and route.detail_type == detail_type:
                return route
        raise RuntimeError(f"No bucket event route configured for cro=[{cro}], detail_type=[{detail_type}].")

    def _log_event_view_url(self, *, log_group_name: str, key: str) -> str:
        query = quote_plus(f'"{key}"')
        log_group = quote_plus(log_group_name)
        return (
            "https://console.aws.amazon.com/cloudwatch/home"
            f"?region={self.config.aws_region}#logsV2:log-groups/log-group/{log_group}/log-events$3FfilterPattern$3D{query}"
        )

    def _rule_report(self, route_key: str, route: WBucketEventRoute) -> dict[str, Any]:
        rule = self._run_json("events", "describe-rule", "--name", route.rule_name)
        targets = self._run_json("events", "list-targets-by-rule", "--rule", route.rule_name).get("Targets", [])
        return {
            "route_key": route_key,
            "cro": route.cro,
            "detail_type": route.detail_type,
            "rule_name": route.rule_name,
            "state": rule.get("State", ""),
            "event_pattern": rule.get("EventPattern", ""),
            "targets": targets,
            "log_group_name": route.log_group_name,
        }

    def preflight_report(self) -> dict[str, Any]:
        notification = self._run_json(
            "s3api",
            "get-bucket-notification-configuration",
            "--bucket",
            self.config.bucket,
        )
        eventbridge_enabled = "EventBridgeConfiguration" in notification
        rules = [
            self._rule_report(route_key, route)
            for route_key, route in self.config.routes.items()
        ]
        broken_rules = [
            rule["rule_name"]
            for rule in rules
            if rule["state"] != "ENABLED" or not rule["targets"]
        ]
        if not eventbridge_enabled or broken_rules:
            raise RuntimeError(
                "Bucket event path is not fully provisioned: "
                f"eventbridge_enabled={eventbridge_enabled}, broken_rules={broken_rules}"
            )
        return {
            "provider": self.config.provider.value,
            "bucket": self.config.bucket,
            "eventbridge_enabled": eventbridge_enabled,
            "event_rules": rules,
        }

    def _is_expected_event(self, body: dict[str, Any], key: str, *, detail_type: str) -> bool:
        return (
            body.get("source") == "aws.s3"
            and body.get("detail-type") == detail_type
            and body.get("detail", {}).get("bucket", {}).get("name") == self.config.bucket
            and body.get("detail", {}).get("object", {}).get("key") == key
        )

    @staticmethod
    def _event_time(body: dict[str, Any]) -> datetime | None:
        event_time = body.get("time")
        if not event_time:
            return None
        try:
            return datetime.fromisoformat(str(event_time).replace("Z", "+00:00"))
        except ValueError:
            return None

    def poll_events(
        self,
        expected_keys: set[str],
        *,
        started_at: datetime,
        event_timeout: int,
        detail_type: str,
    ) -> dict[str, dict[str, Any]]:
        deadline = time.monotonic() + event_timeout
        by_key: dict[str, dict[str, Any]] = {}
        start_millis = str(max(0, int((started_at.timestamp() - 120) * 1000)))

        while time.monotonic() < deadline and not expected_keys.issubset(by_key.keys()):
            for key in sorted(expected_keys - set(by_key)):
                cro = key.split("/", 1)[0]
                route = self._route_for(cro, detail_type)
                response = self._run_json(
                    "logs",
                    "filter-log-events",
                    "--log-group-name",
                    route.log_group_name,
                    "--start-time",
                    start_millis,
                    "--filter-pattern",
                    f'"{key}"',
                    "--limit",
                    "10",
                )
                for event in response.get("events", []):
                    body = json.loads(event.get("message", "{}"))
                    event_time = self._event_time(body)
                    if (
                        event_time is not None
                        and event_time >= started_at
                        and self._is_expected_event(body, key, detail_type=detail_type)
                    ):
                        by_key[key] = {
                            "received_at": datetime.now(timezone.utc).isoformat(),
                            "log_group": route.log_group_name,
                            "log_stream": event.get("logStreamName", ""),
                            "event_id": event.get("eventId", ""),
                            "view_url": self._log_event_view_url(log_group_name=route.log_group_name, key=key),
                            "event_time": body.get("time", ""),
                            "source": body.get("source", ""),
                            "detail_type": body.get("detail-type", ""),
                            "bucket": body.get("detail", {}).get("bucket", {}).get("name", ""),
                            "key": body.get("detail", {}).get("object", {}).get("key", ""),
                        }
                        break
            if expected_keys.issubset(by_key.keys()):
                break
            time.sleep(5)

        missing = expected_keys - set(by_key.keys())
        if missing:
            raise RuntimeError(f"Missing bucket audit [{detail_type}] events for keys: {sorted(missing)}")
        return by_key
