#!/usr/bin/env python
from wielder.default_conf import Conf

__author__ = 'Gideon Bar'

import argparse
from importlib.util import spec_from_file_location, module_from_spec
from wielder.util.commander import async_cmd


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

    if conf.deploy_env not in conf.supported_deploy_envs:

        print(f"We do not support deploy_env: {conf.deploy_env}!!!\n"
              f"If you want to support it add it in:\n"
              f"conf file in supported_deploy_envs field\n"
              f"!!! Exiting ...")
        exit(1)

    # TODO add sanity for debug flag
    # TODO check if configured images exist in repository using docker images | grep or gcloud ...


def set_value(cmd_args, file_args, attribute_name, default_value):

    """
    :param cmd_args: command-line argument first precedence
    :param file_args: conf file setting 2cnd precedence
    :param attribute_name:
    :param default_value: used if no other value is set
    :return: final value for conf
    """

    if hasattr(cmd_args, attribute_name):

        attribute = getattr(cmd_args, attribute_name, default_value)

        if attribute is None:

            attribute = getattr(file_args, attribute_name, default_value)

            if attribute is None:
                return default_value

        return attribute
    else:
        return getattr(cmd_args, attribute_name, default_value)


def process_args(cmd_args):

    if cmd_args.conf_file is None:

        from wielder.default_conf import get_conf
        conf = get_conf()

    else:

        spec = spec_from_file_location("my_conf", cmd_args.conf_file)
        my_conf = module_from_spec(spec)
        spec.loader.exec_module(my_conf)
        conf = Conf()
        conf = my_conf.fill_alternate_conf(conf)

    # TODO make a tuple list and feed it as a function

    conf.plan = set_value(cmd_args, conf, 'plan', False)

    conf.kube_context = set_value(cmd_args, conf, 'kube_context', 'minikube')

    conf.deploy_env = set_value(cmd_args, conf, 'deploy_env', 'local')

    conf.cloud_provider = set_value(cmd_args, conf, 'cloud_provider', 'gcp')

    conf.gcp_project = set_value(cmd_args, conf, 'gcp_project', 'marketo-webpersonalization-dev')

    conf.deploy_strategy = set_value(cmd_args, conf, 'deploy_strategy', 'lean')

    conf.enable_debug = set_value(cmd_args, conf, 'enable_debug', False)

    conf.enable_dev = set_value(cmd_args, conf, 'enable_dev', False)


    sanity(conf)

    return conf


if __name__ == "__main__":

    kube_parser = get_kube_parser()
    kube_args = kube_parser.parse_args()

    conf = process_args(kube_args)
    conf.attr_list(True)

    destroy_sanity(conf)



