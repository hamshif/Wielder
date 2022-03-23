#!/usr/bin/env python
from time import sleep
import pprint

from confluent_kafka.admin import AdminClient, NewTopic

import traceback
from confluent_kafka.cimpl import KafkaError
from wielder.datastore_admin.kafka_cli_conf import AdminAction


class WrapKafkaAdmin:

    def __init__(self, conf):

        self.conf = conf

        print(f'Shmulik: {conf.KAFKA_BROKERS}')

        kafka_conf = {'bootstrap.servers': conf.KAFKA_BROKERS}
        kafka_admin = AdminClient(kafka_conf)
        self.admin = kafka_admin

    def list_topics(self):

        pprint.pprint(self.admin.list_topics().topics)  # LIST

    def create_topics(self, listen=False):

        topic_list = []

        for topic_name, topic in self.conf.topics.items():

            print(f'Topic config: {topic}')

            topic_config = {}

            for k, v in topic.config.items():

                k = k.replace('_', '.')
                topic_config[k] = v

            num_partitions = topic.num_partitions + topic.other_channels

            print(topic)
            topic_list.append(NewTopic(
                topic=topic_name,
                num_partitions=num_partitions,
                replication_factor=topic.replication_factor,
                config=topic_config
                )
            )

        # new_topic = kad.NewTopic('topic100', 3, 2)
        # Number-of-partitions  = 1
        # Number-of-replicas    = 1

        futures = self.admin.create_topics(topic_list)  # CREATE (a list(), so you can create multiple).

        if listen:
            try:
                record_metadata = []
                for k, future in futures.items():
                    # f = i.get(timeout=10)
                    print(f"type(k): {type(k)}")
                    print(f"type(v): {type(future)}")
                    print(future.result())

            except KafkaError:
                # Decide what to do if produce request failed...
                print(traceback.format_exc())
                result = 'Fail'
            finally:
                print("finally")

        else:
            sleep(3)

        self.list_topics()

    def delete_topics(self):

        topics_for_deletion = [a for a in self.conf.topics_for_deletion]

        future_dict = self.admin.delete_topics(topics_for_deletion)

        print('delete futures:')
        for k, v in future_dict.items():

            print(f'future key: {k}     value: {v}')

        sleep(5)

        self.list_topics()

    def explore(self):

        self.admin.describe_configs()


def kafka_admin_action(conf):

    action = conf.admin_action

    print(f"admin_action: {action}")

    kafka_wrapper = WrapKafkaAdmin(conf)

    if action is AdminAction.DELETE:

        kafka_wrapper.delete_topics()

    elif action is AdminAction.LIST:

        kafka_wrapper.list_topics()

    elif action is AdminAction.CREATE:
        kafka_wrapper.create_topics()
    else:
        print(f"No such action {action}")