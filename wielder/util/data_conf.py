#!/usr/bin/env python

__author__ = 'Gideon Bar'

import os
import argparse
import yaml
from collections import namedtuple
import logging

from wielder.util.arguer import LogLevel, convert_log_level
from wielder.util.log_util import setup_logging


class Conf:

    def __init__(self):

        self.template_ignore_dirs = []

    def attr_list(self, should_print=False):

        items = self.__dict__.items()
        if should_print:

            logging.debug("Conf items:\n______\n")
            [logging.debug(f"attribute: {k}    value: {v}") for k, v in items]

        return items


def get_datalake_parser():

    parser = argparse.ArgumentParser(description=
                                     'Data Orchestration Reactive Framework.')

    parser.add_argument(
        '-cf', '--conf_file',
        type=str,
        help='Full path to config file with all arguments.\nCommandline args override those in the file.'
    )

    parser.add_argument(
        '-pl', '--plan',
        type=bool,
        default=False,
        help='plan means to create template instances/files but not deploy them e.g. conf.yml.tmpl => conf.yml.'
    )

    parser.add_argument(
        '-e', '--env',
        type=str,
        default='qe',
        help='Deployment environment local means dev refers to git branches ...'
    )

    parser.add_argument(
        '-re', '--runtime_env',
        type=str,
        default='local-docker',
        help='Runtime environment eg local-docker, local, gcp, gcp-shared-vpc etc...'
    )

    parser.add_argument(
        '-cpr', '--cloud_provider',
        type=str,
        choices=['gcp', 'aws', 'azure'],
        help='Cloud provider will only mean something if not local:'
    )

    parser.add_argument(
        '-edb', '--enable_debug',
        type=bool,
        help='Enabling Debug ports for remote debugging:'
    )

    parser.add_argument(
        '-ll', '--log_level',
        type=LogLevel,
        choices=list(LogLevel),
        help='LogLevel: as in Python logging',
        default=LogLevel.INFO
    )

    return parser


def extract_gcp_to_conf(conf):

    raw = conf.raw_config_args['gcp']

    gcp = Conf()

    gcp.gcp_project = raw['project']
    gcp.gcp_image_repo_zone = raw['image_repo_zone']
    gcp.is_shared_vpc = raw['is_shared_vpc']
    gcp.region = raw['region']
    gcp.zone = raw['zone']
    gcp.image_repo_zone = raw['image_repo_zone']
    gcp.service_accounts = raw['service_accounts']
    gcp.network = raw['network']
    gcp.subnetwork = raw['subnetwork']

    conf.gcp = gcp

    gcp_services = raw['services']

    if 'dataproc' in gcp_services:

        raw_dataproc = gcp_services['dataproc']
        dataproc = Conf()
        dataproc.high_availability = raw_dataproc['high_availability']
        dataproc.extra_tags = raw_dataproc['extra_tags']
        dataproc.region = raw_dataproc['region']
        dataproc.zone = raw_dataproc['zone']
        dataproc.internal_ip_only = raw_dataproc['internal_ip_only']
        dataproc.master_machine_type = raw_dataproc['master_machine_type']
        dataproc.worker_machine_type = raw_dataproc['worker_machine_type']
        dataproc.master_boot_disk_size = raw_dataproc['master_boot_disk_size']
        dataproc.worker_boot_disk_size = raw_dataproc['worker_boot_disk_size']
        dataproc.num_worker_nodes = raw_dataproc['num_worker_nodes']

        conf.gcp.dataproc = dataproc
        

def process_args(cmd_args):

    if cmd_args.conf_file is None:

        dir_path = os.path.dirname(os.path.realpath(__file__))

        cmd_args.conf_file = dir_path + '/data_conf.yaml'

    log_level = convert_log_level(cmd_args.log_level)

    logging.basicConfig(
        format='%(asctime)s %(levelname)s :%(message)s',
        level=log_level,
        datefmt='%m/%d/%Y %I:%M:%S %p'
    )

    with open(cmd_args.conf_file, 'r') as yaml_file:
        conf_args = yaml.load(yaml_file, Loader=yaml.FullLoader)

    if not hasattr(conf_args, 'plan'):
        conf_args['plan'] = False

    logging.debug('Configuration File Arguments:')

    config_items = cmd_args.__dict__.items()

    for k, v in config_items:

        if v is not None:
            conf_args[k] = v

    named_tuple = namedtuple("Conf1", conf_args.keys())(*conf_args.values())

    conf = Conf()

    conf.plan = named_tuple.plan
    conf.conf_file = named_tuple.conf_file
    conf.deploy_env = named_tuple.deploy_env
    conf.enable_debug = named_tuple.enable_debug
    conf.enable_dev = named_tuple.enable_dev
    conf.deploy_strategy = named_tuple.deploy_strategy
    conf.supported_deploy_envs = named_tuple.supported_deploy_envs
    conf.cloud_provider = named_tuple.cloud_provider
    conf.template_ignore_dirs = named_tuple.template_ignore_dirs
    conf.template_variables = named_tuple.template_variables
    conf.script_variables = named_tuple.script_variables

    conf.git_super_repo = named_tuple.git_super_repo
    conf.git_branch = named_tuple.git_branch
    conf.git_commit = named_tuple.git_commit

    conf.raw_config_args = conf_args

    if conf.cloud_provider == 'gcp':

        extract_gcp_to_conf(conf)

    conf.attr_list(True)

    return conf


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    datalake_args, other_args = get_datalake_parser().parse_known_args()

    _conf = process_args(datalake_args)

    logging.debug('break point')

    logging.info(f"datalake_args:\n{datalake_args}\n")
    logging.info(f"other_args:\n{other_args}")





