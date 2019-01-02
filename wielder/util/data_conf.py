#!/usr/bin/env python
import os

__author__ = 'Gideon Bar'

import argparse

import yaml

from collections import namedtuple


class Conf:

    def __init__(self):

        self.template_ignore_dirs = []

    def attr_list(self, should_print=False):

        items = self.__dict__.items()
        if should_print:

            print("Conf items:\n______\n")
            [print(f"attribute: {k}    value: {v}") for k, v in items]

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
        '-de', '--deploy_env',
        type=str,
        choices=['local', 'dev', 'int', 'qa', 'stage', 'prod'],
        help='Deployment environment local means dev refers to git branches ...'
    )

    parser.add_argument(
        '-cpr', '--cloud_provider',
        type=str,
        choices=['gcp', 'aws', 'azure'],
        help='Cloud provider will only mean something if not local:'
    )

    parser.add_argument(
        '-gp', '--gcp_project',
        type=str,
        choices=['marketo-webpersonalization-dev', 'rtp-gcp-poc'],
        help='GCP project for GKE means:\n'
             'Which project to use for deploy and resources.'
    )

    parser.add_argument(
        '-edb', '--enable_debug',
        type=bool,
        help='Enabling Debug ports for remote debugging:'
    )

    parser.add_argument(
        '-edv', '--enable_dev',
        type=bool,
        help='Enabling Development on pods e.g. mot running the java process on cep:'
    )

    return parser


def process_args(cmd_args):

    if cmd_args.conf_file is None:

        dir_path = os.path.dirname(os.path.realpath(__file__))

        cmd_args.conf_file = dir_path + '/data_conf.yaml'

    with open(cmd_args.conf_file, 'r') as yaml_file:
        conf_args = yaml.load(yaml_file)

    if not hasattr(conf_args, 'plan'):
        conf_args['plan'] = False

    print('Configuration File Arguments:')

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

    conf.gcp_project = named_tuple.gcp['project']
    conf.gcp_image_repo_zone = named_tuple.gcp['image_repo_zone']
    conf.is_shared_vpc = named_tuple.gcp['is_shared_vpc']
    conf.region = named_tuple.gcp['region']
    conf.zone = named_tuple.gcp['zone']
    conf.image_repo_zone = named_tuple.gcp['image_repo_zone']
    conf.service_accounts = named_tuple.gcp['service_accounts']
    conf.network = named_tuple.gcp['network']
    conf.subnetwork = named_tuple.gcp['subnetwork']

    conf.raw_config_args = conf_args

    conf.attr_list(True)

    return conf


if __name__ == "__main__":

    datalake_parser = get_datalake_parser()
    datalake_args = datalake_parser.parse_args()

    _conf = process_args(datalake_args)

    print('brake point')




