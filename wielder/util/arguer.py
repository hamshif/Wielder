#!/usr/bin/env python

__author__ = 'Gideon Bar'

import logging
from enum import Enum
import argparse
from kubernetes import config

from wielder.util.log_util import setup_logging
from wielder.util.commander import async_cmd

from wielder.wield.enumerator import WieldAction, CodeLanguage, LanguageFramework, local_kubes, RuntimeEnv


class LogLevel(Enum):

    CRITICAL = 'critical'
    FATAL = 'fatal'
    ERROR = 'error'
    WARN = 'warn'
    INFO = 'info'
    DEBUG = 'debug'
    NOTSET = 'notest'


def convert_log_level(log_level):

    converted = None
    if log_level is LogLevel.CRITICAL:
        converted = logging.CRITICAL
    elif log_level is LogLevel.FATAL:
        converted = logging.FATAL
    elif log_level is LogLevel.ERROR:
        converted = logging.ERROR
    elif log_level is LogLevel.WARN:
        converted = logging.WARN
    elif log_level is LogLevel.INFO:
        converted = logging.INFO
    elif log_level is LogLevel.DEBUG:
        converted = logging.DEBUG
    else:
        raise Exception('Input must be LogLevel enumeration value')

    return converted


class Conf:

    def __init__(self):

        self.template_ignore_dirs = []

    def attr_list(self, should_print=False):

        items = self.__dict__.items()
        if should_print:

            logging.info("Conf items:\n______\n")
            [logging.info(f"attribute: {k}    value: {v}") for k, v in items]

        return items


def destroy_sanity(conf):

    if conf.deploy_env == 'prod':

        logging.error(
            'You are trying to destroy a production environment!!!'
            'Exiting!!!'
        )

        exit(1)


def get_wielder_parser():

    parser = argparse.ArgumentParser(
        description='Three rings for the cloud-kings in the sky,\n'
                    'Seven for the CI-CD-lords in their halls of stone,\n'
                    'Nine for mortal services doomed to die,\n'
                    'One for the Wielder on his Python throne\n'
                    'In the Land of Babylon where technologies lie.\n'
                    'One ring to rule them all, One ring to find them,\n'
                    'One ring to bring them all, and in the a framework bind them,\n'
                    'In the Land of Babylon where technologies lie.\n\n'
                    
                    'Created by Gideon Bar to tame Bash, Git, Terraform, Containers, Kubernetes, Cloud CLIs etc.\n'
                    'In to one debugable understandable Python framework.'
    )

    parser.add_argument(
        '-w', '--wield',
        type=WieldAction,
        choices=list(WieldAction),
        help='Wield actions:\n'
             'plan: produces the configuration without applying it e.g. yaml for kubernetes or terraform vars\n'
             'apply: deploys the plan\n'
             'delete: deletes the deployed resources',
        default=WieldAction.PLAN
    )

    parser.add_argument(
        '-re', '--runtime_env',
        type=str,
        choices=['docker', 'gcp', 'on-prem', 'aws', 'azure', 'kind', 'mac', 'ubuntu'],
        help='Runtime environment refers to where clusters such as Kubernetes are running',
        default='docker'
    )

    parser.add_argument(
        '-be', '--bootstrap_env',
        type=str,
        choices=['docker', 'gcp', 'on-prem', 'aws', 'azure', 'kind', 'mac', 'ubuntu'],
        help='The OS where the app runs.',
        default='docker'
    )

    parser.add_argument(
        '-de', '--deploy_env',
        type=str,
        choices=['local', 'dev', 'int', 'qa', 'stage', 'prod'],
        help='Deployment environment refers to stages of production',
        default='dev'
    )

    parser.add_argument(
        '-uc', '--unique_conf',
        type=str,
        help='The name of the overriding config dir, default: default_conf'
             'By convention use a string describing an underscore separated list of keys.'
             'Used to define a unique configuration namespace e.g terraform backend, kube context.'
             'Facilitates concurrent deployments.',
        default='default_conf'
    )

    parser.add_argument(
        '-ll', '--log_level',
        type=LogLevel,
        choices=list(LogLevel),
        help='LogLevel: as in Python logging',
        default=LogLevel.INFO
    )

    parser.add_argument(
        '-d', '--debug_mode',
        type=bool,
        help='Debug mode is a general instruction  '
             'An example would be WieldService debug_mode means the mode-debug.conf file is resolved for configuration',
        default=False
    )

    parser.add_argument(
        '-lm', '--local_mount',
        type=bool,
        help='Local mount is an instruction to WieldService '
             'to mount a local directory to the runtime env e.g. Kubernetes or Docker'
             'WieldService will resolve {service name}-mount.conf for configuration',
        default=False
    )

    return parser


