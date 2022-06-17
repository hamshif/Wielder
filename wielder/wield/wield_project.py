import logging
import logging
import os

from wielder.util.arguer import wielder_sanity
from wielder.util.hocon_util import resolve_ordered
from wielder.util.wgit import WGit
from wielder.wield.base import WielderBase
from wielder.wield.enumerator import PlanType
from wielder.wield.modality import WieldMode
from wielder.wield.planner import WieldPlan


def get_basic_module_properties(injection=[]):

    props = [
        'explain: "This file is where developers override project level configuration properties '
        'it is .gitignored"',
    ]

    props = props + injection

    return props


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

        local_properties = get_basic_module_properties()

        with open(local_path, 'wt') as file_out:

            for p in local_properties:

                file_out.write(f'{p}\n\n')

    return conf_dir


def get_conf_context_project(wield_mode, locale, module_paths=[], app='', injection={}):
    """
    Gets the configuration from environment specific config.
    Config files gateways [specific include statements] have to be placed and named according to convention.
    by convention use the unique name.
    :param app: the application modality overrides
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
    app_conf_path = f'{project_root}conf/app/{app}/app.conf'
    developer_conf_path = f'{conf_dir}/developer.conf'
    module_override_path = f'{conf_dir}/modules_override.conf'

    ordered_project_files = module_paths + [
        project_conf_path,
        bootstrap_conf_path,
        runtime_conf_path,
        deploy_env_conf_path,
        app_conf_path,
        developer_conf_path,
        module_override_path
    ]

    try:
        wg = WGit(super_project_root)

        git_injection = wg.as_dict_injection()

        code_repo_commit = wg.get_submodule_commit(locale.code_repo_name)
        wielder_commit = wg.get_submodule_commit('Wielder')
    except Exception as e:

        code_repo_commit = 'wile_coyote'
        wielder_commit = 'elmore_fud'

        logging.error(e)
        git_injection = {}

    injection['runtime_env'] = runtime_env
    injection['deploy_env'] = deploy_env
    injection['bootstrap_env'] = bootstrap_env
    injection['super_project_root'] = super_project_root
    injection['super_project_name'] = locale.super_project_name
    injection['code_repo_name'] = locale.code_repo_name
    injection['conf_dir'] = unique_conf
    injection['wielder_commit'] = wielder_commit
    injection['code_repo_commit'] = code_repo_commit
    injection['bootstrap_conf_root'] = conf_dir

    injection = {**injection, **git_injection}

    conf = resolve_ordered(
        ordered_conf_paths=ordered_project_files,
        injection=injection
    )

    conf['unique_name_underscore'] = conf.unique_name.lower()

    return conf


class WieldProject(WielderBase):
    """

    """
    def __init__(self, name, locale, conf, mode=None, conf_dir=None, plan_dir=None, plan_format=PlanType.YAML):

        self.name = name
        self.locale = locale
        self.unique_name = conf.unique_name
        self.conf = conf
        self.mode = mode if mode else WieldMode()
        self.conf_dir = conf_dir if conf_dir else f'{locale.project_root}conf'
        self.plan_dir = plan_dir if plan_dir else f'{locale.project_root}plan/{conf.unique_name}'

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



