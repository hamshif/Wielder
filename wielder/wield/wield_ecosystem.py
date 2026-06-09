import logging
import os
import sys
import select
from pathlib import Path
from prometheus_client import Enum
from pyhocon.tool import HOCONConverter as Hc
from pyhocon import ConfigFactory as Cf
from wielder.wield.wield_conf import _parse_hocon

from wielder.wield.enumerator import PlanType, WieldAction
from wielder.wield.deployer import get_pods, observe_pod
from wielder.wield.kube_probe import observe_set, delete_pvc_volumes
from wielder.wield.servicer import observe_service
from wielder.util.arguer import destroy_sanity, wielder_sanity_ecosystem, parse_known_args_strict
from wielder.util.kuber import ensure_kubernetes_namespace
import wielder.util.util as wu
from wielder.wield.modality import WieldServiceMode
from wielder.wield.project import get_super_project_wield_conf, get_super_project_roots, resolve_ordered
from wielder.wield.wield_conf import get_wield_app_conf, get_wield_project_conf, resolve_ecosystem_manifest_path
from wielder.util.arguer import get_wielder_parser, convert_log_level
from wielder.util.wgit import WGit

# Import the original classes to inherit and override
from wielder.wield.planner import WieldPlan
from wielder.wield.wield_service import WieldService

class WieldPlan_ecosystem(WieldPlan):
    """
    Ecosystem fork of WieldPlan natively masking aggressive legacy PyHocon property assertions.
    """
    def wield(self, action=WieldAction.PLAN, auto_approve=False, service_only=False, observe=None):
        if not isinstance(action, WieldAction):
            raise TypeError("action must of type WieldAction")

        self.plan()

        if action == action.DELETE:
            self.delete(auto_approve)
        elif action == action.APPLY:
            if observe is None:
                observe = self.module_conf.get('observe_deploy', False)

            self.apply(
                observe,
                self.module_conf.get('observe_svc', False),
                service_only
            )

        logging.debug('break')

    def apply(self, observe_deploy=False, observe_svc=False, service_only=False):
        ensure_kubernetes_namespace(self.context, self.namespace)

        if service_only:
            plan_path = self.to_plan_path(res='service')
            os.system(f"kubectl --context {self.context} apply -f {plan_path};")
        else:
            for res in self.ordered_kube_resources:
                plan_path = self.to_plan_path(res=res)
                os.system(f"kubectl --context {self.context} apply -f {plan_path};")

                if 'service' in res and observe_svc:
                    observe_service(
                        context=self.context,
                        svc_name=self.name,
                        svc_namespace=self.namespace
                    )

                elif ('deploy' in res or 'statefulset' in res) and observe_deploy:
                    pods = get_pods(
                        self.name,
                        context=self.context,
                        namespace=self.namespace
                    )
                    for pod in pods:
                        observe_pod(pod, self.context)

                    if '-' in res:
                        res_tup = res.split('-')
                        observe_set(self.context, self.namespace, res_tup[0], res_tup[1])

        if self.module_conf.get('observe_svc', False):
            observe_service(
                context=self.context,
                svc_name=self.name,
                svc_namespace=self.namespace
            )

class WieldService_ecosystem(WieldService):
    """
    Ecosystem fork of WieldService wiring the custom WieldPlan_ecosystem parser.
    """
    def __init__(self, name, project_conf_root, module_root, app,
                 app_project_root, app_conf_root,
                 plan_format=PlanType.YAML, injection={}, verbose=False,
                 cli_overrides=None):

        self.name = name
        self.module_root = module_root
        self.image_root = f'{self.module_root}/image/{name}'
        self.project_conf_root = project_conf_root

        self.service_mode = WieldServiceMode()
        self.conf_dir = f'{self.module_root}/conf'

        if name not in injection:
            injection[name] = {}

        if verbose:
            self.pretty()

        extra_paths = []

        if self.service_mode.debug_mode:
            self.debug_path = f'{self.conf_dir}/{name}-debug.conf'
            extra_paths.append(self.debug_path)

        _, super_project_root, _ = get_super_project_roots()
        runtime_defaults = {**injection, "super_project_root": super_project_root}

        base_conf = get_wield_app_conf(
            project_root=app_project_root,
            conf_root=self.project_conf_root,
            app_name=app,
            runtime_defaults=runtime_defaults,
            app_conf_root=app_conf_root,
            cli_overrides=cli_overrides,
            mute=True,
        )

        ecosystem_module_conf_path = None
        module_conf_path = None
        if self.module_root is not None:
            module_conf_path = f'{self.module_root}/conf/wield.conf'
            ecosystem_module_conf_path = resolve_ecosystem_manifest_path(
                Path(f"{self.module_root}/conf/ecosystem"),
                str(base_conf.ecosystem),
            )

        base_module_paths = []
        if ecosystem_module_conf_path is not None:
            base_module_paths.append(str(ecosystem_module_conf_path))
        if extra_paths:
            base_module_paths.extend(extra_paths)

        self.conf = get_wield_app_conf(
            project_root=app_project_root,
            conf_root=self.project_conf_root,
            app_name=app,
            runtime_defaults=runtime_defaults,
            app_conf_root=app_conf_root,
            module_paths=base_module_paths,
            cli_overrides=cli_overrides,
        )

        if module_conf_path is not None:
            module_conf = _parse_hocon(Path(module_conf_path))
            self.conf = Cf.from_dict({}).with_fallback(
                module_conf.with_fallback(self.conf, resolve=False),
                resolve=True,
            )

        unique_name = self.conf.unique_name
        self.plan_dir = f'{self.module_root}/plan/{unique_name}'

        # INJECTING ECOSYSTEM PLANNER OVERRIDE HERE
        self.plan = WieldPlan_ecosystem(
            name=self.name,
            conf=self.conf,
            plan_dir=self.plan_dir,
            plan_format=plan_format
        )

        self.plan.wield(action=WieldAction.PLAN)

        if verbose:
            self.plan.pretty()

        self.packaging = self.plan.module_conf.get('packaging', None)

        wielder_sanity_ecosystem(self.conf)


