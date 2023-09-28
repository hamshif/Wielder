#!/usr/bin/env python

__author__ = 'Gideon Bar'

import logging
import os
import sys
import select
import wielder.util.util as wu

from pyhocon.tool import HOCONConverter as Hc
from wielder.wield.base import WielderBase
from wielder.wield.enumerator import PlanType, WieldAction
from wielder.wield.deployer import get_pods, observe_pod
from wielder.wield.kube_probe import observe_set, delete_pvc_volumes
from wielder.wield.servicer import observe_service
from wielder.util.arguer import destroy_sanity
from pyhocon import ConfigFactory as Cf

class WieldPlan(WielderBase):

    def __init__(self, name, conf, plan_dir, plan_format=PlanType.YAML):

        self.context = conf.kube_context
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

            if not wu.exists(self.plan_dir):
                wu.makedirs(self.plan_dir)

            plan_path = self.to_plan_path(res=res)

            with open(plan_path, 'wt') as file_out:
                file_out.write(plan)

            self.plan_paths.append(plan_path)

    def wield(self, action=WieldAction.PLAN, auto_approve=False, service_only=False, observe=None):

        if not isinstance(action, WieldAction):
            raise TypeError("action must of type WieldAction")

        self.plan()

        if action == action.DELETE:

            self.delete(auto_approve)

        elif action == action.APPLY:

            if observe is None:
                observe = self.module_conf.observe_deploy

            self.apply(
                observe,
                self.module_conf.observe_svc,
                service_only
            )

        logging.debug('break')

    def apply(self, observe_deploy=False, observe_svc=False, service_only=False):

        os.system(f"kubectl --context {self.context} create namespace {self.namespace};")

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

                    # Observe the pods created
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

        if self.module_conf.observe_svc:

            observe_service(
                context=self.context,
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

            if answer != 'Y':
                logging.warning(f'\nAborting deletion of {self.name} resources\n')
                return

        rev = self.ordered_kube_resources
        rev.reverse()

        for res in rev:

            plan_path = self.to_plan_path(res=res)

            if 'namespace' not in res:
                os.system(f"kubectl --context {self.context} delete -f {plan_path} --wait=false;")

        # TODO check for exit commands in all wield-services
        os.system(f"kubectl --context {self.context} delete -n {self.namespace} po -l app={self.name}"
                  f" --force --grace-period=0;")

        if 'remove_storage_on_delete' in self.module_conf and self.module_conf.remove_storage_on_delete:
            print('woo')

            delete_pvc_volumes(self.context, self.namespace, 'evolution-storage-evolution')


def plan(conf, plan_key, plan_dir, plan_path, plan_format=PlanType.YAML):

    plan_conf = conf.planables[plan_key]
    plan_resources = plan_conf.ordered_resources

    for res in plan_resources:

        files_conf = Cf.parse_file(f'{plan_path}/{res}.conf', resolve=False)

        new_conf = conf.with_fallback(
            config=files_conf,
            resolve=True,
        )

        plans = Hc.convert(new_conf[f'{res}'], plan_format.value, 2)

        logging.info(f'\n{plans}')

        if not os.path.exists(plan_dir):
            wu.makedirs(plan_dir)

        with wu.open(f'{plan_path}/{res}.{plan_format.value}', 'wt') as file_out:
            file_out.write(plans)



