#!/usr/bin/env python
"""
Author: Gideon Bar
"""
import json
import os
import argparse
import traceback
from enum import Enum

from time import sleep

import logging
from cassandra import ConsistencyLevel, ReadTimeout
from cassandra.cluster import Cluster, BatchStatement
from cassandra.auth import PlainTextAuthProvider
# from cassandra.policies import RoundRobinPolicy
from cassandra.query import SimpleStatement
from pyhocon import ConfigFactory

import rx
from rx import operators as ops
import concurrent.futures

from wielder.util.hocon_util import get_conf_ordered_files


class WieldTable:

    def __init__(
            self, project_conf, keyspace, table_name,
            with_logger=True, with_session=True
    ):

        conf = project_conf.cassandra
        meta = conf.keyspaces_meta[keyspace]
        table_conf = conf.keyspaces[keyspace][table_name]

        self.host = conf.host
        self.port = conf.port
        self.user = conf.user
        self.password = conf.password
        self.keyspace = keyspace
        self.replication_class = meta.replication_class
        self.replication_factor = str(meta.replication_factor)
        self.table_name = table_name
        self.consistency_level = conf.consistency_level

        self.table_conf = table_conf
        self.batch_size = table_conf.batch_size
        self.cql_create = table_conf.cql_create
        self.table_fields = table_conf.table_fields
        self.cql_upsert = table_conf.cql_upsert.replace('table_fields', self.table_fields)
        self.cql_delete_by_primary_key = table_conf.cql_delete_by_primary_key

        self.batch = None
        self.prepared_upsert_cql_cmd = None
        self.upsert_count = 0

        self.credentials = PlainTextAuthProvider(
            username=self.user,
            password=self.password
        )

        consistency_level = ConsistencyLevel.QUORUM

        if conf.consistency_level == 'ONE':
            consistency_level = ConsistencyLevel.ONE
        elif conf.consistency_level == 'ALL':
            consistency_level = ConsistencyLevel.ALL
        elif conf.consistency_level == 'TWO':
            consistency_level = ConsistencyLevel.TWO
        elif conf.consistency_level == 'ANY':
            consistency_level = ConsistencyLevel.ANY
        elif conf.consistency_level == 'EACH_QUORUM':
            consistency_level = ConsistencyLevel.EACH_QUORUM
        elif conf.consistency_level == 'LOCAL_ONE':
            consistency_level = ConsistencyLevel.LOCAL_ONE
        elif conf.consistency_level == 'LOCAL_QUORUM':
            consistency_level = ConsistencyLevel.LOCAL_QUORUM
        elif conf.consistency_level == 'LOCAL_SERIAL':
            consistency_level = ConsistencyLevel.LOCAL_SERIAL
        elif conf.consistency_level == 'SERIAL':
            consistency_level = ConsistencyLevel.SERIAL
        elif conf.consistency_level == 'THREE':
            consistency_level = ConsistencyLevel.THREE

        self.consistency_level = consistency_level

        if with_logger:
            self.set_logger()
        else:
            self.log = None

        if with_session:
            self.create_session()
        else:
            self.cluster = None
            self.session = None

    def __del__(self):
        self.cluster.shutdown()

    def get_cluster(self):

        node_ips = [self.host]

        cluster = Cluster(
            node_ips,
            auth_provider=self.credentials,
            protocol_version=4,
            port=self.port,
            # load_balancing_policy=RoundRobinPolicy(),
        )

        return cluster

    def create_session(self):

        logging.debug('moose')
        logging.info(f'credentials:\n{self.credentials}')
        print(f'credentials:\n{self.credentials}')

        self.cluster = self.get_cluster()
        self.session = self.cluster.connect()

        keyspace_cmd = f"""
                CREATE KEYSPACE IF NOT EXISTS {self.keyspace}
                WITH replication = {{ 'class': '{self.replication_class}', 'replication_factor': '{self.replication_factor}' }} 
                """

        logging.info(f'Running :\n{keyspace_cmd}')
        # self.log.info(f"creating keyspace: {self.keyspace}")
        self.session.execute(keyspace_cmd)

        # self.log.info(f"keyspace: {self.keyspace} verified")
        self.session.set_keyspace(self.keyspace)

    def get_session(self):
        return self.session

    # How about Adding some log info to see what went wrong
    def set_logger(self):
        log = logging.getLogger()
        log.setLevel('INFO')
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        log.addHandler(handler)
        self.log = log

    def list_keyspaces(self):

        rows = self.session.execute(f"SELECT keyspace_name FROM system_schema.keyspaces")

        [print(row) for row in rows]

    def select_data(self, limit=50, pr=False):
        rows = self.session.execute(f'select * from {self.table_name} limit {limit};')

        if pr:
            [print(row) for row in rows]

        return rows

    def select_all(self, pr=False, where_args=None):

        if where_args is None:
            where_clause = ''
        else:
            where_clause = f' where {where_args}'

        rows = self.session.execute(f'select * from {self.table_name}{where_clause};')

        if pr:
            [print(row) for row in rows]

        return rows

    def del_keyspace(self, keyspace=None):

        if keyspace is None:
            keyspace = self.keyspace

        if self.cluster is not None:
            self.cluster.shutdown()
        self.cluster = self.get_cluster()
        self.session = self.cluster.connect()

        rows = self.session.execute(f"SELECT keyspace_name FROM system_schema.keyspaces", timeout=20)
        if keyspace in [row[0] for row in rows]:
            self.log.info(f"dropping existing keyspace: {keyspace}")
            self.session.execute(f"DROP KEYSPACE {keyspace}")
        else:
            self.log.info(f"could'nt find keyspace: {keyspace}")

    def describe_keyspace(self, keyspace=None):

        if keyspace is None:
            keyspace = self.keyspace

        self.cluster = self.get_cluster()
        self.session = self.cluster.connect()

        cmd = f"DESCRIBE KEYSPACE {keyspace};"

        print(cmd)

        description = self.session.execute(cmd)

        for r in description.current_rows:
            print(r)

    def list_tables(self, keyspace=None):

        if keyspace is None:
            keyspace = self.keyspace

        self.cluster = self.get_cluster()
        self.session = self.cluster.connect()

        tables = self.cluster.metadata.keyspaces[keyspace]

        print(f"meta data:\n{tables.__dict__}")

        table_names = []

        for table in tables.__dict__['tables']:
            print(table)

            table_names.append(table)

            column = tables.__dict__['tables'][table].__dict__['columns'].items()

            [print(f'column: {i}   {i[1]}') for i in column]

        return table_names

    def del_table(self):

        future = self.session.execute_async(f"DROP TABLE IF EXISTS {self.table_name};")
        future.add_callbacks(handle_success, handle_error)

    def create_table(self):

        self.log.info(f"Creating table {self.table_name} with this statement:\n{self.cql_create}")
        self.session.execute(self.cql_create)
        self.log.info(f"{self.table_name} Table verified !!!")

    def maybe_upsert_batch(self, upsert):

        # print(f"klook  {upsert}")
        self.batch.add(self.prepared_upsert_cql_cmd, upsert)
        self.upsert_count += 1

        if self.upsert_count > self.batch_size:
            print(f"upsert count:  {self.upsert_count}")
            self.upsert_count = 0
            self.session.execute(self.batch)
            self.batch.clear()
            self.log.info(f'Intermediate Batch Insert Completed {self.table_name}')