def get_wield_svc_ecosystem(locale, app, service_name, injection={}, cli_overrides=None):
    if locale.app_project_root == 'unknown' or locale.app_conf_root == 'unknown':
        raise AttributeError(
            "Locale is missing app_project_root/app_conf_root. "
            "The caller must bind the target app repository roots explicitly."
        )

    service = WieldService_ecosystem(
        name=service_name,
        project_conf_root=f'{locale.project_root}/conf',
        module_root=locale.module_root,
        app=app,
        app_project_root=locale.app_project_root,
        app_conf_root=locale.app_conf_root,
        injection=injection,
        cli_overrides=cli_overrides,
    )
    
    # Dynamically converting the Native PyHocon string evaluation safely to Enum
    action_str = service.conf.action
    action_enum = WieldAction(action_str)
    return action_enum, service

def get_super_project_wield_conf_ecosystem(project_conf_root, module_root=None, app=None, extra_paths=None,
                                 configure_wield_modules=True, injection=None, wield_parser=None):
    if wield_parser is None:
        wield_parser = get_wielder_parser()

    wield_args, unknown = parse_known_args_strict(wield_parser)

    staging_root, super_project_root, super_project_name = get_super_project_roots()

    if injection is None:
        injection = {}

    local_system = 'unix' if os.name != 'nt' else 'win'

    action = wield_args.wield
    runtime_env = wield_args.runtime_env
    deploy_env = wield_args.deploy_env
    bootstrap_env = wield_args.bootstrap_env
    if bootstrap_env != local_system:
        logging.warning(f'bootstrap_env: {bootstrap_env} is not consistent with local system: {local_system}')
    unique_conf = wield_args.unique_conf
    log_level = convert_log_level(wield_args.log_level)

    injection['local_system'] = local_system
    injection['action'] = action
    injection['unique_conf'] = unique_conf
    injection['log_level'] = log_level
    injection['staging_root'] = staging_root
    injection['super_project_root'] = super_project_root
    injection['super_project_name'] = super_project_name
    injection['project_conf_root'] = project_conf_root

    debug_mode = wield_args.debug_mode

    injection |= wield_args.__dict__

    wg = WGit(super_project_root)

    injection |= wg.as_dict_injection()

    home = os.getenv('HOME', 'limbo')
    injection['home'] = home

    try:
        wielder_commit = injection['git']['subs']['Wielder']
    except Exception as e:
        wielder_commit = 'elmore_fud'
        logging.error(e)

    injection['wielder_commit'] = wielder_commit

    ordered_project_files = []

    if configure_wield_modules:
        for sub in injection['git']['subs'].keys():
            potential_conf_path = f'{super_project_root}/{sub}/wield.conf'
            if wu.exists(potential_conf_path):
                ordered_project_files.append(potential_conf_path)

    if module_root is not None:
        module_conf_path = f'{module_root}/conf/{runtime_env}/wield.conf'
        ordered_project_files.append(module_conf_path)

    if extra_paths is not None:
        ordered_project_files = ordered_project_files + extra_paths

    if app is not None:
        app_conf_path = f'{project_conf_root}/app/{app}/app.conf'
        ordered_project_files.append(app_conf_path)

    deploy_conf = f'{project_conf_root}/deploy_env/{deploy_env}/wield.conf'
    bootstrap_conf = f'{project_conf_root}/bootstrap_env/{bootstrap_env}/wield.conf'
    runtime_conf = f'{project_conf_root}/runtime_env/{runtime_env}/wield.conf'

    ordered_project_files.append(deploy_conf)
    ordered_project_files.append(bootstrap_conf)
    ordered_project_files.append(runtime_conf)

    bootstrap_conf_root = f'{project_conf_root}/unique_conf/{unique_conf}'
    injection['bootstrap_conf_root'] = bootstrap_conf_root
    developer_conf = f'{bootstrap_conf_root}/developer.conf'

    ordered_project_files.append(developer_conf)

    conf = resolve_ordered(
        ordered_conf_paths=ordered_project_files,
        injection=injection
    )

    try:
        code_repo_commit = injection['git']['subs'][conf[app].code_repo_name]
    except Exception as e:
        code_repo_commit = 'wile_coyote'
        logging.error(e)

    post_resolution = Cf.from_dict({
        app: {
            "code_repo_commit": code_repo_commit
        }
    })

    conf = conf.with_fallback(
        config=post_resolution,
        resolve=True,
    )

    return conf
