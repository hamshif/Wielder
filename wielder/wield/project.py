#!/usr/bin/env python
import logging
import os

from wielder.util.arguer import get_kube_parser, convert_log_level
from wielder.util.hocon_util import object_to_conf, resolve_ordered
from wielder.util.wgit import WGit


def get_super_project_conf(project_conf_dir, module_conf_dir=None, app=None):
    """
    A modal configuration evaluation varying with the context of the run.

    Hocon configuration files are evaluated in the overriding order listed below.

    1. CLI args
    3. Developer Instructions
    4. Runtime Environment (Where distributed applications run e.g AWS, GCP, Azure)
    5. Deploy Environment e.g int, dev, qa, stage, prod
    6. Bootstrap Environment (Where Code Build transpires, Artifacts Images & Container are Packed,
    Resource Provisioning and deployments are managed).
    7. Project Default Instructions.
    8. Submodule Configurations

    The evaluation paths vary with the CLI arguments values.
    Accordingly Hocon configuration files are evaluated
    if placed in a directory structure similar to Wielder conf directory.

    The function assumes Wielder is a git submodule of its parent directory
    It actively looks for other submodules and evaluates app.conf files in each submodule top directory.

    :param module_conf_dir:
    :param project_conf_dir: the path to the config directory starting from the parent directory of Wielder
    :param app: App name for application specific configuration
    :return: project level modulated hocon config tree
    """

    wield_parser = get_kube_parser()
    wield_args = wield_parser.parse_args()

    print(wield_args)

    action = wield_args.wield
    runtime_env = wield_args.runtime_env
    deploy_env = wield_args.deploy_env
    bootstrap_env = wield_args.bootstrap_env
    unique_conf = wield_args.unique_conf
    log_level = convert_log_level(wield_args.log_level)

    staging_root, super_project_root, super_project_name = get_super_project_roots()

    wg = WGit(super_project_root)

    injection = wg.as_dict_injection()

    injection['action'] = action
    injection['runtime_env'] = runtime_env
    injection['deploy_env'] = deploy_env
    injection['bootstrap_env'] = bootstrap_env
    injection['unique_conf'] = unique_conf
    injection['log_level'] = log_level

    injection['staging_root'] = staging_root
    injection['super_project_root'] = super_project_root
    injection['super_project_name'] = super_project_name

    try:
        wielder_commit = injection['git']['subs']['Wielder']
    except Exception as e:
        wielder_commit = 'elmore_fud'
        logging.error(e)

    injection['wielder_commit'] = wielder_commit

    ordered_project_files = []

    for sub in injection['git']['subs'].keys():
        potential_conf_path = f'{super_project_root}/{sub}/wield.conf'
        if os.path.exists(potential_conf_path):
            ordered_project_files.append(potential_conf_path)

    project_conf_dir = f'{super_project_root}/{project_conf_dir}'
    bootstrap_conf_root = f'{project_conf_dir}/unique_conf/{unique_conf}'

    injection['conf_dir'] = project_conf_dir
    injection['bootstrap_conf_root'] = bootstrap_conf_root

    if app is not None:
        app_conf_path = f'{project_conf_dir}/app/{app}/app.conf'
        ordered_project_files.append(app_conf_path)

    project_conf = f'{project_conf_dir}/project.conf'
    deploy_conf = f'{project_conf_dir}/deploy_env/{deploy_env}/wield.conf'
    bootstrap_conf = f'{project_conf_dir}/bootstrap_env/{bootstrap_env}/wield.conf'
    runtime_conf = f'{project_conf_dir}/runtime_env/{runtime_env}/wield.conf'
    developer_conf = f'{bootstrap_conf_root}/developer.conf'

    ordered_project_files.append(project_conf)
    ordered_project_files.append(deploy_conf)
    ordered_project_files.append(bootstrap_conf)
    ordered_project_files.append(runtime_conf)
    ordered_project_files.append(developer_conf)

    conf = resolve_ordered(
        ordered_conf_paths=ordered_project_files,
        injection=injection
    )

    try:
        code_repo_commit = injection['git']['subs'][conf.code_repo_name]
    except Exception as e:
        code_repo_commit = 'wile_coyote'
        logging.error(e)

    conf.code_repo_commit = code_repo_commit

    return conf


def get_super_project_roots():

    super_project_root = os.path.dirname(os.path.realpath(__file__))

    for i in range(3):
        super_project_root = super_project_root[:super_project_root.rfind('/')]

    logging.info(f'staging_root:\n{super_project_root}')

    staging_root = super_project_root[:super_project_root.rfind('/')]

    super_project_name = super_project_root[super_project_root.rfind('/') + 1:]

    return staging_root, super_project_root, super_project_name


class WielderProject:
    """
    Encapsulates project directory structure and paths
    peculiar to the machine wielder is running on.
    """

    def __init__(self, super_project_root=None, project_root=None, super_project_name=None, packing_root=None, provision_root=None, mock_buckets_root=None, build_root=None):

        if super_project_root is None or project_root is None or super_project_name is None:
            super_project_root, project_root, super_project_name = get_super_project_roots()

        self.super_project_root = super_project_root
        self.project_root = project_root
        self.super_project_name = super_project_name

        if packing_root is None:
            packing_root = f'{super_project_root}/pack'
            os.makedirs(packing_root, exist_ok=True)

        self.packing_root = packing_root

        if build_root is None:
            build_root = f'{super_project_root}/build'
            os.makedirs(build_root, exist_ok=True)

        self.build_root = build_root

        if provision_root is None:
            provision_root = f'{super_project_root}/provision'
            os.makedirs(provision_root, exist_ok=True)

        self.provision_root = provision_root

        if mock_buckets_root is None:
            mock_buckets_root = f'{super_project_root}/buckets'
            os.makedirs(mock_buckets_root, exist_ok=True)

        self.mock_buckets_root = mock_buckets_root

    def as_hocon(self):

        return object_to_conf(self)


if __name__ == "__main__":

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    wp = WielderProject()




