"""Generic Wielder topic publishing and consuming surfaces."""

import base64
import json
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wielder.wield.enumerator import WieldAction


def _plain_conf(value):
    if hasattr(value, "as_plain_ordered_dict"):
        return value.as_plain_ordered_dict()
    return value


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class WTopicProvider(str, Enum):
    AWS_SNS = "aws_sns"
    GCP_PUBSUB = "gcp_pubsub"


class WTopicRuntimeSurface(str, Enum):
    LOCAL_AWS = "local_aws"
    LOCAL_GCP = "local_gcp"
    AWS = "aws"
    GCP = "gcp"


class WTopicMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    message: dict[str, Any]
    attributes: dict[str, str] = Field(default_factory=dict)
    key: str = ""

    @field_validator("topic", "key")
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in WTopicMessage value [{value}]")
        return value

    @classmethod
    def from_envelope(
        cls,
        *,
        topic: str,
        envelope: "WTopicEventEnvelope",
        key: str = "",
        attributes: dict[str, str] | None = None,
        projected_provenance_keys: tuple[str, ...] = (),
    ) -> "WTopicMessage":
        return cls(
            topic=topic,
            key=key,
            message=envelope.to_message(projected_provenance_keys=projected_provenance_keys),
            attributes={**envelope.attributes(), **(attributes or {})},
        )


class WTopicEventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    event_type: str
    event_time: str = Field(default_factory=_utc_now_iso)
    status: str = ""
    source_event: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("schema_version", "event_type", "event_time", "status")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return value.strip()

    @classmethod
    def build(
        cls,
        *,
        schema_version: str,
        event_type: str,
        status: str = "",
        source_event: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        event_time: str | None = None,
    ) -> "WTopicEventEnvelope":
        source = cls.source_event_summary(source_event or {})
        source_provenance = cls.source_provenance(source_event or {})
        resolved_provenance = _dict_or_empty(provenance) or source_provenance
        if resolved_provenance:
            source["provenance"] = resolved_provenance
        return cls(
            schema_version=schema_version,
            event_type=event_type,
            event_time=event_time or _utc_now_iso(),
            status=status,
            source_event=source,
            provenance=resolved_provenance,
            payload=payload or {},
        )

    @classmethod
    def from_message(cls, message: dict[str, Any]) -> "WTopicEventEnvelope":
        if "payload" in message or "source_event" in message or "provenance" in message:
            return cls.model_validate({
                "schema_version": message.get("schema_version", ""),
                "event_type": message.get("event_type", ""),
                "event_time": message.get("event_time", ""),
                "status": message.get("status", ""),
                "source_event": message.get("source_event", {}),
                "provenance": message.get("provenance", {}),
                "payload": message.get("payload", {}),
            })
        return cls.build(
            schema_version=str(message.get("schema_version") or "wtopic.event.v1"),
            event_type=str(message.get("event_type") or ""),
            event_time=str(message.get("event_time") or ""),
            status=str(message.get("status") or ""),
            source_event=message,
            payload={
                key: value
                for key, value in message.items()
                if key not in {"schema_version", "event_type", "event_time", "status", "provenance"}
            },
        )

    def to_message(self, *, projected_provenance_keys: tuple[str, ...] = ()) -> dict[str, Any]:
        message = self.model_dump(mode="json")
        message.update(self.projected_provenance_fields(
            self.source_event,
            provenance=self.provenance,
            keys=projected_provenance_keys,
        ))
        return message

    def attributes(self) -> dict[str, str]:
        attributes = {
            "schema_version": self.schema_version,
            "event_type": self.event_type,
        }
        if self.status:
            attributes["status"] = self.status
        return attributes

    @classmethod
    def source_provenance(cls, source_event: dict[str, Any]) -> dict[str, Any]:
        event = _dict_or_empty(source_event)
        raw_event = _dict_or_empty(event.get("raw_event"))
        return _dict_or_empty(event.get("provenance")) or _dict_or_empty(raw_event.get("provenance"))

    @classmethod
    def source_event_summary(cls, source_event: dict[str, Any]) -> dict[str, Any]:
        event = _dict_or_empty(source_event)
        raw_event = _dict_or_empty(event.get("raw_event"))
        bucket = str(event.get("bucket") or raw_event.get("bucket") or "")
        object_key = str(event.get("object_key") or event.get("name") or raw_event.get("object_key") or "").strip("/")
        uri = str(event.get("uri") or raw_event.get("uri") or "")
        if not uri and bucket and object_key:
            source = str(event.get("source") or raw_event.get("source") or "")
            scheme = "gs" if "gcp" in source or "google" in source else "s3"
            uri = f"{scheme}://{bucket}/{object_key}"
        return {
            "bucket": bucket,
            "object_key": object_key,
            "uri": uri or object_key or bucket or "<unknown file/blob>",
            "event_id": str(event.get("event_id") or event.get("id") or raw_event.get("event_id") or raw_event.get("id") or ""),
            "event_time": str(event.get("event_time") or event.get("time") or raw_event.get("event_time") or raw_event.get("time") or ""),
            "object_last_modified": str(event.get("object_last_modified") or raw_event.get("object_last_modified") or ""),
            "etag": str(event.get("etag") or raw_event.get("etag") or ""),
            "version_id": str(event.get("version_id") or raw_event.get("version_id") or ""),
            "size": event.get("size", raw_event.get("size")),
            "source": str(event.get("source") or raw_event.get("source") or ""),
            "provenance": cls.source_provenance(event),
        }

    @classmethod
    def projected_provenance_fields(
        cls,
        source_event: dict[str, Any],
        *,
        provenance: dict[str, Any] | None = None,
        keys: tuple[str, ...],
    ) -> dict[str, str]:
        if not keys:
            return {}
        event = _dict_or_empty(source_event)
        raw_event = _dict_or_empty(event.get("raw_event"))
        resolved_provenance = _dict_or_empty(provenance) or cls.source_provenance(event)
        fields: dict[str, str] = {}
        for key in keys:
            value = event.get(key) or raw_event.get(key) or resolved_provenance.get(key)
            if value is not None and str(value).strip():
                fields[key] = str(value)
        return fields


class WTopicPublisherConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: WTopicProvider
    project_id: str | None = None
    aws_region: str | None = None
    aws_account_id: str | None = None
    aws_profile: str = ""

    @classmethod
    def from_conf(cls, conf) -> "WTopicPublisherConfig":
        return cls.model_validate(_plain_conf(conf))

    @field_validator("project_id", "aws_region", "aws_account_id", "aws_profile")
    @classmethod
    def validate_token(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in WTopicPublisherConfig value [{value}]")
        return value.strip()

    @model_validator(mode="after")
    def validate_provider_contract(self):
        if self.provider == WTopicProvider.GCP_PUBSUB and not self.project_id:
            raise ValueError("GCP Pub/Sub publishing requires project_id")
        if self.provider == WTopicProvider.AWS_SNS and (not self.aws_region or not self.aws_account_id):
            raise ValueError("AWS SNS publishing requires aws_region and aws_account_id")
        return self


class WTopicPublisher(ABC):
    def __init__(self, config: WTopicPublisherConfig) -> None:
        self.config = config

    @classmethod
    def from_conf(cls, conf) -> "WTopicPublisher":
        config = WTopicPublisherConfig.from_conf(conf)
        match config.provider:
            case WTopicProvider.AWS_SNS:
                return WAwsSnsTopicPublisher(config)
            case WTopicProvider.GCP_PUBSUB:
                return WGcpPubSubTopicPublisher(config)
        raise ValueError(f"Unsupported WTopicPublisher provider [{config.provider}]")

    @abstractmethod
    def command_for(self, message: WTopicMessage) -> list[str]:
        raise NotImplementedError

    def plan(self, messages: list[WTopicMessage]) -> list[dict[str, Any]]:
        return [
            {
                "provider": self.config.provider.value,
                "key": message.key,
                "topic": message.topic,
                "message": message.message,
                "attributes": message.attributes,
                "command": self.command_for(message),
            }
            for message in messages
        ]

    @staticmethod
    def print_plan(records: list[dict[str, Any]], *, empty_message: str = "No topic messages are enabled in config.") -> None:
        if not records:
            print(empty_message)
            return
        print(json.dumps(records, indent=2, sort_keys=True))

    @staticmethod
    def publish(records: list[dict[str, Any]]) -> None:
        for record in records:
            print()
            print("publish topic message")
            print(f"provider: {record['provider']}")
            print(f"topic: {record['topic']}")
            if record.get("key"):
                print(f"key: {record['key']}")
            if record.get("attributes"):
                print("attributes:")
                print(json.dumps(record["attributes"], indent=2, sort_keys=True))
            print("message:")
            print(json.dumps(record["message"], indent=2, sort_keys=True))
            print()
            subprocess.run(record["command"], check=True)

    def wield(
        self,
        action: WieldAction | str,
        messages: list[WTopicMessage],
        *,
        empty_message: str = "No topic messages are enabled in config.",
    ) -> list[dict[str, Any]]:
        action = action if isinstance(action, WieldAction) else WieldAction(str(action))
        records = self.plan(messages)
        if action in {WieldAction.SHOW, WieldAction.PLAN, WieldAction.PROBE}:
            self.print_plan(records, empty_message=empty_message)
            return records
        if action in {WieldAction.APPLY, WieldAction.RUN}:
            if not records:
                self.print_plan(records, empty_message=empty_message)
                return records
            self.publish(records)
            return records
        self.print_plan(records, empty_message=empty_message)
        return records


class WAwsSnsTopicPublisher(WTopicPublisher):
    def topic_arn(self, topic_ref: str) -> str:
        if topic_ref.startswith("arn:aws:sns:"):
            return topic_ref
        return f"arn:aws:sns:{self.config.aws_region}:{self.config.aws_account_id}:{topic_ref}"

    def command_for(self, message: WTopicMessage) -> list[str]:
        message_attributes = {
            key: {"DataType": "String", "StringValue": str(value)}
            for key, value in message.attributes.items()
            if value
        }
        command = [
            "aws",
            "sns",
            "publish",
            "--topic-arn",
            self.topic_arn(message.topic),
            "--message",
            json.dumps(message.message, sort_keys=True),
            "--message-attributes",
            json.dumps(message_attributes, sort_keys=True),
            "--region",
            str(self.config.aws_region),
        ]
        if self.config.aws_profile:
            command.extend(["--profile", self.config.aws_profile])
        return command


class WGcpPubSubTopicPublisher(WTopicPublisher):
    def command_for(self, message: WTopicMessage) -> list[str]:
        attribute_arg = ",".join(f"{key}={value}" for key, value in message.attributes.items() if value)
        command = [
            "gcloud",
            "pubsub",
            "topics",
            "publish",
            message.topic,
            f"--project={self.config.project_id}",
            f"--message={json.dumps(message.message, sort_keys=True)}",
        ]
        if attribute_arg:
            command.append(f"--attribute={attribute_arg}")
        return command


class WTopicEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    role: str

    @field_validator("topic", "role")
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("WTopicEndpoint values must not be empty")
        return value


class WTopicConsumerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: WTopicProvider
    runtime_surface: WTopicRuntimeSurface
    topics: dict[str, WTopicEndpoint] = Field(default_factory=dict)
    pull_limit: int = 10
    project_id: str | None = None
    subscription_prefix: str | None = None
    create_subscriptions: bool = False
    auto_ack: bool = False
    aws_region: str | None = None
    aws_account_id: str | None = None
    aws_profile: str = ""
    queue_name: str | None = None
    create_queue: bool = False
    subscribe_topics: bool = False
    wait_time_seconds: int = 5
    visibility_timeout_seconds: int = 30
    auto_delete: bool = False
    print_messages: bool = True
    poll_mode: str = "once"
    poll_interval_seconds: int = 5
    max_polls: int | None = 1
    stop_after_empty_poll: bool = False
    command_timeout_seconds: int = 15

    @classmethod
    def from_conf(cls, conf) -> "WTopicConsumerConfig":
        data = dict(_plain_conf(conf))
        if hasattr(conf, "topics"):
            data["topics"] = {
                str(topic_key): _plain_conf(topic_conf)
                for topic_key, topic_conf in conf.topics.items()
            }
        return cls.model_validate(data)

    @field_validator(
        "project_id",
        "subscription_prefix",
        "aws_region",
        "aws_account_id",
        "aws_profile",
        "queue_name",
    )
    @classmethod
    def validate_token(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if "\\" in value:
            raise ValueError(f"backslash is not allowed in WTopicConsumerConfig value [{value}]")
        return value.strip()

    @model_validator(mode="after")
    def validate_provider_contract(self):
        if not self.topics:
            raise ValueError("WTopicConsumerConfig topics must not be empty")
        if self.pull_limit < 1:
            raise ValueError("WTopicConsumerConfig pull_limit must be >= 1")
        if self.poll_mode not in {"once", "loop"}:
            raise ValueError("WTopicConsumerConfig poll_mode must be one of: once, loop")
        if self.poll_interval_seconds < 0:
            raise ValueError("WTopicConsumerConfig poll_interval_seconds must be >= 0")
        if self.max_polls is not None and self.max_polls < 1:
            raise ValueError("WTopicConsumerConfig max_polls must be >= 1 when configured")
        if self.command_timeout_seconds < 1:
            raise ValueError("WTopicConsumerConfig command_timeout_seconds must be >= 1")
        aws_surfaces = {WTopicRuntimeSurface.AWS, WTopicRuntimeSurface.LOCAL_AWS}
        gcp_surfaces = {WTopicRuntimeSurface.GCP, WTopicRuntimeSurface.LOCAL_GCP}
        if self.runtime_surface in aws_surfaces and self.provider != WTopicProvider.AWS_SNS:
            raise ValueError("AWS topic runtime_surface requires provider=aws_sns")
        if self.runtime_surface in gcp_surfaces and self.provider != WTopicProvider.GCP_PUBSUB:
            raise ValueError("GCP topic runtime_surface requires provider=gcp_pubsub")
        if self.provider == WTopicProvider.GCP_PUBSUB:
            if not self.project_id or not self.subscription_prefix:
                raise ValueError("GCP Pub/Sub consuming requires project_id and subscription_prefix")
        if self.provider == WTopicProvider.AWS_SNS:
            if not self.aws_region or not self.aws_account_id or not self.queue_name:
                raise ValueError("AWS SNS consuming requires aws_region, aws_account_id, and queue_name")
        return self


class WTopicConsumer(ABC):
    def __init__(self, config: WTopicConsumerConfig) -> None:
        self.config = config

    @classmethod
    def from_conf(cls, conf) -> "WTopicConsumer":
        config = WTopicConsumerConfig.from_conf(conf)
        match config.provider:
            case WTopicProvider.AWS_SNS:
                return WAwsSnsTopicConsumer(config)
            case WTopicProvider.GCP_PUBSUB:
                return WGcpPubSubTopicConsumer(config)
        raise ValueError(f"Unsupported WTopicConsumer provider [{config.provider}]")

    @abstractmethod
    def plan(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def receive_records_once(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @staticmethod
    def _json_or_text(value: str) -> Any:
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return value

    @classmethod
    def _record_for_display(cls, record: dict[str, Any]) -> dict[str, Any]:
        if record.get("provider") == "aws_sns":
            message = record.get("message", {})
            body = message.get("Body", "")
            display_record = {
                "provider": record.get("provider"),
                "queue_name": record.get("queue_name"),
                "message_id": message.get("MessageId", ""),
                "receive_count": message.get("Attributes", {}).get("ApproximateReceiveCount", ""),
                "sent_timestamp": message.get("Attributes", {}).get("SentTimestamp", ""),
            }
            if body:
                display_record["decoded_message"] = cls._json_or_text(body)
            return display_record

        display_record = dict(record)
        if record.get("provider") == "gcp_pubsub":
            data = record.get("message", {}).get("message", {}).get("data", "")
            if data:
                try:
                    decoded_data = base64.b64decode(data).decode("utf-8")
                    display_record["decoded_data"] = decoded_data
                    display_record["decoded_message"] = cls._json_or_text(decoded_data)
                except Exception:
                    display_record["decoded_data"] = str(data)
                    display_record["decoded_message"] = data
        return display_record

    @staticmethod
    def print_message_records(records: list[dict[str, Any]]) -> None:
        if not records:
            print()
            print("[]")
            print()
            return
        for record in records:
            print()
            print(json.dumps(WTopicConsumer._record_for_display(record), indent=2, sort_keys=True))
            print()

    @staticmethod
    def _dispatch_callback(callback: Callable[[dict[str, Any]], None], record: dict[str, Any]) -> None:
        callback(record)

    def ack_records(self, records: list[dict[str, Any]]) -> None:
        return None

    def consume_once(self, callback: Callable[[dict[str, Any]], None] | None = None) -> list[dict[str, Any]]:
        records = self.receive_records_once()
        if callback is None:
            if self.config.print_messages:
                self.print_message_records(records)
            if self.config.auto_delete:
                self.ack_records(records)
            return records
        for record in records:
            self._dispatch_callback(callback, record)
        if self.config.auto_delete:
            self.ack_records(records)
        return records

    def status_report(self) -> dict[str, Any]:
        return {
            "provider": self.config.provider.value,
            "topics": [
                {
                    "topic_key": topic_key,
                    "topic": topic.topic,
                    "role": topic.role,
                }
                for topic_key, topic in self.config.topics.items()
            ],
        }

    def clear_records(self) -> list[dict[str, Any]]:
        raise NotImplementedError(f"{self.__class__.__name__} does not implement clear_records().")

    def subscribe(
        self,
        callback: Callable[[dict[str, Any]], None] | None = None,
        *,
        stop_event: threading.Event | None = None,
    ) -> None:
        match self.config.runtime_surface:
            case (
                WTopicRuntimeSurface.LOCAL_AWS
                | WTopicRuntimeSurface.LOCAL_GCP
                | WTopicRuntimeSurface.AWS
                | WTopicRuntimeSurface.GCP
            ):
                return self.poll_provider_topic(callback=callback, stop_event=stop_event)
        raise ValueError(f"Unsupported topic runtime_surface [{self.config.runtime_surface}]")

    def consume(
        self,
        callback: Callable[[dict[str, Any]], None] | None = None,
        *,
        stop_event: threading.Event | None = None,
    ) -> None:
        return self.subscribe(callback=callback, stop_event=stop_event)

    def poll_provider_topic(
        self,
        callback: Callable[[dict[str, Any]], None] | None = None,
        *,
        stop_event: threading.Event | None = None,
    ) -> None:
        poll_count = 0
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            poll_count += 1
            if self.config.print_messages:
                print()
                print(f"poll: {poll_count}")
                print(f"mode: {self.config.poll_mode}")
                print()
            records = self.consume_once(callback=callback)
            if self.config.poll_mode == "once":
                return
            if self.config.stop_after_empty_poll and not records:
                return
            if self.config.max_polls is not None and poll_count >= self.config.max_polls:
                return
            if self.config.poll_interval_seconds:
                if stop_event is None:
                    time.sleep(self.config.poll_interval_seconds)
                elif stop_event.wait(self.config.poll_interval_seconds):
                    return

    def native_subscribe(
        self,
        callback: Callable[[dict[str, Any]], None] | None = None,
        *,
        stop_event: threading.Event | None = None,
    ) -> None:
        match self.config.runtime_surface:
            case WTopicRuntimeSurface.AWS:
                return self.consume_aws(callback=callback, stop_event=stop_event)
            case WTopicRuntimeSurface.GCP:
                return self.consume_gcp(callback=callback, stop_event=stop_event)
        raise ValueError(f"Unsupported topic runtime_surface [{self.config.runtime_surface}]")

    def local_provider_poll(
        self,
        callback: Callable[[dict[str, Any]], None] | None = None,
        *,
        stop_event: threading.Event | None = None,
    ) -> None:
        return self.poll_provider_topic(callback=callback, stop_event=stop_event)

    def consume_aws(
        self,
        callback: Callable[[dict[str, Any]], None] | None = None,
        *,
        stop_event: threading.Event | None = None,
    ) -> None:
        return self.poll_provider_topic(callback=callback, stop_event=stop_event)

    def consume_gcp(
        self,
        callback: Callable[[dict[str, Any]], None] | None = None,
        *,
        stop_event: threading.Event | None = None,
    ) -> None:
        return self.poll_provider_topic(callback=callback, stop_event=stop_event)

    @staticmethod
    def print_plan(records: list[dict[str, Any]]) -> None:
        print(json.dumps(records, indent=2, sort_keys=True))

    def wield(self, action: WieldAction | str) -> list[dict[str, Any]]:
        action = action if isinstance(action, WieldAction) else WieldAction(str(action))
        records = self.plan()
        if action in {WieldAction.SHOW, WieldAction.PLAN, WieldAction.PROBE}:
            self.print_plan(records)
            return records
        if action in {WieldAction.APPLY, WieldAction.MONITOR, WieldAction.RUN}:
            self.subscribe()
            return records
        self.print_plan(records)
        return records


class WGcpPubSubTopicConsumer(WTopicConsumer):
    def plan(self) -> list[dict[str, Any]]:
        records = []
        for topic_key, topic_conf in self.config.topics.items():
            subscription = f"{self.config.subscription_prefix}-{topic_key}"
            create_command = [
                "gcloud",
                "pubsub",
                "subscriptions",
                "create",
                subscription,
                f"--topic={topic_conf.topic}",
                f"--project={self.config.project_id}",
                "--expiration-period=1d",
            ]
            pull_command = [
                "gcloud",
                "pubsub",
                "subscriptions",
                "pull",
                subscription,
                f"--project={self.config.project_id}",
                f"--limit={self.config.pull_limit}",
                "--format=json",
            ]
            if self.config.auto_ack:
                pull_command.append("--auto-ack")
            records.append(
                {
                    "provider": self.config.provider.value,
                    "runtime_surface": self.config.runtime_surface.value,
                    "topic_key": topic_key,
                    "topic": topic_conf.topic,
                    "role": topic_conf.role,
                    "subscription": subscription,
                    "create_subscription": self.config.create_subscriptions,
                    "poll_mode": self.config.poll_mode,
                    "poll_interval_seconds": self.config.poll_interval_seconds,
                    "max_polls": self.config.max_polls,
                    "stop_after_empty_poll": self.config.stop_after_empty_poll,
                    "print_messages": self.config.print_messages,
                    "create_command": create_command,
                    "pull_command": pull_command,
                }
            )
        return records

    @staticmethod
    def _subscription_exists(subscription: str, project_id: str) -> bool:
        command = [
            "gcloud",
            "pubsub",
            "subscriptions",
            "describe",
            subscription,
            f"--project={project_id}",
            "--format=value(name)",
        ]
        return subprocess.run(command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0

    def _ensure_subscription(self, record: dict[str, Any]) -> None:
        if self._subscription_exists(record["subscription"], str(self.config.project_id)):
            return
        subprocess.run(record["create_command"], check=True)

    def receive_records_once(self) -> list[dict[str, Any]]:
        records = []
        for record in self.plan():
            if self.config.print_messages:
                print()
                print("provider: GCP Pub/Sub")
                print(f"project: {self.config.project_id}")
                print(f"topic: {record['topic']}")
                print(f"role: {record['role']}")
                print(f"subscription: {record['subscription']}")
                print()
            if self.config.create_subscriptions:
                self._ensure_subscription(record)
            try:
                result = subprocess.run(
                    record["pull_command"],
                    check=False,
                    text=True,
                    capture_output=True,
                    timeout=self.config.command_timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                records.append(
                    {
                        "provider": "gcp_pubsub",
                        "topic_key": record["topic_key"],
                        "topic": record["topic"],
                        "role": record["role"],
                        "subscription": record["subscription"],
                        "timeout": True,
                        "timeout_seconds": self.config.command_timeout_seconds,
                        "message": {},
                    }
                )
                continue
            payload = json.loads(result.stdout) if result.stdout.strip() else []
            for item in payload:
                records.append(
                    {
                        "provider": "gcp_pubsub",
                        "topic_key": record["topic_key"],
                        "topic": record["topic"],
                        "role": record["role"],
                        "subscription": record["subscription"],
                        "message": item,
                    }
                )
        return records

    def clear_records(self) -> list[dict[str, Any]]:
        cleared_at = datetime.now(timezone.utc).isoformat()
        records = []
        for record in self.plan():
            if not self.config.create_subscriptions and not self._subscription_exists(
                record["subscription"],
                str(self.config.project_id),
            ):
                records.append(
                    {
                        "provider": "gcp_pubsub",
                        "topic_key": record["topic_key"],
                        "topic": record["topic"],
                        "subscription": record["subscription"],
                        "cleared_at": cleared_at,
                        "status": "missing",
                    }
                )
                continue
            if self.config.create_subscriptions:
                self._ensure_subscription(record)
            command = [
                "gcloud",
                "pubsub",
                "subscriptions",
                "seek",
                record["subscription"],
                f"--time={cleared_at}",
                f"--project={self.config.project_id}",
            ]
            result = subprocess.run(command, check=False, text=True, capture_output=True)
            records.append(
                {
                    "provider": "gcp_pubsub",
                    "topic_key": record["topic_key"],
                    "topic": record["topic"],
                    "subscription": record["subscription"],
                    "cleared_at": cleared_at,
                    "status": "cleared",
                    "command": command,
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"GCP Pub/Sub subscription clear failed for [{record['subscription']}]: {result.stderr.strip()}"
                )
        return records


class WAwsSnsTopicConsumer(WTopicConsumer):
    def topic_arn(self, topic_ref: str) -> str:
        if topic_ref.startswith("arn:aws:sns:"):
            return topic_ref
        return f"arn:aws:sns:{self.config.aws_region}:{self.config.aws_account_id}:{topic_ref}"

    def aws_command(self, *args: str) -> list[str]:
        command = ["aws", *args, "--region", str(self.config.aws_region)]
        if self.config.aws_profile:
            command.extend(["--profile", self.config.aws_profile])
        return command

    def plan(self) -> list[dict[str, Any]]:
        topic_arns = {
            topic_key: self.topic_arn(topic_conf.topic)
            for topic_key, topic_conf in self.config.topics.items()
        }
        return [
            {
                "provider": self.config.provider.value,
                "runtime_surface": self.config.runtime_surface.value,
                "queue_name": self.config.queue_name,
                "create_queue": self.config.create_queue,
                "subscribe_topics": self.config.subscribe_topics,
                "auto_delete": self.config.auto_delete,
                "print_messages": self.config.print_messages,
                "poll_mode": self.config.poll_mode,
                "poll_interval_seconds": self.config.poll_interval_seconds,
                "max_polls": self.config.max_polls,
                "stop_after_empty_poll": self.config.stop_after_empty_poll,
                "topics": [
                    {
                        "topic_key": topic_key,
                        "topic": topic_conf.topic,
                        "topic_arn": topic_arns[topic_key],
                        "role": topic_conf.role,
                    }
                    for topic_key, topic_conf in self.config.topics.items()
                ],
                "create_queue_command": self.aws_command(
                    "sqs",
                    "create-queue",
                    "--queue-name",
                    str(self.config.queue_name),
                    "--attributes",
                    json.dumps({"VisibilityTimeout": str(self.config.visibility_timeout_seconds)}),
                ),
                "subscribe_commands": [
                    self.aws_command(
                        "sns",
                        "subscribe",
                        "--topic-arn",
                        topic_arns[topic_key],
                        "--protocol",
                        "sqs",
                        "--notification-endpoint",
                        "<resolved_queue_arn>",
                        "--attributes",
                        "RawMessageDelivery=true",
                    )
                    for topic_key in self.config.topics
                ],
                "receive_command": self.aws_command(
                    "sqs",
                    "receive-message",
                    "--queue-url",
                    "<resolved_queue_url>",
                    "--max-number-of-messages",
                    str(min(self.config.pull_limit, 10)),
                    "--wait-time-seconds",
                    str(self.config.wait_time_seconds),
                    "--visibility-timeout",
                    str(self.config.visibility_timeout_seconds),
                    "--attribute-names",
                    "All",
                    "--message-attribute-names",
                    "All",
                ),
            }
        ]

    def _run_json(self, command: list[str], *, check: bool = True) -> dict[str, Any]:
        try:
            result = subprocess.run(command, check=check, text=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            detail = f" stderr: {stderr}" if stderr else ""
            if stdout:
                detail = f"{detail} stdout: {stdout}"
            raise RuntimeError(f"Command {exc.cmd!r} failed with exit code {exc.returncode}.{detail}") from exc
        if not result.stdout.strip():
            return {}
        return json.loads(result.stdout)

    def _queue_url(self) -> str | None:
        command = self.aws_command(
            "sqs",
            "get-queue-url",
            "--queue-name",
            str(self.config.queue_name),
        )
        result = subprocess.run(command, check=False, text=True, capture_output=True)
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)["QueueUrl"]

    def _ensure_queue_url(self) -> str:
        queue_url = self._queue_url()
        if queue_url:
            return queue_url
        if not self.config.create_queue:
            raise RuntimeError(f"AWS SNS consumer queue [{self.config.queue_name}] does not exist.")
        response = self._run_json(
            self.aws_command(
                "sqs",
                "create-queue",
                "--queue-name",
                str(self.config.queue_name),
                "--attributes",
                json.dumps({"VisibilityTimeout": str(self.config.visibility_timeout_seconds)}),
            )
        )
        return response["QueueUrl"]

    def _queue_arn(self, queue_url: str) -> str:
        response = self._run_json(
            self.aws_command(
                "sqs",
                "get-queue-attributes",
                "--queue-url",
                queue_url,
                "--attribute-names",
                "QueueArn",
            )
        )
        return response["Attributes"]["QueueArn"]

    def queue_attributes(self) -> dict[str, str]:
        queue_url = self._ensure_queue_url()
        response = self._run_json(
            self.aws_command(
                "sqs",
                "get-queue-attributes",
                "--queue-url",
                queue_url,
                "--attribute-names",
                "All",
            )
        )
        return response.get("Attributes", {})

    def status_report(self) -> dict[str, Any]:
        queue_url = self._ensure_queue_url()
        attrs = self.queue_attributes()
        expected_topic_arns = [
            self.topic_arn(topic.topic)
            for topic in self.config.topics.values()
        ]
        queue_policy = attrs.get("Policy", "")
        missing_policy_topics = [
            topic_arn for topic_arn in expected_topic_arns if topic_arn not in queue_policy
        ]
        return {
            "provider": self.config.provider.value,
            "queue_name": self.config.queue_name,
            "queue_url": queue_url,
            "queue_arn": attrs.get("QueueArn", ""),
            "queue_depth": attrs.get("ApproximateNumberOfMessages", ""),
            "queue_not_visible": attrs.get("ApproximateNumberOfMessagesNotVisible", ""),
            "queue_policy": queue_policy,
            "expected_topic_arns": expected_topic_arns,
            "missing_queue_policy_topics": missing_policy_topics,
            "topics": [
                {
                    "topic_key": topic_key,
                    "topic": topic.topic,
                    "topic_arn": self.topic_arn(topic.topic),
                    "role": topic.role,
                }
                for topic_key, topic in self.config.topics.items()
            ],
        }

    def _set_queue_policy(self, queue_url: str, queue_arn: str) -> None:
        topic_arns = [self.topic_arn(topic.topic) for topic in self.config.topics.values()]
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AllowConfiguredSnsTopicsToPublish",
                    "Effect": "Allow",
                    "Principal": {"Service": "sns.amazonaws.com"},
                    "Action": "sqs:SendMessage",
                    "Resource": queue_arn,
                    "Condition": {"ArnEquals": {"aws:SourceArn": topic_arns}},
                }
            ],
        }
        subprocess.run(
            self.aws_command(
                "sqs",
                "set-queue-attributes",
                "--queue-url",
                queue_url,
                "--attributes",
                json.dumps({"Policy": json.dumps(policy)}),
            ),
            check=True,
        )

    def _subscribe_topics(self, queue_arn: str) -> None:
        for topic in self.config.topics.values():
            topic_arn = self.topic_arn(topic.topic)
            subscriptions = self._run_json(
                self.aws_command("sns", "list-subscriptions-by-topic", "--topic-arn", topic_arn)
            ).get("Subscriptions", [])
            if any(subscription.get("Endpoint") == queue_arn for subscription in subscriptions):
                continue
            subprocess.run(
                self.aws_command(
                    "sns",
                    "subscribe",
                    "--topic-arn",
                    topic_arn,
                    "--protocol",
                    "sqs",
                    "--notification-endpoint",
                    queue_arn,
                    "--attributes",
                    "RawMessageDelivery=true",
                ),
                check=True,
            )

    def _delete_messages(self, queue_url: str, messages: list[dict[str, Any]]) -> None:
        for message in messages:
            receipt_handle = message.get("ReceiptHandle")
            if not receipt_handle:
                continue
            subprocess.run(
                self.aws_command(
                    "sqs",
                    "delete-message",
                    "--queue-url",
                    queue_url,
                    "--receipt-handle",
                    receipt_handle,
                ),
                check=True,
            )

    def receive_records_once(self) -> list[dict[str, Any]]:
        queue_url = self._ensure_queue_url()
        queue_arn = self._queue_arn(queue_url)
        if self.config.subscribe_topics:
            self._set_queue_policy(queue_url, queue_arn)
            self._subscribe_topics(queue_arn)

        response = self._run_json(
            self.aws_command(
                "sqs",
                "receive-message",
                "--queue-url",
                queue_url,
                "--max-number-of-messages",
                str(min(self.config.pull_limit, 10)),
                "--wait-time-seconds",
                str(self.config.wait_time_seconds),
                "--visibility-timeout",
                str(self.config.visibility_timeout_seconds),
                "--attribute-names",
                "All",
                "--message-attribute-names",
                "All",
            ),
        )
        messages = response.get("Messages", [])
        if self.config.print_messages:
            print()
            print("provider: AWS SNS/SQS")
            print(f"queue: {self.config.queue_name}")
            print(f"messages: {len(messages)}")
            print()
        records = []
        for message in messages:
            records.append(
                {
                    "provider": "aws_sns",
                    "queue_name": self.config.queue_name,
                    "queue_url": queue_url,
                    "message": message,
                }
            )
        return records

    def ack_records(self, records: list[dict[str, Any]]) -> None:
        messages = [
            record["message"]
            for record in records
            if record.get("provider") == "aws_sns" and record.get("message")
        ]
        self._delete_messages(self._ensure_queue_url(), messages)

    def clear_records(self) -> list[dict[str, Any]]:
        queue_url = self._ensure_queue_url()
        command = self.aws_command("sqs", "purge-queue", "--queue-url", queue_url)
        result = subprocess.run(command, check=False, text=True, capture_output=True)
        stderr = result.stderr.strip()
        status = "cleared"
        if result.returncode != 0 and "PurgeQueueInProgress" in stderr:
            status = "already_clearing"
        elif result.returncode != 0:
            raise RuntimeError(f"AWS SQS queue clear failed for [{self.config.queue_name}]: {stderr}")
        return [
            {
                "provider": "aws_sns",
                "queue_name": self.config.queue_name,
                "queue_url": queue_url,
                "status": status,
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        ]
