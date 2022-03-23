#!/usr/bin/env python
import json
import traceback

from confluent_kafka import Producer
import socket


def json_file_to_topic(conf, full_path, key, topic):

    print("Gremlin")

    with open(full_path) as json_file:

        print(f"full: {full_path}")

        data = json.load(json_file)

        j = json.dumps(data)

        print(type(j))

        message = (key, j)

        produce_messages(conf, [message], [topic], False)


def producer_callback(err, msg):

    if err is not None:
        print(f"Failed to deliver message: {str(msg)}, {str(err)}")
    else:
        print(f"Message produced: {str(msg)}")


def produce_conf(conf, listen=False):

    topics = [t for t in conf.topics]

    [print(f'KAFKA_BROKERS: {conf.KAFKA_BROKERS}\n Topic {t}') for t in topics]

    messages = conf.demo_messages

    produce_messages(conf, messages, topics, listen)


def produce_debug(conf):

    topic = conf.topic if conf.topic is not None else 'docking_experiments'

    debug = conf['topics'][topic]['debug']

    bot_ids = [t for t in debug.ids]

    for bot_id in bot_ids:

        print(f'bot_id {bot_id}')
        full_path = f'{conf.project_root}/{debug.input_dir}/{debug.input_name_prefix}{bot_id}.json'

        try:
            with open(full_path) as json_file:
                print(f"full: {full_path}")

                data = json.load(json_file)

                j = json.dumps(data)

                print(type(j))

                message = [bot_id, j]

                produce_messages(conf, [message], [topic], False)
        except Exception as e:

            print(e)


def produce_messages(conf, messages, topics, listen=False):
    encoded = []

    for m in messages:

        encoded.append((str(m[0]).encode('utf-8'), str(m[1]).encode('utf-8')))

    conf = {
        'bootstrap.servers': f"{conf.KAFKA_BROKERS}",
        'client.id': socket.gethostname(),
        'message.max.bytes': 15048576,
    }

    producer = Producer(conf)

    for t in topics:

        for m in encoded:

            print(f"sending: {m} to topic: {t}")

            if listen:
                producer.produce(topic=t, key=m[0], value=m[1])

            else:
                producer.produce(topic=t, key=m[0], value=m[1], callback=producer_callback)

            producer.flush()




