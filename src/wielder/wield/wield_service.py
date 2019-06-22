import os
from wielder.wield.enumerator import PlanType

from wielder.wield.modality import WieldMode
from wielder.wield.planner import WieldPlan
from wielder.util.hocon_util import get_conf_ordered_files


def get_module_root(file_context=__file__):

    dir_path = os.path.dirname(os.path.realpath(file_context))
    print(f"\ncurrent working dir: {dir_path}\n")

    module_root = dir_path[:dir_path.rfind('/') + 1]
    print(f"Module root: {module_root}")

    return module_root


def get_conf_context_project(project_root, runtime_env='docker', deploy_env='dev', module_paths=[]):
    """
    Gets the configuration from environment specific config.
    Config files gateways [specific include statements] have to be placed and named according to convention.
    :param project_root: the project root for inferring config and plan paths
    :param module_paths: paths to module files their values get overridden by project
    :param deploy_env: Development stage [dev, int, qa, stage, prod]
    :param runtime_env: Where the kubernetes cluster is running
    :return: pyhocon configuration tree object
    :except: If both data_conf_env are not None
    """

    project_conf_path = f'{project_root}conf/project.conf'
    runtime_conf_path = f'{project_root}conf/runtime_env/{runtime_env}/wield.conf'
    deploy_env_conf_path = f'{project_root}conf/deploy_env/{deploy_env}/wield.conf'
    developer_conf_path = f'{project_root}conf/personal/developer.conf'

    ordered_project_files = module_paths + [
        project_conf_path,
        runtime_conf_path,
        deploy_env_conf_path,
        developer_conf_path
    ]

    return get_conf_ordered_files(ordered_project_files)


class WieldService:
    """
    A class wrapping configuration and code to deploy a service on Kubernetes
    disambiguation: service => a set of kubernetes resources
    e.g. micro-service comprised of deployment service storage ..
    By default it assumes a specific project structure
    It assumes specific fields in the configuration
    """

    def __init__(self, name, module_root, project_root, super_project_root, project_override=False, mode=None, conf_dir=None,
                 plan_dir=None, plan_format=PlanType.YAML):

        self.name = name
        self.module_root = module_root
        self.project_root = project_root
        self.super_project_root = super_project_root
        self.project_override = project_override
        self.mode = mode if mode else WieldMode()
        self.conf_dir = conf_dir if conf_dir else f'{module_root}conf'
        self.plan_dir = plan_dir if plan_dir else f'{module_root}plan'

        self.wield_path = f'{self.conf_dir}/{self.mode.runtime_env}/{name}-wield.conf'

        self.pretty()

        module_paths = [self.wield_path]

        if self.mode.debug_mode:

            # adding to self to facilitate debugging
            self.debug_path = f'{self.conf_dir}/{name}-debug.conf'
            module_paths.append(self.debug_path)

        if self.mode.local_mount:

            # adding to self to facilitate debugging
            self.local_mount = f'{self.conf_dir}/{name}-mount.conf'
            module_paths.append(self.local_mount)

        self.local_path = f'{self.conf_dir}/{self.name}-local.conf'
        module_paths.append(self.local_path)

        self.init_conf(module_paths=module_paths)

        self.make_sure_local_conf_exists(module_paths)

        print('break')

        self.plan = WieldPlan(
            name=self.name,
            conf=self.conf,
            plan_dir=self.plan_dir,
            plan_format=plan_format
        )

        self.plan.pretty()

    def pretty(self):

        [print(it) for it in self.__dict__.items()]

    def make_sure_local_conf_exists(self, module_paths):

        local_path = f'{self.conf_dir}/{self.name}-local.conf'

        if not os.path.exists(local_path):

            print(f'\ncould not find file: {local_path}\ncreating it on the fly!\n')

            relative_code_path = self.conf[self.name]['relativeCodePath']

            local_code_path = f'{self.super_project_root}/{relative_code_path}'

            with open(local_path, 'wt') as file_out:

                file_out.write(f'\n{self.name}.codePath : {local_code_path}')

            self.init_conf(module_paths=module_paths)

    def init_conf(self, module_paths):

        if self.project_override:

            print(f'\nOverriding module conf with project conf\n')

            self.conf = get_conf_context_project(
                project_root=self.project_root,
                runtime_env=self.mode.runtime_env,
                deploy_env=self.mode.deploy_env,
                module_paths=module_paths
            )

        else:

            self.conf = get_conf_ordered_files(module_paths)

