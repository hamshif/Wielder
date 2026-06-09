#!/usr/bin/env python

__author__ = 'Gideon Bar'

import logging
from enum import Enum
import argparse
import sys
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


def parse_bool_arg(value):
    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "off"}:
        return False

    raise argparse.ArgumentTypeError(f"Expected a boolean value, got [{value}].")


class Conf:

    def __init__(self):

        self.template_ignore_dirs = []

    def attr_list(self, should_print=False):

        items = self.__dict__.items()
        if should_print:

            logging.info("Conf items:\n______\n")
            [logging.info(f"attribute: {k}    value: {v}") for k, v in items]

        return items


def parse_known_args_strict(parser: argparse.ArgumentParser, args=None):
    """
    Parse only exact Wielder-owned flags from argv.
    This avoids host-process flags like pytest's `-s` leaking into config evaluation.
    """
    source_args = sys.argv[1:] if args is None else list(args)
    option_actions = parser._option_string_actions
    filtered_args = []
    index = 0

    while index < len(source_args):
        token = source_args[index]

        if token == "--":
            break

        if token.startswith("--") and "=" in token:
            option = token.split("=", 1)[0]
            if option in option_actions:
                filtered_args.append(token)
            index += 1
            continue

        action = option_actions.get(token)
        if action is None:
            index += 1
            continue

        filtered_args.append(token)
        if action.nargs == 0:
            index += 1
            continue

        if action.nargs == "?":
            if index + 1 < len(source_args) and not source_args[index + 1].startswith("-"):
                filtered_args.append(source_args[index + 1])
                index += 2
                continue

            index += 1
            continue

        if index + 1 < len(source_args):
            filtered_args.append(source_args[index + 1])
            index += 2
            continue

        index += 1

    return parser.parse_known_args(filtered_args)


def destroy_sanity(conf):

    if 'deploy_env' in conf and conf.deploy_env == 'prod':

        logging.error(
            'You are trying to destroy a production environment!!!'
            'Exiting!!!'
        )

        exit(1)


