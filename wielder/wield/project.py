#!/usr/bin/env python

import json
import logging
import os

import yaml

import wielder.util.util as wu
from pyhocon import ConfigFactory

from wielder.util.arguer import get_wielder_parser, convert_log_level
from wielder.util.hocon_util import object_to_conf, resolve_ordered
from wielder.util.wgit import WGit
from wielder.wield.enumerator import local_kubes

DEFAULT_WIELDER_APP = 'snegurochka'


def get_project_wield_conf(conf_path, app_name, run_name, override_ordered_files, injection=None, wield_parser=None):
    if wield_parser is None:
        wield_parser = get_wielder_parser()

    wield_args = wield_parser.parse_args()

    if injection is None:
        injection = {}

    runtime_env = wield_args.runtime_env

    app_path = f"{conf_path}/app/{app_name}/app.conf"
    run_path = f"{conf_path}/runs/{run_name}.conf"
    runtime_env_path = f"{conf_path}/runtime_env/{runtime_env}/env.conf"

    plan_path = f"{conf_path}/plan"

    injection['conf_path'] = conf_path
    injection['plan_path'] = plan_path
    injection['run_name'] = run_name

    action = wield_args.wield
    injection['action'] = action

    log_level = convert_log_level(wield_args.log_level)
    injection['log_level'] = log_level

    injection |= wield_args.__dict__

    if override_ordered_files is None:
        override_ordered_files = []

    ordered_conf_files = [
                             app_path,
                             runtime_env_path,
                             run_path,
                         ] + override_ordered_files

    conf = resolve_ordered(
        ordered_conf_paths=ordered_conf_files,
        injection=injection
    )

    return conf


def default_conf_root():
    _, super_project_root, _ = get_super_project_roots()

    return f'{super_project_root}/Wielder/conf'


def get_super_project_wield_conf(project_conf_root, module_root=None, app=None, extra_paths=None,
                                 configure_wield_modules=True, injection=None, wield_parser=None):
    """
    A modal configuration evaluation varying with the context of the run.

    Hocon configuration files are evaluated in the overriding order listed below.

    1. CLI args
    3. Developer Instructions
    4. Runtime Environment (Where distributed applications run e.g AWS, GCP, Azure)
    5. Deploy Environment e.g. int, dev, qa, stage, prod
    6. Bootstrap Environment (Where Code Build transpires, Artifacts Images & Container are Packed,
    Resource Provisioning and deployments are managed).
    7. Project Default Instructions.
    8. Submodule Configurations

    The evaluation paths vary with the CLI arguments values.
    Accordingly, Hocon configuration files are evaluated
    if placed in a directory structure similar to Wielder conf directory.

    The function assumes Wielder is a git submodule of its parent directory
    It actively looks for other submodules and evaluates app.conf files in each submodule top directory.

    :param wield_parser: An alternative parser. best to use wield_parser as a base and add. e.g. kafka_parser
    :param configure_wield_modules:
    :param injection: A dictionary to inject to Hocon config resolution
    :param extra_paths: Config files that get overridden by project and override module if it exists.
    :param module_root: The path to the module configuration root
    :param project_conf_root: the path to the config directory starting from the parent directory of Wielder
    :param app: App name for application specific configuration
    :return: project level modulated hocon config tree
    """

    if wield_parser is None:
        wield_parser = get_wielder_parser()

    wield_args = wield_parser.parse_args()

    staging_root, super_project_root, super_project_name = get_super_project_roots()

    if injection is None:
        injection = {}

    local_system = 'unix' if os.name != 'nt' else 'win'

    action = wield_args.wield
    runtime_env = wield_args.runtime_env
    deploy_env = wield_args.deploy_env
    bootstrap_env = wield_args.bootstrap_env
    if bootstrap_env != local_system:
        logging.warning(f'bootstrap_env: {bootstrap_env} is not consistent with local system: {local_system}')
    unique_conf = wield_args.unique_conf
    log_level = convert_log_level(wield_args.log_level)

    injection['local_system'] = local_system
    injection['action'] = action
    injection['unique_conf'] = unique_conf
    injection['log_level'] = log_level
    injection['staging_root'] = staging_root
    injection['super_project_root'] = super_project_root
    injection['super_project_name'] = super_project_name
    injection['project_conf_root'] = project_conf_root

    # TODO add specific debug and local mount paths appropriately
    debug_mode = wield_args.debug_mode
    local_mount = wield_args.local_mount

    injection |= wield_args.__dict__

    wg = WGit(super_project_root)

    injection |= wg.as_dict_injection()

    home = os.getenv('HOME', 'limbo')
    injection['home'] = home

    try:
        wielder_commit = injection['git']['subs']['Wielder']
    except Exception as e:
        wielder_commit = 'elmore_fud'
        logging.error(e)

    injection['wielder_commit'] = wielder_commit

    ordered_project_files = []

    if configure_wield_modules:
        for sub in injection['git']['subs'].keys():
            potential_conf_path = f'{super_project_root}/{sub}/wield.conf'
            if wu.exists(potential_conf_path):
                ordered_project_files.append(potential_conf_path)

    if module_root is not None:
        module_conf_path = f'{module_root}/conf/{runtime_env}/wield.conf'
        ordered_project_files.append(module_conf_path)

    if extra_paths is not None:
        ordered_project_files = ordered_project_files + extra_paths

    if app is not None:
        app_conf_path = f'{project_conf_root}/app/{app}/app.conf'
        ordered_project_files.append(app_conf_path)

    deploy_conf = f'{project_conf_root}/deploy_env/{deploy_env}/wield.conf'
    bootstrap_conf = f'{project_conf_root}/bootstrap_env/{bootstrap_env}/wield.conf'
    runtime_conf = f'{project_conf_root}/runtime_env/{runtime_env}/wield.conf'

    ordered_project_files.append(deploy_conf)
    ordered_project_files.append(bootstrap_conf)
    ordered_project_files.append(runtime_conf)

    bootstrap_conf_root = f'{project_conf_root}/unique_conf/{unique_conf}'
    injection['bootstrap_conf_root'] = bootstrap_conf_root
    developer_conf = f'{bootstrap_conf_root}/developer.conf'

    ordered_project_files.append(developer_conf)

    conf = resolve_ordered(
        ordered_conf_paths=ordered_project_files,
        injection=injection
    )

    try:
        code_repo_commit = injection['git']['subs'][conf[app].code_repo_name]
    except Exception as e:
        code_repo_commit = 'wile_coyote'
        logging.error(e)

    post_resolution = ConfigFactory.from_dict({
        app: {
            "code_repo_commit": code_repo_commit
        }
    })

    conf = conf.with_fallback(
        config=post_resolution,
        resolve=True,
    )

    return conf


