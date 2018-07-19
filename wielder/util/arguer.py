#!/usr/bin/env python
import os

__author__ = 'Gideon Bar'

import argparse

import yaml

from collections import namedtuple

from wielder.util.commander import async_cmd


class Conf:

    def attr_list(self, should_print=False):

        items = self.__dict__.items()
        if should_print:
            [print(f"attribute: {k}    value: {v}") for k, v in items]

        return items


def destroy_sanity(conf):

    if conf.deploy_env is 'prod':

        print('You are trying to destroy a production environment!!!'
              'Exiting!!!')

        exit(1)

    # TODO enable this
    # elif conf.deploy_env is not 'local' or conf.kube_context is not "minikube":
    #
    #     confirm_destroy = input('Enter Y if you wish to destroy')
    #
    #     if confirm_destroy is not 'Y':
    #
    #         print('Exiting')
    #
    #         exit(1)


def get_kube_parser():

    parser = argparse.ArgumentParser(description=
                                     'Marketo Kubernetes Reactive Extensions Framework, Created by Gideon Bar.')

    parser.add_argument(
        '-cf', '--conf_file',
        type=str,
        help='Full path to config file with all arguments.\nCommandline args override those in the file.'
    )

    parser.add_argument(
        '-pl', '--plan',
        type=bool,
        default=False,
        help='plan means to create kube yaml files but not deploy.'
    )

    parser.add_argument(
        '-kc', '--kube_context',
        type=str,
        help='Kubernetes context i.e. run locally on minikube or in cloud e.g.'
             '\nmarketo-webpersonalization-dev'
    )

    parser.add_argument(
        '-de', '--deploy_env',
        type=str,
        choices=['local', 'dev', 'int', 'qa', 'stage', 'prod'],
        help='Deployment environment local means minikube, dev refers to git branches ...'
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
        '-ds', '--deploy_strategy',
        type=str,
        help='Deployment strategy e.g. "lean" means:\n'
             'single mongo and redis pods to conserve resources while developing or testing'
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


def sanity(conf):

    context = async_cmd('kubectl config current-context')[0][:-1]

    if conf.kube_context != context:

        print(f"There is a discrepancy between the configured and actual contexts:"
              f"\nkube context   : {conf.kube_context}"
              f"\ncurrent context: {context} "
              f"\neither ad context in command-line args or in config file or"
              f"\nto change context run:"
              f"\nkubectl config use-context <the context you meant>"
              f"\n!!! Exiting ...")
        exit(1)
    else:
        print(f"kubernetes current context: {context}")

    if conf.deploy_env == 'local':
        if conf.kube_context != 'minikube':

            print(f"There is a discrepancy between deploy_env: {conf.deploy_env} "
                  f"and kube_context: {conf.kube_context}.\n"
                  f"If you meant to use minikube run:\n"
                  f"kubectl config use-context minikube\n"
                  f"!!! Exiting ...")
            exit(1)

    print(f"conf.supported_deploy_envs: {conf.supported_deploy_envs}")

    if conf.deploy_env not in conf.supported_deploy_envs:

        print(f"We do not support deploy_env: {conf.deploy_env}!!!\n"
              f"If you want to support it add it in:\n"
              f"conf file in supported_deploy_envs field\n"
              f"!!! Exiting ...")
        exit(1)

    # TODO add sanity for debug flag
    # TODO check if configured images exist in repository using docker images | grep or gcloud ...


def process_args(cmd_args):

    if cmd_args.conf_file is None:

        dir_path = os.path.dirname(os.path.realpath(__file__))

        cmd_args.conf_file = dir_path + '/wielder_conf.yaml'


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
    conf.kube_context = named_tuple.kube_context
    conf.cloud_provider = named_tuple.cloud_provider
    conf.gcp_image_repo_zone = named_tuple.gcp_image_repo_zone
    conf.gcp_project = named_tuple.gcp_project
    conf.template_ignore_dirs = named_tuple.template_ignore_dirs
    conf.template_variables = named_tuple.template_variables
    conf.script_variables = named_tuple.script_variables

    sanity(conf)

    return conf



if __name__ == "__main__":

    kube_parser = get_kube_parser()
    kube_args = kube_parser.parse_args()

    conf = process_args(kube_args)

    destroy_sanity(conf)



