#!/usr/bin/env python
import logging
import os
from enum import Enum

from wielder.util.arguer import get_wielder_parser


class AdminAction(Enum):

    LIST = 'list'
    DELETE = 'del'
    CREATE = 'create'


class ConsumerAction(Enum):

    CONSUME = 'consume'
    CONSUME_LAST = 'last'
    LIST = 'list'
    ONE_MSG_BATCH = 'one'


def get_kafka_parser():

    wield_parser = get_wielder_parser()

    wield_parser.add_argument(
        '-aa', '--admin_action',
        type=AdminAction,
        choices=list(AdminAction),
        help='Admin actions:\n'
             ' create : default lists topics in config: \n'
             ' list   : lists topics partitions\n'
             ' del    : deletes topics in deletion list in config\n',
        default=AdminAction.LIST
    )

    wield_parser.add_argument(
        '-a', '--consume_action',
        type=ConsumerAction,
        choices=list(ConsumerAction),
        help='Consumer actions:\n'
             ' consume: default to latest multiple topics from config: \n'
             ' list   : lists topic partitions\n'
             ' last   : fetches the last message in the topic\n'
             ' one    : Consumes one message at a time.\n'
             '          Commits after doing a task and callback\n'
             '          ClI use with --group_id or short -id\n',
        default=ConsumerAction.CONSUME
    )

    wield_parser.add_argument(
        '-id', '--group_id',
        type=str,
        help='Kafka group id for consumer.',
        default=None
    )

    wield_parser.add_argument(
        '-t', '--topic',
        type=str,
        help='Kafka topic to override config subscriptions.',
        default=None
    )

    return wield_parser


def default_project_root():

    dir_path = os.path.dirname(os.path.realpath(__file__))
    logging.info(f"current working dir: {dir_path}")

    project_root = dir_path.replace('/datastore_admin', '')
    return project_root




