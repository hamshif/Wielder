#!/usr/bin/env python
from __future__ import print_function

from abc import ABC, abstractmethod

import os
import rx
from rx import Observer

from wielder.wield.servicer import init_observe_service
from wielder.util.arguer import get_kube_parser, process_args
import concurrent.futures


def svc_init_callback(result):

    for i in range(len(result)):

        print(f"{i}: svc result returned: {result[i]}")


class Deployer(ABC):

    def __init__(self, s):

        self.deploy(s[0])
        self.deploy(s[1])

    @abstractmethod
    def deploy(self, service_only=False, observe=True):

        kube_parser = get_kube_parser()
        kube_args = kube_parser.parse_args()

        conf = process_args(kube_args)
        conf.attr_list(True)

        deploy_function = self.init_service if service_only else self.cep_full_deploy

        dir_path = os.path.dirname(os.path.realpath(__file__))
        print(f"current working dir: {dir_path}")

        rtp_project_root = dir_path.replace('/RtpKube/deploy/cep/rxkube', '')
        print(f"rtp_project_root: {rtp_project_root}")

        module_root = dir_path[:dir_path.rfind('/') + 1]
        print(f"Module root: {module_root}")

        templates = gather_templates(module_root, conf)
        print(f"\ntemplates:\n{templates}")

        print(conf.template_variables)

        deploy_folder = 'minikube' if conf.kube_context == 'minikube' else 'gcp'

        full_svc_file_path = f"{module_root}{deploy_folder}/cep-service.yaml"

        if conf.deploy_strategy is 'stateful_double_pod':

            # I added name as argument for verbosity!

            # TODO find out if the reason I'm not looping is because code supports 2?
            conf1 = cep_conf_add_state(conf, '1')
            templates_to_instances(templates, conf1.template_variables)

            if conf1.plan:
                print("Since plan is True I'm not deploying\n"
                      "Mind you patches are not represented and statefull sets will override")
            else:
                cep_name1 = get_template_var_by_key(conf1.template_variables, '#cep_name#')[1]
                deploy_function(conf1, cep_name1, full_svc_file_path, module_root, observe=observe)

            conf2 = cep_conf_add_state(conf, '2')
            templates_to_instances(templates, conf2.template_variables)

            if conf2.plan:
                print("Since plan is True I'm not deploying\n"
                      "Mind you patches are not represented and statefull sets will override")
            else:
                cep_name2 = get_template_var_by_key(conf2.template_variables, '#cep_name#')[1]
                deploy_function(conf2, cep_name2, full_svc_file_path, module_root, observe=observe)
        else:
            templates_to_instances(templates, conf.template_variables)

            if conf.plan:
                print("Since plan is True I'm not deploying\n"
                      "Mind you patches are not represented and statefull sets will override")
            else:
                cep_name = get_template_var_by_key(conf.template_variables, '#cep_name#')[1]
                deploy_function(conf, cep_name, full_svc_file_path, module_root, observe=observe)

    @abstractmethod
    def init_service(self, conf, svc_name, full_svc_file_path, module_root,
                     callback=svc_init_callback, init=True, observe=True):
        pass


class CepDeployer(Deployer):

    def deploy(self, service_only=False, observe=True):
        pass

    def init_service(self, conf, svc_name, full_svc_file_path, module_root,
                     callback=svc_init_callback, init=True, observe=True):

        if conf.kube_context == "minikube":
            # NO need for load balancer on minikube
            observe = False

        if init:
            os.system(f"kubectl create -f {full_svc_file_path};")
        elif not observe:
            print('wtf')

        if conf.deploy_env != 'prod' and conf.enable_debug:

            # TODO find a polymorphism solution rather than this ugly hack
            # Init and not follow to be able to patch quickly before pod is fired
            print('patching cep service for debug')
            os.system(f'kubectl patch svc {svc_name} --patch "$(cat {module_root}debug/service-debug-patch.yaml)";')

        if observe:

            result = init_observe_service(svc_tuple=(svc_name, full_svc_file_path))

            callback(result)


class ServicerObserver(Observer):

    def on_error(self, error):
        print(f"error occurred:\n{str(error)}")

    def on_completed(self):
        print("Done!")

    def on_next(self, value):
        print(f"{value}")


def output(message_from_other_thread):
    print(f"main thread: {message_from_other_thread}")


# Contents of main is project specific
if __name__ == "__main__":

    kube_parser = get_kube_parser()
    kube_args = kube_parser.parse_args()

    conf = process_args(kube_args)
    conf.attr_list(True)

    _classes = [CepDeployer, CepDeployer, CepDeployer, CepDeployer]

    with concurrent.futures.ProcessPoolExecutor(len(_classes)) as executor:
        rx.Observable.from_(_classes).flat_map(
            lambda ds: executor.submit(ds, ("afro man", "cool"))
        ).subscribe(output)


