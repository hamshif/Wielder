#!/usr/bin/env python

__author__ = 'Gideon Bar'

import logging
import os
import sys
import select

from pyhocon.tool import HOCONConverter as Hc
from wielder.wield.base import WielderBase
from wielder.wield.enumerator import PlanType, WieldAction
from wielder.wield.deployer import get_pods, observe_pod
from wielder.wield.kube_probe import observe_set
from wielder.wield.servicer import observe_service
from wielder.util.arguer import destroy_sanity


class WieldPlan(WielderBase):

    def __init__(self, name, conf, plan_dir, plan_format=PlanType.YAML):

        self.name = name
        self.conf = conf
        self.plan_dir = plan_dir
        self.plan_format = plan_format

        self.module_conf = self.conf[self.name]
        self.namespace = self.module_conf.namespace
        self.ordered_kube_resources = self.module_conf.ordered_kube_resources

        self.plans = []
        self.plan_paths = []

    def to_plan_path(self, res):

        plan_path = f'{self.plan_dir}/{self.name}-{res}.{self.plan_format.value}'
        return plan_path

    def plan(self):

        for res in self.ordered_kube_resources:

            plan = Hc.convert(self.conf[res], self.plan_format.value, 2)

            logging.info(f'\n{plan}')

            self.plans.append(plan)

            if not os.path.exists(self.plan_dir):
                os.makedirs(self.plan_dir)

            plan_path = self.to_plan_path(res=res)

            with open(plan_path, 'wt') as file_out:
                file_out.write(plan)

            self.plan_paths.append(plan_path)

    def wield(self, action=WieldAction.PLAN, auto_approve=False, service_only=False):

        if not isinstance(action, WieldAction):
            raise TypeError("action must of type WieldAction")

        self.plan()

        if action == action.DELETE:

            self.delete(auto_approve)

        elif action == action.APPLY:

            self.apply(
                self.module_conf.observe_deploy,
                self.module_conf.observe_svc,
                service_only
            )

        logging.debug('break')

    def apply(self, observe_deploy=False, observe_svc=False, service_only=False):

        if service_only:

            plan_path = self.to_plan_path(res='service')
            os.system(f"kubectl apply -f {plan_path};")

        else:

            for res in self.ordered_kube_resources:

                plan_path = self.to_plan_path(res=res)
                os.system(f"kubectl apply -f {plan_path};")

                if 'service' in res and observe_svc:

                    observe_service(
                        svc_name=self.name,
                        svc_namespace=self.namespace
                    )

                elif ('deploy' in res or 'statefulset' in res) and observe_deploy:

                    # Observe the pods created
                    pods = get_pods(
                        self.name,
                        namespace=self.namespace
                    )

                    for pod in pods:
                        observe_pod(pod)

                    if '-' in res:

                        res_tup = res.split('-')

                        observe_set(self.namespace, res_tup[0], res_tup[1])

        if self.module_conf.observe_svc:

            observe_service(
                svc_name=self.name,
                svc_namespace=self.namespace
            )

    def delete(self, auto_approve=False):

        destroy_sanity(self.conf)

        if not auto_approve:

            logging.warning(
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
                logging.warning(f'\nAborting deletion of {self.name} resources\n')
                return

        rev = self.ordered_kube_resources
        rev.reverse()

        for res in rev:

            plan_path = self.to_plan_path(res=res)

            if 'namespace' not in res:
                os.system(f"kubectl delete -f {plan_path} --wait=false;")

        # TODO kill all pvc and then all pv
        # TODO check for exit commands in all wield-services
        os.system(f"kubectl delete -n {self.namespace} po -l app={self.name} --force --grace-period=0;")




