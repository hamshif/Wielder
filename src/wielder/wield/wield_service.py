from pyhocon import ConfigFactory as Cf
from wielder.wield.enumerator import PlanType

from wielder.wield.modality import WieldMode
from wielder.wield.planner import WieldPlan
from wield_services.wield.deploy.util import get_conf


class WieldService:
    """
    A class wrapping configuration and code to deploy a service on Kubernetes
    disambiguation: service => a set of kubernetes resources
    e.g. micro-service comprised of deployment service storage ..
    By default it assumes a specific project structure
    It assumes specific fields in the configuration
    """

    def __init__(self, name, module_root, project_override=False, mode=None, conf_dir=None,
                 plan_dir=None, plan_format=PlanType.YAML):

        self.name = name
        self.module_root = module_root
        self.mode = mode if mode else WieldMode()
        self.conf_dir = conf_dir if conf_dir else f'{module_root}conf'
        self.plan_dir = plan_dir if plan_dir else f'{module_root}plan'

        self.wield_path = f'{self.conf_dir}/{self.mode.runtime_env}/{name}-wield.conf'

        self.pretty()

        if project_override:

            print(f'\nOverriding module conf with project conf\n')

            self.conf = get_conf(
                runtime_env=self.mode.runtime_env,
                deploy_env=self.mode.deploy_env,
                module_paths=[self.wield_path]
            )

        else:
            self.conf = Cf.parse_file(self.wield_path)

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