def wielder_sanity(conf):

    try:

        contexts, current_context = config.list_kube_config_contexts()

        contexts = [context['name'] for context in contexts]
        current_context = current_context['name']

        if not conf.insane:

            message = f"\nkube context   : {conf.kube_context}" \
                      f"\nmode.runtime_env is: {conf.runtime_env}" \
                      f"\ncurrent context       : {current_context}" \
                      f"\neIf you wish you can either change context or configure congruent runtime_env" \
                      f"\nto change context run:" \
                      f"\nkubectl config use-context <the context you meant>" \

            if conf.kube_context not in current_context:

                message = f"There is a discrepancy between the configured and actual contexts:\n{message}"

                if conf.kube_context not in contexts:
                    message = f"There appears to be no configuration for configured context:\n{message}"

            logging.warning(message)

        else:

            logging.warning(f'Skipping context check!!\nCurrent context is: {current_context}')

    except Exception as e:
        logging.warning(f"{e}")


def sanity(conf):

    context = async_cmd('kubectl config current-context')[0][:-1]

    if conf.kube_context != context:

        logging.error(
            f"There is a discrepancy between the configured and actual contexts:"
            f"\nkube context   : {conf.kube_context}"
            f"\ncurrent context: {context} "
            f"\neither add context in command-line args or in config file or"
            f"\nto change context run:"
              f"\nkubectl config use-context <the context you meant>"
              f"\n!!! Exiting ..."
        )
        exit(1)
    else:
        logging.info(f"kubernetes current context: {context}")

    if conf.deploy_env == 'local':

        if conf.kube_context not in local_kubes:

            logging.error(
                f"There is a discrepancy between deploy_env: {conf.deploy_env} "
                f"and kube_context: {conf.kube_context}.\n"
                f"If you meant to one of these:\n{local_kubes} run:\n"
                f"kubectl config use-context <some local-context>\n"
                f"!!! Exiting ...")
            exit(1)

    logging.info(f"conf.supported_deploy_envs: {conf.supported_deploy_envs}")

    if conf.deploy_env not in conf.supported_deploy_envs:

        logging.error(
            f"We do not support deploy_env: {conf.deploy_env}!!!\n"
            f"If you want to support it add it in:\n"
            f"conf file in supported_deploy_envs field\n"
            f"!!! Exiting ..."
        )
        exit(1)


def get_create_parser():

    parser = argparse.ArgumentParser(
        description='CLI for automatic creation of Wield Services module\n'
                    'Optional adding of wield services module container project'
                    'We suggest you make it a separate Git repository\n'
                    'We suggest you make the separate Git repository a submodule of the project\n'
    )

    parser.add_argument(
        '-ts', '--test',
        type=bool,
        default=False,
        help='Disregards other arguments and tests creation of a container project and modules'
    )

    parser.add_argument(
        '-c', '--create_project',
        type=bool,
        default=True,
        help='Should a wrapper project be created to contain multiple modules'
    )

    parser.add_argument(
        '-tr', '--target_root',
        type=str,
        help='The directory in which you want to place wield-services'
    )

    parser.add_argument(
        '-pn', '--project_name',
        type=str,
        default='micro-services',
        help='The project name'
    )

    parser.add_argument(
        '-mn', '--module_name',
        type=str,
        default='micro',
        help='The definitive microservice name'
    )

    parser.add_argument(
        '-l', '--language',
        type=CodeLanguage,
        choices=list(CodeLanguage),
        help='Code language for containers of the microservice',
        default=CodeLanguage.PYTHON
    )

    parser.add_argument(
        '-fr', '--framework',
        type=LanguageFramework,
        choices=list(LanguageFramework),
        help='A framework corresponding to code language for containers of the microservice '
             'e.g python flask or java spring-boot',
        default=LanguageFramework.FLASK
    )

    parser.add_argument(
        '-ll', '--log_level',
        type=LogLevel,
        choices=list(LogLevel),
        help='LogLevel: as in Python logging',
        default=LogLevel.INFO
    )

    return parser


if __name__ == "__main__":

    setup_logging()

    _kube_parser = get_wielder_parser()
    _kube_args = _kube_parser.parse_args()



