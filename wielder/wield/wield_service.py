import logging
import os
from pyhocon import ConfigFactory as Cf

from wielder.wield.base import WielderBase
from wielder.wield.enumerator import PlanType, WieldAction
from wielder.util.arguer import get_kube_parser
from wielder.wield.modality import WieldMode, WieldServiceMode
from wielder.wield.planner import WieldPlan
from wielder.util.hocon_util import get_conf_ordered_files
from wielder.util.arguer import wielder_sanity
from wielder.wield.wield_project import get_basic_module_properties, get_conf_context_project


def get_module_root(file_context=__file__):

    dir_path = os.path.dirname(os.path.realpath(file_context))
    logging.debug(f"\ncurrent working dir: {dir_path}\n")

    module_root = dir_path[:dir_path.rfind('/') + 1]
    logging.info(f"Module root: {module_root}")

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

    def __init__(self, name, locale, wield_mode=None, service_mode=None,
                 conf_dir=None, plan_dir=None, plan_format=PlanType.YAML, injection={}):

        self.name = name
        self.locale = locale
        self.wield_mode = wield_mode if wield_mode else WieldMode()
        self.service_mode = service_mode if service_mode else WieldServiceMode()
        self.conf_dir = conf_dir if conf_dir else f'{locale.module_root}conf'
        self.plan_dir = plan_dir if plan_dir else f'{locale.module_root}plan'

        self.wield_path = f'{self.conf_dir}/{self.wield_mode.runtime_env}/{name}-wield.conf'

        if name not in injection:
            injection[name] = {}

        injection[name]['code_path'] = f'{locale.code_root}'

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

        self.local_path = f'{self.conf_dir}/{self.wield_mode.runtime_env}/{self.name}-local.conf'
        module_paths.append(self.local_path)

        self.local_path = self.make_sure_module_local_conf_exists()
        module_paths.append(self.local_path)

        if self.service_mode.project_override:

            logging.info(f'\nTo Override module conf with project conf use\n{locale.unique_conf_root}')

            self.conf = get_conf_context_project(
                wield_mode=self.wield_mode,
                locale=locale,
                module_paths=module_paths,
                injection=injection
            )

        else:

            self.conf = get_conf_ordered_files(module_paths, injection=injection)

        logging.debug('break')

        self.plan = WieldPlan(
            name=self.name,
            conf=self.conf,
            plan_dir=self.plan_dir,
            plan_format=plan_format
        )

        self.plan.wield(action=WieldAction.PLAN)

        self.plan.pretty()

        self.packaging = self.plan.module_conf.packaging

        wielder_sanity(self.conf, self.wield_mode, self.service_mode)

    def make_sure_module_local_conf_exists(self):

        local_path = f'{self.conf_dir}/{self.wield_mode.runtime_env}/{self.name}-local.conf'

        if not os.path.exists(local_path):

            logging.info(f'\ncould not find file: {local_path}\ncreating it on the fly!\n')

            vars_file = f'{self.conf_dir}/{self.wield_mode.runtime_env}/{self.name}-vars.conf'

            tmp_conf = Cf.parse_file(vars_file)

            relative_code_path = tmp_conf[self.name]['relativeCodePath']

            local_code_path = f'{self.locale.super_project_root}/{relative_code_path}'

            local_properties = get_basic_module_properties(self.wield_mode.runtime_env, self.wield_mode.deploy_env, self.name)

            local_properties.append(f'{self.name}.codePath : {local_code_path}')

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
        locale=locale,
        injection=injection
    )

    return action, service