def handle_success(answer):
    print(f"type: {type(answer)}")
    try:

        for k, v in answer.items():
            print(f"res key: {k}, res value: {v}")

    except ReadTimeout as E:
        print(f"Query timed out: {E}")


def handle_error(exception):
    print(exception)


def list_tables(conf, keyspace, table_name):
    table = WieldTable(project_conf=conf, keyspace=keyspace, table_name=table_name)

    tables = table.list_tables()

    return tables


def reset(conf, table_name, keyspace='grids'):

    table = WieldTable(
        project_conf=conf,
        keyspace=keyspace,
        table_name=table_name
    )

    table.list_keyspaces()

    table.del_keyspace()
    table.list_keyspaces()

    table = WieldTable(
        project_conf=conf,
        keyspace=keyspace,
        table_name=table_name,
    )

    table.list_keyspaces()


def del_table(conf, keyspace, table_name):

    print(f'Going to delete table {keyspace}.{table_name}')
    table = WieldTable(
        project_conf=conf,
        keyspace=keyspace,
        table_name=table_name,
    )

    table.del_table()


def get_parser():
    parser = argparse.ArgumentParser(
        description='A wrapper for Cassandra consumer\n'
                    'CLI trumps config file\n'
                    'Used in tandem with Kafka.conf Hocon config file.\n'
    )

    parser.add_argument(
        '-re', '--runtime_env',
        type=str,
        help='Kafka topic to override config subscriptions.',
        default='local'
    )

    return parser


def reset_all_keyspaces(conf):

    for keyspace in conf.cassandra.keyspaces.keys():

        print(f'Resetting keyspace: {keyspace}')
        reset(conf=conf, keyspace=keyspace, table_name='table_name')


def clear_keyspace(conf, keyspace):
    list_tables(conf=conf, keyspace=keyspace, table_name="woo")

