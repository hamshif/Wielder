"""Provider-neutral storage event normalization and consumer surfaces."""

from __future__ import annotations

import base64
import json
import threading
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable
from urllib.parse import unquote, unquote_plus

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wielder.util.wtopic import WTopicConsumer, WTopicConsumerConfig, WTopicProvider


class WStorageEventType(str, Enum):
    OBJECT_CREATED = "object.created"
    OBJECT_DELETED = "object.deleted"


class WStorageSourceProvider(str, Enum):
    AWS = "aws"
    GCP = "gcp"
    LOCAL = "local"
    UNKNOWN = "unknown"


class WStorageEventConsumerSurface(str, Enum):
    AWS_S3 = "aws_s3"
    GCP_GCS = "gcp_gcs"


class WStorageEventObserverProvider(str, Enum):
    AWS = "aws"
    GCP = "gcp"
    LOCAL = "local"


def _plain_conf(value: Any) -> Any:
    if hasattr(value, "as_plain_ordered_dict"):
        return value.as_plain_ordered_dict()
    return value


class WStorageEventConsumerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    surface: WStorageEventConsumerSurface
    topic_consumer: WTopicConsumerConfig

    @classmethod
    def from_conf(cls, conf) -> "WStorageEventConsumerConfig":
        data = dict(_plain_conf(conf))
        if "topic_consumer" in data:
            data["topic_consumer"] = _plain_conf(data["topic_consumer"])
        else:
            topic_consumer_keys = set(WTopicConsumerConfig.model_fields)
            topic_consumer_conf = {
                key: data.pop(key)
                for key in list(data)
                if key in topic_consumer_keys
            }
            data["topic_consumer"] = topic_consumer_conf
        return cls.model_validate(data)

    @model_validator(mode="after")
    def validate_surface_contract(self):
        if (
            self.surface == WStorageEventConsumerSurface.AWS_S3
            and self.topic_consumer.provider != WTopicProvider.AWS_SNS
        ):
            raise ValueError("aws_s3 storage event consumer requires an aws_sns topic_consumer")
        if (
            self.surface == WStorageEventConsumerSurface.GCP_GCS
            and self.topic_consumer.provider != WTopicProvider.GCP_PUBSUB
        ):
            raise ValueError("gcp_gcs storage event consumer requires a gcp_pubsub topic_consumer")
        return self


class WStorageEventObserverConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: WStorageEventObserverProvider
    storage_event_consumer: WStorageEventConsumerConfig | None = None

    @classmethod
    def from_conf(cls, conf) -> "WStorageEventObserverConfig":
        data = dict(_plain_conf(conf))
        if "storage_event_consumer" in data:
            data["storage_event_consumer"] = WStorageEventConsumerConfig.from_conf(
                data["storage_event_consumer"]
            ).model_dump(mode="json")
        return cls.model_validate(data)

    @model_validator(mode="after")
    def validate_provider_contract(self):
        if self.provider in {
            WStorageEventObserverProvider.AWS,
            WStorageEventObserverProvider.GCP,
        } and self.storage_event_consumer is None:
            raise ValueError(f"{self.provider.value} storage event observer requires storage_event_consumer")
        return self


class WStorageEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: WStorageEventType
    bucket: str
    object_key: str
    uri: str = ""
    event_id: str = ""
    event_time: str = ""
    object_last_modified: str = ""
    etag: str = ""
    version_id: str = ""
    size: int | None = None
    source_provider: WStorageSourceProvider = WStorageSourceProvider.UNKNOWN
    raw_event: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "bucket",
        "object_key",
        "uri",
        "event_id",
        "event_time",
        "object_last_modified",
        "etag",
        "version_id",
    )
    @classmethod
    def validate_text(cls, value: str) -> str:
        return value.strip()

    def model_post_init(self, __context: Any) -> None:
        if not self.uri and self.bucket and self.object_key:
            object.__setattr__(self, "uri", f"{self._scheme()}://{self.bucket}/{self.object_key}")

    def _scheme(self) -> str:
        if self.source_provider == WStorageSourceProvider.GCP:
            return "gs"
        if self.source_provider == WStorageSourceProvider.LOCAL:
            return "file"
        return "s3"

    def to_legacy_storage_file_message(
        self,
        *,
        schema_version: str = "storage.object.v1",
        created_event_type: str = "new-storage-file",
        deleted_event_type: str = "deleted-storage-file",
        source: str | None = None,
    ) -> dict[str, Any]:
        event_type = (
            created_event_type
            if self.event_type == WStorageEventType.OBJECT_CREATED
            else deleted_event_type
        )
        provider_source = source or {
            WStorageSourceProvider.AWS: "aws.s3",
            WStorageSourceProvider.GCP: "gcp.storage",
            WStorageSourceProvider.LOCAL: "local.storage",
            WStorageSourceProvider.UNKNOWN: "unknown.storage",
        }[self.source_provider]
        return {
            "schema_version": schema_version,
            "event_type": event_type,
            "event_id": self.event_id,
            "event_time": self.event_time,
            "object_last_modified": self.object_last_modified,
            "bucket": self.bucket,
            "object_key": self.object_key,
            "etag": self.etag,
            "version_id": self.version_id,
            "size": self.size,
            "source": provider_source,
            "uri": self.uri,
            "raw_event": self.raw_event,
        }


class WStorageEventConsumer(ABC):
    @classmethod
    def from_conf(cls, conf) -> "WStorageEventConsumer":
        config = WStorageEventConsumerConfig.from_conf(conf)
        match config.surface:
            case WStorageEventConsumerSurface.AWS_S3:
                return WAwsS3StorageEventConsumer.from_config(config)
            case WStorageEventConsumerSurface.GCP_GCS:
                return WGcpGcsStorageEventConsumer.from_config(config)
        raise ValueError(f"Unsupported WStorageEventConsumer surface [{config.surface}]")

    @abstractmethod
    def plan(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def receive_once(self) -> list[WStorageEvent]:
        raise NotImplementedError

    @abstractmethod
    def subscribe(
        self,
        callback: Callable[[WStorageEvent], None],
        *,
        stop_event: threading.Event | None = None,
    ) -> None:
        raise NotImplementedError

    def listen(
        self,
        callback: Callable[[WStorageEvent], None],
        *,
        stop_event: threading.Event | None = None,
    ) -> None:
        return self.subscribe(callback, stop_event=stop_event)


class WStorageEventObserver:
    """Threaded storage-event observer for tests and operator probes."""

    def __init__(
        self,
        consumer: WStorageEventConsumer,
        *,
        callback: Callable[[WStorageEvent], None] | None = None,
        name: str = "wstorage-event-observer",
    ) -> None:
        self.consumer = consumer
        self.callback = callback
        self.name = name
        self.stop_event = threading.Event()
        self.lock = threading.RLock()
        self.events: list[WStorageEvent] = []
        self.error: Exception | None = None
        self.thread: threading.Thread | None = None

    @classmethod
    def from_consumer(
        cls,
        consumer: WStorageEventConsumer,
        *,
        callback: Callable[[WStorageEvent], None] | None = None,
        name: str = "wstorage-event-observer",
    ) -> "WStorageEventObserver":
        return cls(consumer, callback=callback, name=name)

    @classmethod
    def from_conf(
        cls,
        conf,
        *,
        callback: Callable[[WStorageEvent], None] | None = None,
        name: str = "wstorage-event-observer",
    ) -> "WStorageEventObserver":
        config = WStorageEventObserverConfig.from_conf(conf)
        match config.provider:
            case WStorageEventObserverProvider.AWS:
                return WAwsStorageEventObserver.from_config(config, callback=callback, name=name)
            case WStorageEventObserverProvider.GCP:
                return WGcpStorageEventObserver.from_config(config, callback=callback, name=name)
            case WStorageEventObserverProvider.LOCAL:
                return WLocalStorageEventObserver.from_config(config, callback=callback, name=name)
        raise ValueError(f"Unsupported WStorageEventObserver provider [{config.provider}]")

    @classmethod
    def from_provider(
        cls,
        *,
        provider: WStorageEventObserverProvider | str,
        storage_event_consumer_conf,
        callback: Callable[[WStorageEvent], None] | None = None,
        name: str = "wstorage-event-observer",
    ) -> "WStorageEventObserver":
        observer_provider = WStorageEventObserverProvider(str(provider))
        match observer_provider:
            case WStorageEventObserverProvider.AWS:
                return WAwsStorageEventObserver.from_storage_event_consumer_conf(
                    storage_event_consumer_conf,
                    callback=callback,
                    name=name,
                )
            case WStorageEventObserverProvider.GCP:
                return WGcpStorageEventObserver.from_storage_event_consumer_conf(
                    storage_event_consumer_conf,
                    callback=callback,
                    name=name,
                )
            case WStorageEventObserverProvider.LOCAL:
                raise NotImplementedError("Local storage event observer is not implemented yet.")
        raise ValueError(f"Unsupported WStorageEventObserver provider [{observer_provider}]")

    def start(self) -> "WStorageEventObserver":
        self.thread = threading.Thread(target=self._run, daemon=True, name=self.name)
        self.thread.start()
        return self

    def stop(self, timeout: float = 10) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=timeout)

    def snapshot(self) -> list[WStorageEvent]:
        with self.lock:
            return list(self.events)

    def event_records(self) -> list[dict[str, Any]]:
        return [event.model_dump(mode="json") for event in self.snapshot()]

    def matching_events(self, predicate: Callable[[WStorageEvent], bool]) -> list[WStorageEvent]:
        return [event for event in self.snapshot() if predicate(event)]

    def events_for_keys(
        self,
        expected_keys: set[str],
        *,
        event_type: WStorageEventType | str | None = None,
    ) -> list[WStorageEvent]:
        coerced_event_type = (
            event_type
            if isinstance(event_type, WStorageEventType) or event_type is None
            else WStorageEventType(str(event_type))
        )
        return self.matching_events(
            lambda event: event.object_key in expected_keys
            and (coerced_event_type is None or event.event_type == coerced_event_type)
        )

    def _run(self) -> None:
        try:
            self.consumer.subscribe(callback=self._record, stop_event=self.stop_event)
        except Exception as exc:  # noqa: BLE001 - callers inspect error after stop/wait.
            self.error = exc

    def _record(self, event: WStorageEvent) -> None:
        with self.lock:
            self.events.append(event)
        if self.callback is not None:
            self.callback(event)


