import logging
import os

from wielder.util.arguer import get_kube_parser
from wielder.util.arguer import wielder_sanity
from wielder.wield.base import WielderBase
from wielder.wield.enumerator import PlanType, WieldAction
from wielder.wield.modality import WieldMode, WieldServiceMode
from wielder.wield.planner import WieldPlan
from wielder.wield.project import get_super_project_conf
from wielder.wield.wield_project import get_basic_module_properties


def get_module_root(file_context=__file__):

    dir_path = os.path.dirname(os.path.realpath(file_context))
    logging.debug(f"\ncurrent working dir: {dir_path}")

    module_root = dir_path[:dir_path.rfind('/')]
    logging.debug(f"Module root: {module_root}")

    return module_root


class WieldService(WielderBase):
    """
    A class wrapping configuration and code to deploy a service on Kubernetes
    disambiguation: service => a set of kubernetes resources
    e.g. micro-service comprised of configmap, deployment, service, storage, pvc..
    By default it assumes:
        * A specific project structure
        * Specific fields in the configuration
    """

    def __init__(self, name, project_conf_root, module_root, wield_mode=None, service_mode=None,
                 plan_format=PlanType.YAML, injection={}):

        self.name = name
        self.module_root = module_root
        self.image_root = f'{self.module_root}/image/{name}'

        self.project_conf_root = project_conf_root

        self.wield_mode = wield_mode if wield_mode else WieldMode()
        self.service_mode = service_mode if service_mode else WieldServiceMode()
        self.conf_dir = f'{self.module_root}/conf'

        self.wield_path = f'{self.conf_dir}/{self.wield_mode.runtime_env}/{name}-wield.conf'

        if name not in injection:
            injection[name] = {}

        self.pretty()

        module_paths = [self.wield_path]
        extra_paths = []

        if self.service_mode.debug_mode:

            # adding to self to facilitate debugging
            self.debug_path = f'{self.conf_dir}/{name}-debug.conf'
            module_paths.append(self.debug_path)
            extra_paths.append(self.debug_path)

        # TODO reconsider local mounts it should probably be removed
        if self.service_mode.local_mount:

            # adding to self to facilitate debugging
            self.local_mount = f'{self.conf_dir}/{name}-mount.conf'
            extra_paths.append(self.local_mount)

        self.conf = get_super_project_conf(
            project_conf_root=self.project_conf_root,
            module_root=self.module_root,
            extra_paths=extra_paths,
            injection=injection
        )

        unique_name = self.conf.unique_name

        self.plan_dir = f'{self.module_root}/plan/{unique_name}'

        self.plan = WieldPlan(
            name=self.name,
            conf=self.conf,
            plan_dir=self.plan_dir,
            plan_format=plan_format
        )

        self.plan.wield(action=WieldAction.PLAN)

        self.plan.pretty()

        self.packaging = self.plan.module_conf.packaging

        wielder_sanity(self.conf, self.wield_mode)

    def make_sure_module_local_conf_exists(self):

        local_path = f'{self.conf_dir}/{self.wield_mode.runtime_env}/{self.name}-local.conf'

        if not os.path.exists(local_path):

            logging.info(f'\ncould not find file: {local_path}\ncreating it on the fly!\n')

            local_properties = get_basic_module_properties()

            with open(local_path, 'wt') as file_out:

                for p in local_properties:

                    file_out.write(f'{p}\n\n')

        return local_path


def get_wield_svc(locale, service_name, injection={}):
    """
    A convenience wrapper based on cli and directory conventions
    for getting WieldService.
    :param locale: used to get directory roots
    :param service_name: used as key to configuration
    :return:
    """

    kube_parser = get_kube_parser()
    kube_args = kube_parser.parse_args()

    action = kube_args.wield

    service = WieldService(
        name=service_name,
        project_conf_root=f'{locale.project_root}/conf',
        module_root=locale.module_root,
        injection=injection,
    )

    return action, service
