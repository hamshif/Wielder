import logging
import os

from wielder.util.util import get_external_ip
from wielder.wield.base import WielderBase
from wielder.wield.enumerator import PlanType

from wielder.wield.modality import WieldMode
from wielder.wield.planner import WieldPlan
from wielder.util.hocon_util import get_conf_ordered_files
from wielder.util.arguer import wielder_sanity, get_kube_context
from pyhocon import ConfigFactory as Cf


def get_basic_module_properties(runtime_env, deploy_env, bootstrap_env, name):

    current_kube_context = get_kube_context()

    # TODO find out why getting ip fails when accessed through rx multi process
    ip = '87.70.171.87'  # get_external_ip()

    local_properties = [
        'explain = "This file is where developers override project level configuration properties '
        'it is .gitignored"',
        f'runtime_env : {runtime_env}',
        f'deploy_env : {deploy_env}',
        f'bootstrap_env : {bootstrap_env}',
        '#replace the context below with the context of the kubernetes deployment your working on',
        f'kube_context : {current_kube_context}',
        f'client_ips : [\n#add or change local or office ips\n  {ip}/32\n]',
        f'deployments : [\n{name}\n]',
    ]

    return local_properties


def make_sure_project_local_conf_exists(project_root, runtime_env, deploy_env, bootstrap_env):

    personal_dir = f'{project_root}conf/personal'

    os.makedirs(personal_dir, exist_ok=True)

    local_path = f'{personal_dir}/modules_override.conf'

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

    local_path = f'{personal_dir}/developer.conf'

    if not os.path.exists(local_path):

        logging.info(f'\nCould not find file: {local_path}\nCreating it on the fly!\n')

        if not runtime_env:
            runtime_env = 'docker'

        if not deploy_env:
            deploy_env = 'dev'

        if not bootstrap_env:
            bootstrap_env = 'local'

        project_file = f'{project_root}conf/deploy_env/{deploy_env}/project.conf'

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

    return personal_dir


def get_wield_mode(project_root, runtime_env=None, deploy_env=None, bootstrap_env=None):

    if not runtime_env or not deploy_env:

        make_sure_project_local_conf_exists(
            project_root=project_root,
            runtime_env=runtime_env,
            deploy_env=deploy_env,
            bootstrap_env=bootstrap_env
        )

        developer_conf_path = f'{project_root}conf/personal/developer.conf'
        dev_conf = Cf.parse_file(developer_conf_path)

        if bootstrap_env is None:
            bootstrap_env = dev_conf.bootstrap_env

        if runtime_env is None:
            runtime_env = dev_conf.runtime_env

        if deploy_env is None:
            deploy_env = dev_conf.deploy_env

    wield_mode = WieldMode(runtime_env=runtime_env, deploy_env=deploy_env, bootstrap_env=bootstrap_env)

    return wield_mode


def get_conf_context_project(project_root, runtime_env='docker', deploy_env='dev'
                             , bootstrap_env='local', module_paths=[], injection={}):
    """
    Gets the configuration from environment specific config.
    Config files gateways [specific include statements] have to be placed and named according to convention.
    :param injection: a dictionary of variables to override hocon file variables on the fly.
    :param bootstrap_env: Where deployment automation happens e.g. local devlopers machine, airflow dag.
    :param project_root: the project root for inferring config and plan paths
    :param module_paths: paths to module files their values get overridden by project
    :param deploy_env: Development stage [dev, int, qa, stage, prod]
    :param runtime_env: Where the kubernetes cluster is running
    :return: pyhocon configuration tree object
    :except: If both data_conf_env are not None
    """

    # TODO add bootstrap_env configuration
    project_conf_path = f'{project_root}conf/project.conf'
    runtime_conf_path = f'{project_root}conf/runtime_env/{runtime_env}/wield.conf'
    deploy_env_conf_path = f'{project_root}conf/deploy_env/{deploy_env}/wield.conf'
    developer_conf_path = f'{project_root}conf/personal/developer.conf'
    module_override_path = f'{project_root}conf/personal/modules_override.conf'

    ordered_project_files = module_paths + [
        project_conf_path,
        runtime_conf_path,
        deploy_env_conf_path,
        developer_conf_path,
        module_override_path
    ]

    conf = get_conf_ordered_files(ordered_project_files, injection)
    conf.runtime_env = runtime_env
    conf.deploy_env = deploy_env
    conf.bootstrap_env = bootstrap_env

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

        make_sure_project_local_conf_exists(
            project_root=locale.project_root,
            runtime_env=mode.runtime_env,
            deploy_env=mode.deploy_env,
            bootstrap_env=mode.bootstrap_env
        )

        wielder_sanity(self.conf, self.mode)

        logging.debug('break')

        self.plan = WieldPlan(
            name=self.name,
            conf=self.conf,
            plan_dir=self.plan_dir,
            plan_format=plan_format
        )

        if conf.show_project:
            self.plan.pretty()