class WAwsStorageEventObserver(WStorageEventObserver):
    provider = WStorageEventObserverProvider.AWS

    @classmethod
    def from_config(
        cls,
        config: WStorageEventObserverConfig,
        *,
        callback: Callable[[WStorageEvent], None] | None = None,
        name: str = "wstorage-event-observer",
    ) -> "WAwsStorageEventObserver":
        if config.provider != cls.provider:
            raise ValueError(f"WAwsStorageEventObserver cannot serve provider [{config.provider}]")
        if config.storage_event_consumer is None:
            raise ValueError("WAwsStorageEventObserver requires storage_event_consumer")
        return cls(
            WStorageEventConsumer.from_conf(config.storage_event_consumer.model_dump(mode="json")),
            callback=callback,
            name=name,
        )

    @classmethod
    def from_storage_event_consumer_conf(
        cls,
        storage_event_consumer_conf,
        *,
        callback: Callable[[WStorageEvent], None] | None = None,
        name: str = "wstorage-event-observer",
    ) -> "WAwsStorageEventObserver":
        return cls(
            WStorageEventConsumer.from_conf(storage_event_consumer_conf),
            callback=callback,
            name=name,
        )


class WGcpStorageEventObserver(WStorageEventObserver):
    provider = WStorageEventObserverProvider.GCP

    @classmethod
    def from_config(
        cls,
        config: WStorageEventObserverConfig,
        *,
        callback: Callable[[WStorageEvent], None] | None = None,
        name: str = "wstorage-event-observer",
    ) -> "WGcpStorageEventObserver":
        if config.provider != cls.provider:
            raise ValueError(f"WGcpStorageEventObserver cannot serve provider [{config.provider}]")
        if config.storage_event_consumer is None:
            raise ValueError("WGcpStorageEventObserver requires storage_event_consumer")
        return cls(
            WStorageEventConsumer.from_conf(config.storage_event_consumer.model_dump(mode="json")),
            callback=callback,
            name=name,
        )

    @classmethod
    def from_storage_event_consumer_conf(
        cls,
        storage_event_consumer_conf,
        *,
        callback: Callable[[WStorageEvent], None] | None = None,
        name: str = "wstorage-event-observer",
    ) -> "WGcpStorageEventObserver":
        return cls(
            WStorageEventConsumer.from_conf(storage_event_consumer_conf),
            callback=callback,
            name=name,
        )


