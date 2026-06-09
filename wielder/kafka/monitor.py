#!/usr/bin/env python

from confluent_kafka import Consumer, KafkaException
import sys
import json
import logging
from pprint import pformat


def stats_cb(stats_json_str):
    stats_json = json.loads(stats_json_str)
    print('\nKAFKA Stats: {}\n'.format(pformat(stats_json)))


def print_usage_and_exit(program_name):
    sys.stderr.write('Usage: %s [options..] <bootstrap-brokers> <group> <topic1> <topic2> ..\n' % program_name)
    options = '''
 Options:
  -T <intvl>   Enable client statistics at specified interval (ms)
'''
    sys.stderr.write(options)
    sys.exit(1)


def monitor_topics(conf):

    kafka_conf = conf.kafka

    brokers = kafka_conf.brokers

    if conf.topic is None:
        topics = kafka_conf.topics_for_listening
        topic = 'monitor'
    else:
        topic = conf.topic
        topics = [topic]

    if conf.group_id is None:
        group = kafka_conf.consumer_groups[topic].id
    else:
        group = conf.group_id

    [print(f'listening to topic {t}') for t in topics]

    optlist = []

    conf = {
        'bootstrap.servers': brokers,
        'group.id': group,
        'session.timeout.ms': 1800000,
        'max.poll.interval.ms': 1800000,
        'auto.offset.reset': 'earliest'
    }

    print(f"kafka conf:\n{conf}")

    # Check to see if -T option exists
    for opt in optlist:
        if opt[0] != '-T':
            continue
        try:
            intval = int(opt[1])
        except ValueError:
            sys.stderr.write("Invalid option value for -T: %s\n" % opt[1])
            sys.exit(1)

        if intval <= 0:
            sys.stderr.write("-T option value needs to be larger than zero: %s\n" % opt[1])
            sys.exit(1)

        conf['stats_cb'] = stats_cb
        conf['statistics.interval.ms'] = int(opt[1])

    # Create logger for consumer (logs will be emitted when poll() is called)
    logger = logging.getLogger('consumer')
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)-15s %(levelname)-8s %(message)s'))
    logger.addHandler(handler)

    # Create Consumer instance
    # Hint: try debug='fetch' to generate some log messages
    c = Consumer(conf, logger=logger)

    def print_assignment(consumer, partitions):
        print('Assignment:', partitions)

    # Subscribe to topics
    c.subscribe(topics, on_assign=print_assignment)

    # Read messages from Kafka, print to stdout
    try:
        while True:
            msg = c.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                raise KafkaException(msg.error())

            key = msg.key().decode("utf-8")
            value = msg.value().decode("utf-8")

            t = msg.topic()

            if kafka_conf.topics[t].verbose:

                sys.stderr.write(f'topic: {t}, partition: {msg.offset()}, '
                                 f'offset {msg.partition()},key {key}\n')
                                    # f'offset {msg.partition()},key {key} value {value}\n')
                try:
                    j_value = json.loads(value)
                    log = json.dumps(j_value, indent=4, sort_keys=True)
                    s = f'{log}\n'

                    sys.stdout.write(s)
                except ValueError:
                    sys.stderr.write(value)

            else:
                # Proper message
                sys.stderr.write(f'topic: {t}, partition: {msg.offset()}, '
                                 f'offset {msg.partition()},key {key}\n')
                                # f'offset {msg.partition()},key {key} value {value}\n')

                # print(f'message value type: {type(msg)}')
                # pr = str(msg.value())
                #
                # if len(pr) > 20:
                #     pr = pr[:20]
                #
                # print(pr)

    except KeyboardInterrupt:
        sys.stderr.write('%% Aborted by user\n')

    finally:
        # Close down consumer to commit final offsets.
        c.close()


