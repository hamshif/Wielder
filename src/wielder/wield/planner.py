#!/usr/bin/env python
import os
import sys
import select

from pyhocon.tool import HOCONConverter as Hc
from wielder.wield.enumerator import PlanType, WieldAction
from wielder.wrx.deployer import get_pods, observe_pod
from wielder.wrx.servicer import observe_service


class WieldPlan:

    def __init__(self, name, conf, plan_dir, plan_format=PlanType.YAML):

        self.name = name
        self.conf = conf
        self.plan_dir = plan_dir
        self.plan_format = plan_format
        self.ordered_kube_resources = []
        # TODO consider where to get namespace
        self.namespace = 'default'
        self.plans = []
        self.plan_paths = []

    def pretty(self):

        [print(it) for it in self.__dict__.items()]

    def to_plan_path(self, res):

        plan_path = f'{self.plan_dir}/{self.name}-{res}.{self.plan_format.value}'
        return plan_path

    def plan(self):

        for res in self.ordered_kube_resources:

            plan = Hc.convert(self.conf[res], self.plan_format.value, 2)

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

        module_conf = self.conf[self.name]

        self.namespace = module_conf.namespace
        self.ordered_kube_resources = self.conf.ordered_kube_resources

        self.plan()

        if action == action.APPLY:

            self.apply(module_conf.observe_deploy, module_conf.observe_svc)

        print('break')

    def apply(self, observe_deploy=False, observe_svc=False):

        for res in self.ordered_kube_resources:

            plan_path = self.to_plan_path(res=res)
            os.system(f"kubectl apply -f {plan_path};")

            if res == 'service' and observe_svc:

                # TODO find a better way to make sure the service is up
                # make sure the service in the cloud is up by checking ip
                observe_service(
                    self.name,
                    namespace=self.namespace
                )

            elif res == 'deploy' and observe_deploy:

                # Observe the pods created
                pods = get_pods(
                    self.name,
                    namespace=self.namespace
                )

                for pod in pods:
                    observe_pod(pod)

    def delete(self, auto_approve=False):

        self.ordered_kube_resources = self.conf.ordered_kube_resources

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




