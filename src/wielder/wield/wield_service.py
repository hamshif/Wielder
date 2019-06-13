from pyhocon import ConfigFactory as Cf
from wielder.wield.enumerator import PlanType

from wielder.wield.modality import WieldMode
from wielder.wield.planner import WieldPlan


class WieldService:
    """
    A class wrapping configuration and code to deploy a service on Kubernetes
    disambiguation: service => a set of kubernetes resources e.g. deployment service storage ..
    By default it assumes a specific project structure
    It assumes specific fields in the configuration
    """

    def __init__(self, name, module_root, mode=WieldMode(), conf_dir=None, plan_dir=None, plan_format=PlanType.YAML):

        self.name = name
        self.module_root = module_root
        self.mode = mode
        self.conf_dir = conf_dir if conf_dir else f'{module_root}conf'
        self.plan_dir = plan_dir if plan_dir else f'{module_root}plan'

        self.wield_path = f'{self.conf_dir}/{mode.runtime_env}/{name}-wield.conf'

        self.pretty()

        self.conf = Cf.parse_file(self.wield_path)

        self.plan = WieldPlan(
            name=self.name,
            conf=self.conf,
            plan_dir=self.plan_dir,
            plan_format=plan_format
        )

        self.plan.pretty()

    def pretty(self):

        [print(it) for it in self.__dict__.items()]