def get_super_project_roots():
    super_project_root = os.path.dirname(os.path.realpath(__file__))

    for i in range(3):
        super_project_root = super_project_root[:super_project_root.rfind(os.path.sep)]

    logging.info(f'staging_root:\n{super_project_root}')

    staging_root = super_project_root[:super_project_root.rfind(os.path.sep)]

    super_project_name = super_project_root[super_project_root.rfind(os.path.sep) + 1:]

    staging_root = wu.convert_to_unix_path(staging_root)
    super_project_root = wu.convert_to_unix_path(super_project_root)
    super_project_name = wu.convert_to_unix_path(super_project_name)
    return staging_root, super_project_root, super_project_name


def configure_external_kafka_urls(conf):
    if conf.kafka.override_exposed:

        ports = [30000 + i for i in range(conf.third_party.kafka_replicas)]

        print(ports)

        runtime_env = conf.runtime_env
        exposed_brokers = ""

        if runtime_env == 'aws':
            i = 0

            for port in ports:
                exposed_brokers = f'{exposed_brokers},broker-{i}.{conf.unique_name}:{port}'
                i = i + 1

        elif runtime_env in local_kubes:

            for port in ports:
                exposed_brokers = f'{exposed_brokers},localhost:{port}'

        conf.kafka['exposed_brokers'] = exposed_brokers[1:]
    else:
        exposed_brokers = conf.kafka['exposed_brokers']

    print(f'kafka_brokers: {exposed_brokers}')


def get_local_path(conf, relative_path, bucket_name=None):
    if bucket_name is None:
        bucket_name = conf.namespace_bucket

    local_destination = f'{conf.local_buckets_root}/{bucket_name}/{relative_path}'
    return local_destination


def configure_project_module(conf, app):
    """
    Configure a project module
    :param conf:
    :param module:
    :param app: the application namespace
    :return:
    """

    if app in conf:
        module_config = conf[app]

        if 'configure_modules' in module_config:
            config_instructions = module_config['configure_modules']

            for key, value in config_instructions.items():

                dest = value.dest

                wu.makedirs(wu.dirname(dest))
                _type = value.type

                match _type:
                    case 'text':
                        content = '\n'.join(str(item) for item in value.content) + '\n'

                        mode = 'w'
                        match value.mode:
                            case 'append':
                                mode = 'a'
                            case 'prepend':
                                mode = 'w+'
                                if wu.exists(dest):
                                    with open(dest, 'r') as file:
                                        existing_content = file.read()
                                        content = existing_content + content

                        with open(dest, mode) as file:
                            file.write(content)

                    case 'json':
                        with open(dest, 'w') as file:
                            json.dump(value.content, file, indent=4)
                    case 'yaml':
                        with open(dest, 'w') as file:
                            yaml.dump(value.content, file)


class WielderProject:
    """
    Encapsulates project directory structure and paths
    peculiar to the machine wielder is running on.
    """

    def __init__(self, super_project_root=None, project_root=None, super_project_name=None, packing_root=None,
                 provision_root=None, mock_buckets_root=None, build_root=None):

        if super_project_root is None or project_root is None or super_project_name is None:
            super_project_root, project_root, super_project_name = get_super_project_roots()

        self.super_project_root = super_project_root
        self.project_root = project_root
        self.super_project_name = super_project_name

        if packing_root is None:
            packing_root = f'{super_project_root}/pack'
            wu.makedirs(packing_root, exist_ok=True)

        self.packing_root = packing_root

        if build_root is None:
            build_root = f'{super_project_root}/build'
            wu.makedirs(build_root, exist_ok=True)

        self.build_root = build_root

        if provision_root is None:
            provision_root = f'{super_project_root}/provision'
            wu.makedirs(provision_root, exist_ok=True)

        self.provision_root = provision_root

        if mock_buckets_root is None:
            mock_buckets_root = f'{super_project_root}/buckets'
            wu.makedirs(mock_buckets_root, exist_ok=True)

        self.mock_buckets_root = mock_buckets_root

    def as_hocon(self):

        return object_to_conf(self)


if __name__ == "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    wp = WielderProject()
