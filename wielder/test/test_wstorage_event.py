import base64
import json
import threading

from wielder.util.wstorage_event import (
    WAwsS3StorageEventConsumer,
    WAwsStorageEventObserver,
    WGcpGcsStorageEventConsumer,
    WGcpStorageEventObserver,
    WStorageEventConsumer,
    WStorageEventObserver,
    WStorageEventType,
    WTopicStorageEventConsumer,
    decode_topic_storage_message,
    normalize_storage_events,
)


def test_normalize_direct_storage_event_defaults_to_created():
    events = normalize_storage_events(
        {
            "bucket": "workspace-cro-mirrors-dev",
            "object_key": "provider/example.xlsx",
            "event_id": "event-1",
            "source": "aws.s3",
        }
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == WStorageEventType.OBJECT_CREATED
    assert event.bucket == "workspace-cro-mirrors-dev"
    assert event.object_key == "provider/example.xlsx"
    assert event.uri == "s3://workspace-cro-mirrors-dev/provider/example.xlsx"


def test_normalize_aws_s3_records_created_and_deleted_events():
    events = normalize_storage_events(
        {
            "Records": [
                {
                    "eventSource": "aws:s3",
                    "eventName": "ObjectCreated:Put",
                    "eventTime": "2026-05-16T10:00:00.000Z",
                    "responseElements": {"x-amz-request-id": "request-create"},
                    "s3": {
                        "bucket": {"name": "bucket-a"},
                        "object": {"key": "provider/foo+bar.xlsx", "eTag": "abc", "size": 12},
                    },
                },
                {
                    "eventSource": "aws:s3",
                    "eventName": "ObjectRemoved:Delete",
                    "s3": {
                        "bucket": {"name": "bucket-a"},
                        "object": {"key": "provider/old.xlsx", "versionId": "v1"},
                    },
                },
            ]
        }
    )

    assert [event.event_type for event in events] == [
        WStorageEventType.OBJECT_CREATED,
        WStorageEventType.OBJECT_DELETED,
    ]
    assert events[0].object_key == "provider/foo bar.xlsx"
    assert events[0].etag == "abc"
    assert events[0].size == 12
    assert events[1].version_id == "v1"


def test_normalize_aws_eventbridge_s3_event():
    events = normalize_storage_events(
        {
            "source": "aws.s3",
            "detail-type": "Object Created",
            "id": "eventbridge-1",
            "time": "2026-05-16T10:00:00Z",
            "detail": {
                "bucket": {"name": "bucket-a"},
                "object": {"key": "provider/raw%20file.xlsx", "etag": "abc"},
            },
        }
    )

    assert len(events) == 1
    assert events[0].event_type == WStorageEventType.OBJECT_CREATED
    assert events[0].object_key == "provider/raw file.xlsx"
    assert events[0].event_id == "eventbridge-1"


def test_decode_topic_storage_message_supports_aws_sns_wrapper():
    inner = {"bucket": "bucket-a", "object_key": "provider/example.xlsx"}
    record = {
        "provider": "aws_sns",
        "message": {
            "Body": json.dumps({"Message": json.dumps(inner)}),
        },
    }

    assert decode_topic_storage_message(record) == inner


def test_decode_topic_storage_message_supports_gcp_pubsub_data():
    inner = {"bucket": "bucket-a", "name": "provider/example.xlsx"}
    data = base64.b64encode(json.dumps(inner).encode("utf-8")).decode("utf-8")
    record = {
        "provider": "gcp_pubsub",
        "message": {
            "message": {
                "data": data,
                "messageId": "message-1",
                "publishTime": "2026-05-18T10:00:00Z",
                "attributes": {
                    "eventType": "OBJECT_FINALIZE",
                    "bucketId": "bucket-a",
                    "objectId": "provider/example.xlsx",
                },
            }
        },
    }

    decoded = decode_topic_storage_message(record)

    assert decoded["bucket"] == "bucket-a"
    assert decoded["name"] == "provider/example.xlsx"
    assert decoded["event_type"] == "OBJECT_FINALIZE"
    assert decoded["event_id"] == "message-1"


class FakeTopicConsumer:
    def __init__(self):
        self.records = [
            {
                "message": {
                    "bucket": "bucket-a",
                    "object_key": "provider/example.xlsx",
                }
            }
        ]

    def plan(self):
        return [{"provider": "fake"}]

    def receive_records_once(self):
        return self.records

    def subscribe(self, callback=None, *, stop_event=None):
        for record in self.records:
            callback(record)
        if stop_event is not None:
            stop_event.set()


def test_topic_storage_event_consumer_wraps_topic_consumer():
    consumer = WTopicStorageEventConsumer(FakeTopicConsumer())

    assert consumer.plan() == [{"provider": "fake"}]
    assert consumer.receive_once()[0].object_key == "provider/example.xlsx"

    received = []
    stop_event = threading.Event()
    consumer.subscribe(received.append, stop_event=stop_event)
    assert received[0].bucket == "bucket-a"
    assert stop_event.is_set()


def test_storage_event_observer_records_events_without_domain_coupling():
    consumer = WTopicStorageEventConsumer(FakeTopicConsumer())
    observer = WStorageEventObserver.from_consumer(consumer)

    observer.start()
    if observer.thread is not None:
        observer.thread.join(timeout=2)

    records = observer.event_records()
    assert records[0]["bucket"] == "bucket-a"
    assert observer.events_for_keys({"provider/example.xlsx"}, event_type=WStorageEventType.OBJECT_CREATED)


def _aws_storage_event_observer_conf():
    flat_conf = _aws_s3_listener_conf()
    return {
        "provider": "aws",
        "storage_event_consumer": {
            "surface": flat_conf.pop("surface"),
            "topic_consumer": flat_conf,
        },
    }


def test_storage_event_observer_factory_returns_aws_observer():
    observer = WStorageEventObserver.from_conf(_aws_storage_event_observer_conf())

    assert isinstance(observer, WAwsStorageEventObserver)
    assert isinstance(observer.consumer, WAwsS3StorageEventConsumer)


def test_storage_event_observer_provider_factory_uses_consumer_conf_directly():
    observer = WStorageEventObserver.from_provider(
        provider="aws",
        storage_event_consumer_conf=_aws_s3_listener_conf(),
    )

    assert isinstance(observer, WAwsStorageEventObserver)
    assert isinstance(observer.consumer, WAwsS3StorageEventConsumer)


def test_storage_event_observer_factory_returns_gcp_observer():
    observer = WStorageEventObserver.from_conf({
        "provider": "gcp",
        "storage_event_consumer": _gcp_gcs_listener_conf(),
    })

    assert isinstance(observer, WGcpStorageEventObserver)
    assert isinstance(observer.consumer, WGcpGcsStorageEventConsumer)


def test_storage_event_observer_provider_factory_uses_gcp_consumer_conf_directly():
    observer = WStorageEventObserver.from_provider(
        provider="gcp",
        storage_event_consumer_conf=_gcp_gcs_listener_conf(),
    )

    assert isinstance(observer, WGcpStorageEventObserver)
    assert isinstance(observer.consumer, WGcpGcsStorageEventConsumer)


def test_storage_event_observer_factory_rejects_unimplemented_providers():
    for provider in ("local",):
        try:
            WStorageEventObserver.from_conf({"provider": provider})
        except NotImplementedError as exc:
            assert "Local storage event observer" in str(exc)
        else:
            raise AssertionError(f"Expected [{provider}] observer to be unimplemented")


def _aws_s3_listener_conf():
    return {
        "surface": "aws_s3",
        "provider": "aws_sns",
        "runtime_surface": "local_aws",
        "topics": {
            "mirror_file": {
                "topic": "workspace-provider-raw-ingestion-dev",
                "role": "mirror_file",
            }
        },
        "aws_region": "us-east-1",
        "aws_account_id": "000000000000",
        "queue_name": "workspace-provider-ingestion-dev-listener-dev",
    }


def _gcp_gcs_listener_conf():
    return {
        "surface": "gcp_gcs",
        "provider": "gcp_pubsub",
        "runtime_surface": "local_gcp",
        "topics": {
            "mirror_file": {
                "topic": "workspace-partner-raw-clone-completed-dev",
                "role": "mirror_file",
            }
        },
        "project_id": "workspace-dev",
        "subscription_prefix": "workspace-partner-gcs-listener",
    }


def test_storage_event_consumer_factory_returns_aws_s3_consumer_from_flat_conf():
    consumer = WStorageEventConsumer.from_conf(_aws_s3_listener_conf())

    assert isinstance(consumer, WAwsS3StorageEventConsumer)
    assert consumer.consumer.config.provider.value == "aws_sns"
    assert consumer.consumer.config.topics["mirror_file"].topic == "workspace-provider-raw-ingestion-dev"


def test_storage_event_consumer_factory_returns_aws_s3_consumer_from_nested_consumer_conf():
    flat_conf = _aws_s3_listener_conf()
    nested_conf = {
        "surface": flat_conf.pop("surface"),
        "topic_consumer": flat_conf,
    }

    consumer = WStorageEventConsumer.from_conf(nested_conf)

    assert isinstance(consumer, WAwsS3StorageEventConsumer)
    assert consumer.plan()[0]["surface"] == "aws_s3"


def test_storage_event_consumer_factory_returns_gcp_gcs_consumer_from_flat_conf():
    consumer = WStorageEventConsumer.from_conf(_gcp_gcs_listener_conf())

    assert isinstance(consumer, WGcpGcsStorageEventConsumer)
    assert consumer.consumer.config.provider.value == "gcp_pubsub"
    assert consumer.consumer.config.topics["mirror_file"].topic == "workspace-partner-raw-clone-completed-dev"
    assert consumer.plan()[0]["surface"] == "gcp_gcs"


def test_aws_s3_consumer_requires_aws_sns_topic_consumer():
    bad_conf = _aws_s3_listener_conf()
    bad_conf["provider"] = "gcp_pubsub"
    bad_conf["runtime_surface"] = "local_gcp"
    bad_conf["project_id"] = "project-a"
    bad_conf["subscription_prefix"] = "sub"
    bad_conf.pop("aws_region")
    bad_conf.pop("aws_account_id")
    bad_conf.pop("queue_name")

    try:
        WStorageEventConsumer.from_conf(bad_conf)
    except ValueError as exc:
        assert "aws_s3 storage event consumer requires an aws_sns topic_consumer" in str(exc)
    else:
        raise AssertionError("Expected aws_s3 consumer/provider contract failure")


def test_gcp_gcs_consumer_requires_gcp_pubsub_topic_consumer():
    bad_conf = _gcp_gcs_listener_conf()
    bad_conf["provider"] = "aws_sns"
    bad_conf["runtime_surface"] = "local_aws"
    bad_conf["aws_region"] = "us-east-1"
    bad_conf["aws_account_id"] = "000000000000"
    bad_conf["queue_name"] = "queue-a"
    bad_conf.pop("project_id")
    bad_conf.pop("subscription_prefix")

    try:
        WStorageEventConsumer.from_conf(bad_conf)
    except ValueError as exc:
        assert "gcp_gcs storage event consumer requires a gcp_pubsub topic_consumer" in str(exc)
    else:
        raise AssertionError("Expected gcp_gcs consumer/provider contract failure")
