#!/usr/bin/env python
import os
import sys
import select
from enum import Enum
from pyhocon import ConfigFactory as Cf
from pyhocon.tool import HOCONConverter as Hc
from wielder.util.arguer import get_kube_parser
from wielder.wrx.deployer import init_observe_pods


class KubeResType(Enum):
    DEPLOY = 'deploy'
    POD = 'pod'
    STATEFUL = 'stateful'
    SERVICE = 'service'
    PV = 'pv'
    PVC = 'pvc'
    STORAGE = 'storage'


class PlanType(Enum):
    YAML = 'yaml'
    JSON = 'json'


class WieldAction(Enum):
    APPLY = 'apply'
    PLAN = 'plan'
    DELETE = 'delete'


def wrap_included(paths):

    includes = ''
    for path in paths:
        includes += f'include file("{path}")\n'

    return includes


def deploy_init_callback(result):

    for i in range(len(result)):

        print(f"{i}: deploy result returned: {result[i]}")


class WieldPlan:

    def __init__(self, name, conf_dir, plan_dir, runtime_env='docker', plan_format=PlanType.YAML):

        self.name = name
        self.conf_dir = conf_dir
        self.plan_dir = plan_dir
        self.runtime_env = runtime_env
        self.wield_path = f'{conf_dir}/{runtime_env}/{name}-wield.conf'
        self.plan_format = plan_format
        self.ordered_kube_resources = []
        self.plans = []
        self.plan_paths = []

    def pretty(self):

        [print(it) for it in self.__dict__.items()]

    def to_plan_path(self, res):

        plan_path = f'{self.plan_dir}/{self.name}-{res}.{self.plan_format.value}'
        return plan_path

    def plan(self, conf):

        for res in self.ordered_kube_resources:

            plan = Hc.convert(conf[res], self.plan_format.value, 2)

            print(f'\n{plan}')

            self.plans.append(plan)

            if not os.path.exists(self.plan_dir):
                os.makedirs(self.plan_dir)

            plan_path = self.to_plan_path(res=res)

            with open(plan_path, 'wt') as file_out:
                file_out.write(plan)

            self.plan_paths.append(plan_path)

    def wield(self, action=WieldAction.PLAN, auto_approve=False):

        if not isinstance(action, WieldAction):
            raise TypeError("action must of type WieldAction")

        if action == action.DELETE:
            self.delete(auto_approve)
            return

        conf = Cf.parse_file(self.wield_path)

        self.ordered_kube_resources = conf.ordered_kube_resources

        self.plan(conf)

        if action == action.APPLY:
            self.apply()

        print('break')

    def apply(self):

        deploy_plan = None

        possible_deploy_plan = self.to_plan_path('deploy')

        for plan_path in self.plan_paths:

            os.system(f"kubectl apply -f {plan_path};")

            if possible_deploy_plan == plan_path:
                deploy_plan = plan_path

        if deploy_plan:
            # Observe the pods created
            init_observe_pods(
                deploy_tuple=(self.name, deploy_plan),
                use_minikube_repo=False,
                callback=deploy_init_callback,
                init=False
            )

    def delete(self, auto_approve=False):

        conf = Cf.parse_file(self.wield_path)

        self.ordered_kube_resources = conf.ordered_kube_resources

        if not auto_approve:

            print(
                f'If your sure you want to delete all {self.name} plan resources\n'
                f'{self.ordered_kube_resources}\n type Y\n'
                f'You have 10 seconds to answer!'
            )

            i, o, e = select.select([sys.stdin], [], [], 10)

            if i:
                answer = sys.stdin.readline().strip()
            else:
                answer = 'N'

            if answer is not 'Y':
                print(f'\nAborting deletion of {self.name} resources\n')
                return

        for res in self.ordered_kube_resources:

            plan_path = self.to_plan_path(res=res)

            os.system(f"kubectl delete -f {plan_path};")

        os.system(f"kubectl delete po -l app={self.name} --force --grace-period=0;")




