import logging
import os

from wielder.util.arguer import wielder_sanity
from wielder.wield.base import WielderBase
from wielder.wield.enumerator import PlanType, WieldAction
from wielder.wield.modality import WieldServiceMode
from wielder.wield.planner import WieldPlan
from wielder.wield.project import get_super_project_wield_conf


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
    e.g. microservice comprised of configmap, deployment, service, storage, pvc..
    By default it assumes:
        * A specific project structure
        * Specific fields in the configuration
    """

    def __init__(self, name, project_conf_root, module_root, app,
                 plan_format=PlanType.YAML, injection={}):

        self.name = name
        self.module_root = module_root
        self.image_root = f'{self.module_root}/image/{name}'

        self.project_conf_root = project_conf_root

        self.service_mode = WieldServiceMode()
        self.conf_dir = f'{self.module_root}/conf'

        if name not in injection.items():
            injection[name] = {}

        self.pretty()

        extra_paths = []

        if self.service_mode.debug_mode:

            # adding to self to facilitate debugging
            self.debug_path = f'{self.conf_dir}/{name}-debug.conf'
            extra_paths.append(self.debug_path)

        if self.service_mode.local_mount:

            # adding to self to facilitate debugging
            self.local_mount = f'{self.conf_dir}/{name}-mount.conf'
            extra_paths.append(self.local_mount)

        self.conf = get_super_project_wield_conf(
            project_conf_root=self.project_conf_root,
            module_root=self.module_root,
            app=app,
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

        wielder_sanity(self.conf)


def get_wield_svc(locale, app, service_name, injection={}):
    """
    A convenience wrapper based on cli and directory conventions
    for getting WieldService.
    :param app: The distributed application to which the service belongs
    :param injection: A dictionary that gets evaluated as HOCON.
    :param locale: Used to get directory roots.
    :param service_name: Used as key to configuration.
    :return:
    """

    service = WieldService(
        name=service_name,
        project_conf_root=f'{locale.project_root}/conf',
        module_root=locale.module_root,
        app=app,
        injection=injection,
    )

    return service.conf.action, service
