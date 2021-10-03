import logging
import os

from wielder.util.wgit import WGit
from wielder.wield.base import WielderBase
from wielder.wield.enumerator import PlanType

from wielder.wield.modality import WieldMode
from wielder.wield.planner import WieldPlan
from wielder.util.hocon_util import get_conf_ordered_files
from wielder.util.arguer import wielder_sanity, get_kube_context
from pyhocon import ConfigFactory as Cf


# TODO remove this hardcoded stuff
def get_basic_module_properties(runtime_env, deploy_env, bootstrap_env, name):

    current_kube_context = get_kube_context()

    local_properties = [
        'explain = "This file is where developers override project level configuration properties '
        'it is .gitignored"',
        f'runtime_env : {runtime_env}',
        f'deploy_env : {deploy_env}',
        f'bootstrap_env : {bootstrap_env}',
        '#replace the context below with the context of the kubernetes deployment your working on',
        f'kube_context : {current_kube_context}',
        f'deployments : [\n{name}\n]',
    ]

    return local_properties


def make_sure_project_local_conf_exists(locale, bootstrap_env, runtime_env, deploy_env):

    conf_dir = locale.unique_conf_root

    os.makedirs(conf_dir, exist_ok=True)

    local_path = f'{conf_dir}/modules_override.conf'

    if not os.path.exists(local_path):

        local_properties = [
            'explain = "This file is where developers override configuration properties '
            'at module level and project context"',
            f'# Override module WieldServiceMode\n'
            f'slate.WieldServiceMode : {{\n\n'
            f'  observe : true\n'
            f'  service_only : false\n'
            f'  debug_mode : true\n'
            f'  local_mount : true\n'
            f'}}'
        ]

        with open(local_path, 'wt') as file_out:

            for p in local_properties:
                file_out.write(f'{p}\n\n')

    local_path = f'{conf_dir}/developer.conf'

    if not os.path.exists(local_path):

        logging.info(f'\nCould not find file: {local_path}\nCreating it on the fly!\n')

        if not runtime_env:
            runtime_env = 'docker'

        if not deploy_env:
            deploy_env = 'dev'

        if not bootstrap_env:
            bootstrap_env = 'local'

        project_file = f'{locale.project_root}conf/deploy_env/{deploy_env}/project.conf'

        # TODO use in the future
        tmp_conf = Cf.parse_file(project_file)

        local_properties = get_basic_module_properties(
            runtime_env=runtime_env,
            deploy_env=deploy_env,
            bootstrap_env=bootstrap_env,
            name='slate'
        )

        # TODO
        namespace = 'default'

        local_properties.append(f'namespace : {namespace}')
        #
        # relative_code_path = tmp_conf[self.name]['relativeCodePath']
        #
        # local_code_path = f'{self.super_project_root}/{relative_code_path}'

        with open(local_path, 'wt') as file_out:

            for p in local_properties:

                file_out.write(f'{p}\n\n')

    return conf_dir


def get_conf_context_project(wield_mode, locale, module_paths=[], injection={}):
    """
    Gets the configuration from environment specific config.
    Config files gateways [specific include statements] have to be placed and named according to convention.
    by convention use the unique name.
    :param locale: Locale object with real paths to directories
    :param wield_mode: A project modality derived from cli arguments
    :param injection: a dictionary of variables to override hocon file variables on the fly.
    :param module_paths: paths to module files their values get overridden by project
    :return: pyhocon configuration tree object
    :except: If both data_conf_env are not None
    """

    bootstrap_env = wield_mode.bootstrap_env
    runtime_env = wield_mode.runtime_env
    deploy_env = wield_mode.deploy_env
    unique_conf = wield_mode.unique_conf

    project_root = locale.project_root
    super_project_root = locale.super_project_root

    conf_dir = f'{project_root}conf/unique_conf/{unique_conf}'
    locale.unique_conf_root = conf_dir

    make_sure_project_local_conf_exists(
        locale=locale,
        bootstrap_env=bootstrap_env,
        runtime_env=runtime_env,
        deploy_env=deploy_env
    )

    project_conf_path = f'{project_root}conf/project.conf'
    bootstrap_conf_path = f'{project_root}conf/bootstrap_env/{bootstrap_env}/wield.conf'
    runtime_conf_path = f'{project_root}conf/runtime_env/{runtime_env}/wield.conf'
    deploy_env_conf_path = f'{project_root}conf/deploy_env/{deploy_env}/wield.conf'
    developer_conf_path = f'{conf_dir}/developer.conf'
    module_override_path = f'{conf_dir}/modules_override.conf'

    build_instructions_path = f'{locale.code_root}/ex_config/build_instructions.conf'

    ordered_project_files = module_paths + [
        project_conf_path,
        bootstrap_conf_path,
        runtime_conf_path,
        deploy_env_conf_path,
        build_instructions_path,
        developer_conf_path,
        module_override_path
    ]

    code_repo_commit = 'wile_coyote'

    try:
        wg = WGit(super_project_root)

        injection_str = wg.as_hocon_injection()

        code_repo_commit = wg.get_submodule_commit(locale.code_repo_name)
    except Exception as e:

        logging.error(e)
        injection_str = ''

    injection['runtime_env'] = runtime_env
    injection['deploy_env'] = deploy_env
    injection['bootstrap_env'] = bootstrap_env
    injection['super_project_root'] = super_project_root
    injection['super_project_name'] = locale.super_project_name
    injection['conf_dir'] = unique_conf
    injection['code_repo_commit'] = code_repo_commit
    injection['bootstrap_conf_root'] = conf_dir

    conf = get_conf_ordered_files(
        ordered_conf_files=ordered_project_files,
        injection=injection,
        injection_str=injection_str
    )

    return conf


class WieldProject(WielderBase):
    """

    """
    def __init__(self, name, locale, conf, mode=None, conf_dir=None, plan_dir=None, plan_format=PlanType.YAML):

        self.name = name
        self.locale = locale
        self.conf = conf
        self.mode = mode if mode else WieldMode()
        self.conf_dir = conf_dir if conf_dir else f'{locale.project_root}conf'
        self.plan_dir = plan_dir if plan_dir else f'{locale.project_root}plan'

        if conf.show_project:
            self.pretty()

        logging.debug('break')

        self.plan = WieldPlan(
            name=self.name,
            conf=self.conf,
            plan_dir=self.plan_dir,
            plan_format=plan_format
        )

        if conf.show_project:
            self.plan.pretty()

        wielder_sanity(self.conf, self.mode)