def get_wielder_parser(
        runtime_env=None, bootstrap_env=None, unique_conf=None, deploy_env=None, config_env=None
):

    if runtime_env is None:
        runtime_env = 'docker'
    if bootstrap_env is None:
        bootstrap_env = 'docker'
    if config_env is None:
        config_env = 'local'
    if unique_conf is None:
        unique_conf = 'default_conf'
    if deploy_env is None:
        deploy_env = 'dev'

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
                    'In to one debugable understandable Python framework.',
        allow_abbrev=False
    )

    parser.add_argument(
        '-w', '--wield',
        type=WieldAction,
        choices=list(WieldAction),
        help='Wield actions:\n'
             'plan: produces the configuration without applying it e.g. yaml for kubernetes or terraform vars\n'
             'apply: deploys the plan\n'
             'run: starts a configured runtime process/job without changing provisioned infrastructure\n'
             'monitor: observes configured runtime process/job status without changing it\n'
             'delete: deletes the deployed resources',
        default=WieldAction.PLAN
    )

    parser.add_argument(
        '-re', '--runtime_env',
        type=str,
        choices=['docker', 'gcp', 'on-prem', 'aws', 'azure', 'kind', 'mac', 'ubuntu', 'exdocker', 'win'],
        help='Runtime environment refers to where clusters such as Kubernetes are running',
        default=runtime_env
    )

    parser.add_argument(
        '-ce', '--config_env',
        type=str,
        choices=['docker', 'gcp', 'on-prem', 'aws', 'azure', 'kind', 'mac', 'ubuntu', 'exdocker', 'local'],
        help='Config environment refers to where the configuration is residing E.G AWS bucket',
        default=config_env
    )

    parser.add_argument(
        '-be', '--bootstrap_env',
        type=str,
        choices=['docker', 'gcp', 'on-prem', 'aws', 'azure', 'kind', 'mac', 'ubuntu', 'win'],
        help='The OS where the app runs.',
        default=bootstrap_env
    )

    parser.add_argument(
        '-de', '--deploy_env',
        type=str,
        choices=['local', 'dev', 'int', 'qa', 'stage', 'prod'],
        help='Deployment environment refers to stages of production',
        default=deploy_env
    )

    parser.add_argument(
        '-uc', '--unique_conf',
        type=str,
        help='The name of the overriding config dir, default: default_conf'
             'By convention use a string describing an underscore separated list of keys.'
             'Used to define a unique configuration namespace e.g terraform backend, kube context.'
             'Facilitates concurrent deployments.',
        default=unique_conf
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
        help='Debug mode is a general instruction. '
             'An example would be WieldService debug_mode means the mode-debug.conf file is resolved for configuration',
        default=False
    )

    parser.add_argument(
        '-t', '--test',
        type=parse_bool_arg,
        nargs='?',
        const=True,
        help='Wielder test mode. When true, canonical config resolution includes test.conf overlays when present.',
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


def wielder_sanity_ecosystem(conf):

    try:
        insane = conf.get('insane', False)
        runtime_env = conf.get('runtime_env', 'ecosystem-unset')

        contexts, current_context = config.list_kube_config_contexts()

        contexts = [context['name'] for context in contexts]
        current_context = current_context['name']

        if not insane:

            message = f"\nkube context   : {conf.kube_context}" \
                      f"\nmode.runtime_env is: {runtime_env}" \
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


def get_ecosystem_parser(
        context_conf=None
):
    if context_conf is None:
        context_conf = 'default_conf'

    parser = argparse.ArgumentParser(
        description='Three rings for the cloud-kings in the sky,\n'
                    'Seven for the CI-CD-lords in their halls of stone,\n'
                    'Nine for mortal services doomed to die,\n'
                    'One for the Wielder on his Python throne\n'
                    'In the Land of Babylon where technologies lie.\n\n'
                    'Native Ecosystem Parser built strictly to manage distributed 5D topologies.',
        allow_abbrev=False
    )

    parser.add_argument(
        '-w', '--wield',
        type=WieldAction,
        choices=list(WieldAction),
        help='WieldAction: plan (dry run), apply (execute physical state), run (start runtime job), monitor (observe runtime job), delete (destroy infrastructure). Defaults to PLAN safely.',
        default=WieldAction.PLAN
    )

    parser.add_argument(
        '-es', '--ecosystem',
        type=str,
        help='Topographical ecosystem defining bare-metal mapping (e.g., workstation_wsl, gcp_core).'
    )

    parser.add_argument(
        '-st', '--stage_tier',
        type=str,
        choices=['local', 'dev', 'int', 'qa', 'stage', 'prod'],
        help='Topographical chronological tier (e.g. dev, prod). Replaces legacy deploy_env.'
    )

    parser.add_argument(
        '-se', '--security',
        type=str,
        help='Topographical security hood/envelope (e.g. org, restricted, break_glass).'
    )

    parser.add_argument(
        '-dl', '--deletion',
        type=str,
        help='Topographical deletion cadence policy.'
    )

    parser.add_argument(
        '-cn', '--canary',
        type=str,
        help='Topographical canary predicates payload mapping.'
    )

    parser.add_argument(
        '-cc', '--context_conf', '--unique_conf',
        type=str,
        dest='context_conf',
        help='The name of the central developer context pack, default: default_conf.',
        default=context_conf
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
        help='Debug mode triggers runtime trace logging configuration merges.',
        default=False
    )

    parser.add_argument(
        '-t', '--test',
        type=parse_bool_arg,
        nargs='?',
        const=True,
        help='Wielder test mode. When true, canonical config resolution includes test.conf overlays when present.',
        default=False
    )

    return parser



if __name__ == "__main__":

    setup_logging()

    _wield_parser = get_wielder_parser()
    _wield_args = _wield_parser.parse_args()
