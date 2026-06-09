from wielder.util.wtopic import WTopicConsumer, WTopicEventEnvelope, WTopicMessage


def test_topic_event_envelope_serializes_source_provenance():
    envelope = WTopicEventEnvelope.build(
        schema_version="example.event.v1",
        event_type="example.completed",
        status="done",
        source_event={
            "bucket": "example-bucket",
            "object_key": "raw/example.txt",
            "source": "aws.s3",
            "raw_mirror_run_id": "run-1",
            "provenance": {
                "raw_mirror_run_id": "run-1",
                "entrypoint": "raw_mirror_workflow_run",
            },
        },
        payload={"records": 3},
    )

    message = envelope.to_message(projected_provenance_keys=("raw_mirror_run_id",))

    assert message["schema_version"] == "example.event.v1"
    assert message["raw_mirror_run_id"] == "run-1"
    assert message["source_event"]["uri"] == "s3://example-bucket/raw/example.txt"
    assert message["source_event"]["provenance"]["entrypoint"] == "raw_mirror_workflow_run"
    assert message["payload"] == {"records": 3}


def test_topic_message_from_envelope_includes_transport_attributes():
    envelope = WTopicEventEnvelope.build(
        schema_version="example.event.v1",
        event_type="example.completed",
        status="done",
        source_event={"bucket": "bucket", "object_key": "key"},
    )

    message = WTopicMessage.from_envelope(
        topic="example-topic",
        key="example",
        envelope=envelope,
        attributes={"domain": "example"},
    )

    assert message.topic == "example-topic"
    assert message.key == "example"
    assert message.attributes["schema_version"] == "example.event.v1"
    assert message.attributes["event_type"] == "example.completed"
    assert message.attributes["status"] == "done"
    assert message.attributes["domain"] == "example"


def test_topic_event_envelope_parses_projected_message():
    envelope = WTopicEventEnvelope.build(
        schema_version="example.event.v1",
        event_type="example.completed",
        status="done",
        source_event={
            "bucket": "example-bucket",
            "object_key": "raw/example.txt",
            "raw_mirror_run_id": "run-1",
            "provenance": {"raw_mirror_run_id": "run-1"},
        },
        payload={"records": 3},
    )
    message = envelope.to_message(projected_provenance_keys=("raw_mirror_run_id",))

    parsed = WTopicEventEnvelope.from_message(message)

    assert parsed.schema_version == "example.event.v1"
    assert parsed.event_type == "example.completed"
    assert parsed.payload == {"records": 3}
    assert parsed.provenance["raw_mirror_run_id"] == "run-1"


def test_aws_sns_consumer_clear_records_purges_configured_queue(monkeypatch):
    commands = []

    class Completed:
        returncode = 0
        stdout = '{"QueueUrl": "https://sqs.us-east-1.amazonaws.com/123/raw-mirror"}'
        stderr = ""

    class Purged:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        commands.append(command)
        if "get-queue-url" in command:
            return Completed()
        return Purged()

    monkeypatch.setattr("subprocess.run", fake_run)
    consumer = WTopicConsumer.from_conf(
        {
            "provider": "aws_sns",
            "runtime_surface": "local_aws",
            "aws_region": "us-east-1",
            "aws_account_id": "123",
            "queue_name": "raw-mirror",
            "topics": {"example": {"topic": "topic", "role": "emission"}},
        }
    )

    records = consumer.clear_records()

    assert records[0]["status"] == "cleared"
    assert commands[-1][:3] == ["aws", "sqs", "purge-queue"]
    assert "https://sqs.us-east-1.amazonaws.com/123/raw-mirror" in commands[-1]


def test_gcp_pubsub_consumer_clear_records_seeks_subscriptions(monkeypatch):
    commands = []

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        commands.append(command)
        return Completed()

    monkeypatch.setattr("subprocess.run", fake_run)
    consumer = WTopicConsumer.from_conf(
        {
            "provider": "gcp_pubsub",
            "runtime_surface": "local_gcp",
            "project_id": "example-dev",
            "subscription_prefix": "raw-mirror",
            "topics": {"example": {"topic": "topic", "role": "emission"}},
        }
    )

    records = consumer.clear_records()

    assert records[0]["subscription"] == "raw-mirror-example"
    assert commands[0][:4] == ["gcloud", "pubsub", "subscriptions", "describe"]
    assert commands[1][:4] == ["gcloud", "pubsub", "subscriptions", "seek"]
    assert "--project=example-dev" in commands[1]
