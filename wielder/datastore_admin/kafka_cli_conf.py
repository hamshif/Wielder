#!/usr/bin/env python
import argparse
import os
from enum import Enum

from wielder.util.hocon_util import get_conf_ordered_files

import logging


class AdminAction(Enum):

    LIST = 'list'
    DELETE = 'del'
    CREATE = 'create'


class ConsumerAction(Enum):

    CONSUME = 'consume'
    CONSUME_LAST = 'last'
    LIST = 'list'
    ONE_MSG_BATCH = 'one'


def get_parser():

    parser = argparse.ArgumentParser(
        description='A wrapper for kafka consumer\n'
                    'CLI trumps config file\n'
                    'Used in tandem with Kafka.conf Hocon config file.\n'
    )

    parser.add_argument(
        '-re', '--runtime_env',
        type=str,
        help='Kafka topic to override config subscriptions.',
        default='kube_docker'
    )

    parser.add_argument(
        '-aa', '--admin_action',
        type=AdminAction,
        choices=list(AdminAction),
        help='Admin actions:\n'
             ' create : default lists topics in config: \n'
             ' list   : lists topics partitions\n'
             ' del    : deletes topics in deletion list in config\n',
        default=AdminAction.LIST
    )

    parser.add_argument(
        '-a', '--action',
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

    parser.add_argument(
        '-id', '--group_id',
        type=str,
        help='Kafka group id for consumer.',
        default=None
    )

    parser.add_argument(
        '-t', '--topic',
        type=str,
        help='Kafka topic to override config subscriptions.',
        default=None
    )

    return parser


def default_project_root():

    dir_path = os.path.dirname(os.path.realpath(__file__))
    logging.info(f"current working dir: {dir_path}")

    project_root = dir_path.replace('/datastore_admin', '')
    return project_root


def get_kafka_conf(project_root=None):
    """
    To view CLI options call this module with -h

    :param project_root: full path to where the project root lies
        i.e. a config dir with environment specific folders. If None goes to default example config.
    :type project_root: str
    :return: A hocon config tree overridden by CLI
    :rtype: hocon config tree
    """

    p = get_parser()
    ar = p.parse_args()

    if project_root is None:
        project_root = default_project_root()

    conf_root = f'{project_root}/conf/kafka'

    main_conf_path = f"{conf_root}/kafka.conf"
    env_conf_path = f"{conf_root}/{ar.runtime_env}/kafka.conf"
    dev_override_path = f"{conf_root}/dev.conf"

    ordered_conf_files = [
        main_conf_path,
        env_conf_path,
        dev_override_path
    ]

    conf = get_conf_ordered_files(ordered_conf_files)

    conf.project_root = project_root
    conf.action = ar.action
    conf.admin_action = ar.admin_action

    if ar.group_id is not None:
        conf.group_id = ar.group_id

    conf.topic = ar.topic

    return conf


if __name__ == "__main__":

    _conf = get_kafka_conf()
    print(_conf)