class WLocalStorageEventObserver(WStorageEventObserver):
    provider = WStorageEventObserverProvider.LOCAL

    @classmethod
    def from_config(
        cls,
        config: WStorageEventObserverConfig,
        *,
        callback: Callable[[WStorageEvent], None] | None = None,
        name: str = "wstorage-event-observer",
    ) -> "WLocalStorageEventObserver":
        raise NotImplementedError("Local storage event observer is not implemented yet.")


class WTopicStorageEventConsumer(WStorageEventConsumer):
    def __init__(self, consumer: WTopicConsumer) -> None:
        self.consumer = consumer

    @classmethod
    def from_conf(cls, conf) -> "WTopicStorageEventConsumer":
        config = WStorageEventConsumerConfig.from_conf(conf)
        return cls(WTopicConsumer.from_conf(config.topic_consumer.model_dump(mode="json")))

    def plan(self) -> list[dict[str, Any]]:
        return self.consumer.plan()

    def receive_once(self) -> list[WStorageEvent]:
        events: list[WStorageEvent] = []
        for record in self.consumer.receive_records_once():
            events.extend(normalize_storage_events(decode_topic_storage_message(record)))
        return events

    def subscribe(
        self,
        callback: Callable[[WStorageEvent], None],
        *,
        stop_event: threading.Event | None = None,
    ) -> None:
        def topic_callback(record: dict[str, Any]) -> None:
            for event in normalize_storage_events(decode_topic_storage_message(record)):
                callback(event)

        self.consumer.subscribe(callback=topic_callback, stop_event=stop_event)


class WAwsS3StorageEventConsumer(WTopicStorageEventConsumer):
    surface = WStorageEventConsumerSurface.AWS_S3

    @classmethod
    def from_config(cls, config: WStorageEventConsumerConfig) -> "WAwsS3StorageEventConsumer":
        if config.surface != WStorageEventConsumerSurface.AWS_S3:
            raise ValueError(f"WAwsS3StorageEventConsumer cannot serve surface [{config.surface}]")
        return cls(WTopicConsumer.from_conf(config.topic_consumer.model_dump(mode="json")))

    @classmethod
    def from_conf(cls, conf) -> "WAwsS3StorageEventConsumer":
        return cls.from_config(WStorageEventConsumerConfig.from_conf(conf))

    def plan(self) -> list[dict[str, Any]]:
        return [
            {
                "surface": self.surface.value,
                "topic_consumer": record,
            }
            for record in self.consumer.plan()
        ]


class WGcpGcsStorageEventConsumer(WTopicStorageEventConsumer):
    surface = WStorageEventConsumerSurface.GCP_GCS

    @classmethod
    def from_config(cls, config: WStorageEventConsumerConfig) -> "WGcpGcsStorageEventConsumer":
        if config.surface != WStorageEventConsumerSurface.GCP_GCS:
            raise ValueError(f"WGcpGcsStorageEventConsumer cannot serve surface [{config.surface}]")
        return cls(WTopicConsumer.from_conf(config.topic_consumer.model_dump(mode="json")))

    @classmethod
    def from_conf(cls, conf) -> "WGcpGcsStorageEventConsumer":
        return cls.from_config(WStorageEventConsumerConfig.from_conf(conf))

    def plan(self) -> list[dict[str, Any]]:
        return [
            {
                "surface": self.surface.value,
                "topic_consumer": record,
            }
            for record in self.consumer.plan()
        ]


