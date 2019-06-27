import os

from wielder.util.util import get_external_ip
from wielder.wield.enumerator import PlanType

from wielder.wield.modality import WieldMode, WieldServiceMode
from wielder.wield.planner import WieldPlan
from wielder.util.hocon_util import get_conf_ordered_files
from wielder.util.arguer import wielder_sanity, get_kube_context
from pyhocon import ConfigFactory as Cf


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
    e.g. micro-service comprised of configmap, deployment, service, storage, pvc..
    By default it assumes:
        * A specific project structure
        * Specific fields in the configuration
    """

    def __init__(self, name, locale, project_override=False,
                 mode=None, service_mode=None, conf_dir=None, plan_dir=None, plan_format=PlanType.YAML):

        self.name = name
        self.locale = locale
        self.project_override = project_override
        self.mode = mode if mode else WieldMode()
        self.service_mode = service_mode if service_mode else WieldServiceMode()
        self.conf_dir = conf_dir if conf_dir else f'{locale.module_root}conf'
        self.plan_dir = plan_dir if plan_dir else f'{locale.module_root}plan'

        self.wield_path = f'{self.conf_dir}/{self.mode.runtime_env}/{name}-wield.conf'

        self.pretty()

        module_paths = [self.wield_path]

        if self.service_mode.debug_mode:

            # adding to self to facilitate debugging
            self.debug_path = f'{self.conf_dir}/{name}-debug.conf'
            module_paths.append(self.debug_path)

        if self.service_mode.local_mount:

            # adding to self to facilitate debugging
            self.local_mount = f'{self.conf_dir}/{name}-mount.conf'
            module_paths.append(self.local_mount)

        self.local_path = f'{self.conf_dir}/{self.name}-local.conf'
        module_paths.append(self.local_path)

        self.make_sure_module_local_conf_exists()

        if self.project_override:

            self.make_sure_project_local_conf_exists()
            print(f'\nOverriding module conf with project conf\n')

            self.conf = get_conf_context_project(
                project_root=self.locale.project_root,
                runtime_env=self.mode.runtime_env,
                deploy_env=self.mode.deploy_env,
                module_paths=module_paths
            )

        else:

            self.conf = get_conf_ordered_files(module_paths)

        wielder_sanity(self.conf, self.mode, self.service_mode)

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

    def make_sure_project_local_conf_exists(self):

        personal_dir = f'{self.locale.project_root}conf/personal'

        if not os.path.exists(personal_dir):
            os.makedirs(personal_dir)

        local_path = f'{personal_dir}/developer.conf'

        if not os.path.exists(local_path):

            print(f'\nCould not find file: {local_path}\nCreating it on the fly!\n')

            project_file = f'{self.locale.project_root}conf/deploy_env/{self.mode.deploy_env}/project.conf'

            # TODO use in the future
            tmp_conf = Cf.parse_file(project_file)

            current_kube_context = get_kube_context()

            ip = '87.70.171.87'#get_external_ip()

            local_properties = [
                'explain = "This .gitignored file is where developers override configuration properties"',
                f'runtime_env : {self.mode.runtime_env}',
                '#replace the context below with the context of the kubernetes deployment your working on',
                f'kube_context : {current_kube_context}',
                f'client_ips : [\n#add or change local or office ips\n  {ip}/32\n]'
            ]
            #
            # relative_code_path = tmp_conf[self.name]['relativeCodePath']
            #
            # local_code_path = f'{self.super_project_root}/{relative_code_path}'

            with open(local_path, 'wt') as file_out:

                for p in local_properties:

                    file_out.write(f'{p}\n\n')

    def make_sure_module_local_conf_exists(self):

        local_path = f'{self.conf_dir}/{self.name}-local.conf'

        if not os.path.exists(local_path):

            print(f'\ncould not find file: {local_path}\ncreating it on the fly!\n')

            vars_file = f'{self.conf_dir}/{self.mode.runtime_env}/{self.name}-vars.conf'

            tmp_conf = Cf.parse_file(vars_file)

            relative_code_path = tmp_conf[self.name]['relativeCodePath']

            local_code_path = f'{self.locale.super_project_root}/{relative_code_path}'

            with open(local_path, 'wt') as file_out:

                file_out.write(f'\n{self.name}.codePath : {local_code_path}')