WStorageEventListenerSurface = WStorageEventConsumerSurface
WStorageEventListenerConfig = WStorageEventConsumerConfig
WStorageEventListener = WStorageEventConsumer
WTopicStorageEventListener = WTopicStorageEventConsumer
WAwsS3StorageEventListener = WAwsS3StorageEventConsumer
WGcpGcsStorageEventListener = WGcpGcsStorageEventConsumer


def normalize_storage_events(message: dict[str, Any]) -> list[WStorageEvent]:
    """Normalize direct, AWS S3 Records, and AWS EventBridge storage events."""
    if not isinstance(message, dict):
        return []

    direct = _direct_storage_event(message)
    if direct is not None:
        return [direct]

    records = _aws_s3_records_events(message)
    if records:
        return records

    eventbridge = _aws_eventbridge_s3_event(message)
    return [eventbridge] if eventbridge is not None else []


def decode_topic_storage_message(record: dict[str, Any]) -> dict[str, Any]:
    provider = record.get("provider", "")
    if provider == "aws_sns":
        return _decode_aws_sns_record(record)
    if provider == "gcp_pubsub":
        return _decode_gcp_pubsub_record(record)
    if "message" in record and isinstance(record["message"], dict):
        return record["message"]
    return record


def _decode_json_text(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def _decode_aws_sns_record(record: dict[str, Any]) -> dict[str, Any]:
    body = record.get("message", {}).get("Body", "")
    decoded = _decode_json_text(body)
    if isinstance(decoded, dict) and "Message" in decoded:
        message = _decode_json_text(decoded["Message"])
        return message if isinstance(message, dict) else {"message": message}
    return decoded if isinstance(decoded, dict) else {"message": decoded}


def _decode_gcp_pubsub_record(record: dict[str, Any]) -> dict[str, Any]:
    pubsub_message = record.get("message", {}).get("message", {})
    data = pubsub_message.get("data", "")
    if not data:
        return {}
    decoded_text = base64.b64decode(data).decode("utf-8")
    decoded = _decode_json_text(decoded_text)
    message = decoded if isinstance(decoded, dict) else {"message": decoded}
    attributes = pubsub_message.get("attributes", {}) or {}
    if isinstance(attributes, dict):
        if "eventType" in attributes and "event_type" not in message:
            message["event_type"] = attributes["eventType"]
        if "objectId" in attributes and "object_key" not in message and "name" not in message:
            message["object_key"] = attributes["objectId"]
        if "bucketId" in attributes and "bucket" not in message:
            message["bucket"] = attributes["bucketId"]
    if "messageId" in pubsub_message and "event_id" not in message:
        message["event_id"] = pubsub_message["messageId"]
    if "publishTime" in pubsub_message and "event_time" not in message:
        message["event_time"] = pubsub_message["publishTime"]
    return message


def _direct_storage_event(message: dict[str, Any]) -> WStorageEvent | None:
    bucket = str(message.get("bucket", "")).strip()
    raw_object_key = message.get("object_key")
    raw_name = message.get("name")
    object_key = str(raw_object_key or raw_name or "").strip("/")
    if not bucket or not object_key:
        return None
    source_provider = _source_provider(message)
    if source_provider == WStorageSourceProvider.UNKNOWN and raw_object_key is None and raw_name:
        source_provider = WStorageSourceProvider.GCP
    return WStorageEvent(
        event_type=_event_type(message.get("event_type") or message.get("type")),
        bucket=bucket,
        object_key=object_key,
        uri=str(message.get("uri") or _uri(source_provider, bucket, object_key)),
        event_id=str(message.get("event_id") or message.get("id") or ""),
        event_time=str(message.get("event_time") or message.get("time") or ""),
        object_last_modified=str(message.get("object_last_modified") or message.get("updated") or ""),
        etag=str(message.get("etag") or message.get("eTag") or ""),
        version_id=str(message.get("version_id") or message.get("versionId") or ""),
        size=message.get("size"),
        source_provider=source_provider,
        raw_event=message.get("raw_event", message),
    )


def _aws_s3_records_events(message: dict[str, Any]) -> list[WStorageEvent]:
    records = []
    for index, record in enumerate(message.get("Records", []), start=1):
        if record.get("eventSource") != "aws:s3":
            continue
        event_name = str(record.get("eventName", ""))
        event_type = _aws_s3_event_name_type(event_name)
        if event_type is None:
            continue
        bucket = str(record.get("s3", {}).get("bucket", {}).get("name", "")).strip()
        object_info = record.get("s3", {}).get("object", {})
        object_key = unquote_plus(str(object_info.get("key", ""))).strip("/")
        if not bucket or not object_key:
            continue
        records.append(
            WStorageEvent(
                event_type=event_type,
                bucket=bucket,
                object_key=object_key,
                uri=f"s3://{bucket}/{object_key}",
                event_id=str(
                    record.get("responseElements", {}).get("x-amz-request-id")
                    or object_info.get("sequencer")
                    or f"s3-record-{index}"
                ),
                event_time=str(record.get("eventTime") or ""),
                etag=str(object_info.get("eTag") or ""),
                version_id=str(object_info.get("versionId") or ""),
                size=object_info.get("size"),
                source_provider=WStorageSourceProvider.AWS,
                raw_event=record,
            )
        )
    return records


def _aws_eventbridge_s3_event(message: dict[str, Any]) -> WStorageEvent | None:
    if str(message.get("source", "")) != "aws.s3":
        return None
    event_type = _event_type(message.get("detail-type") or message.get("event_type"))
    detail = message.get("detail", {})
    bucket = str(detail.get("bucket", {}).get("name", "")).strip()
    object_info = detail.get("object", {})
    object_key = unquote(str(object_info.get("key", ""))).strip("/")
    if not bucket or not object_key:
        return None
    return WStorageEvent(
        event_type=event_type,
        bucket=bucket,
        object_key=object_key,
        uri=f"s3://{bucket}/{object_key}",
        event_id=str(message.get("id") or ""),
        event_time=str(message.get("time") or ""),
        etag=str(object_info.get("etag") or ""),
        version_id=str(object_info.get("version-id") or ""),
        size=object_info.get("size"),
        source_provider=WStorageSourceProvider.AWS,
        raw_event=message,
    )


def _event_type(value: Any) -> WStorageEventType:
    text = str(value or "").strip().lower()
    if text in {
        WStorageEventType.OBJECT_DELETED.value,
        "object deleted",
        "object delete",
        "objectremoved",
        "objectremoved:delete",
        "object_delete",
        "object_delete_event",
        "google.storage.object.delete",
        "google.cloud.storage.object.v1.deleted",
        "deleted-storage-file",
        "delete",
        "deleted",
    }:
        return WStorageEventType.OBJECT_DELETED
    return WStorageEventType.OBJECT_CREATED


def _aws_s3_event_name_type(value: str) -> WStorageEventType | None:
    if value.startswith("ObjectCreated:"):
        return WStorageEventType.OBJECT_CREATED
    if value.startswith("ObjectRemoved:"):
        return WStorageEventType.OBJECT_DELETED
    return None


def _source_provider(message: dict[str, Any]) -> WStorageSourceProvider:
    source = str(
        message.get("source_provider")
        or message.get("source")
        or message.get("provider")
        or ""
    ).lower()
    if source.startswith("aws") or source == "s3":
        return WStorageSourceProvider.AWS
    if source.startswith("gcp") or source.startswith("google") or source in {"gcs", "gs"}:
        return WStorageSourceProvider.GCP
    if source.startswith("local") or source == "file":
        return WStorageSourceProvider.LOCAL
    return WStorageSourceProvider.UNKNOWN


def _uri(source_provider: WStorageSourceProvider, bucket: str, object_key: str) -> str:
    scheme = "gs" if source_provider == WStorageSourceProvider.GCP else "s3"
    if source_provider == WStorageSourceProvider.LOCAL:
        scheme = "file"
    return f"{scheme}://{bucket}/{object_key}"
