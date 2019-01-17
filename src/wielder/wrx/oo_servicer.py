#!/usr/bin/env python
import os
import time
import inspect
from rx import Observable, Observer
from kubernetes import client, config

from wielder.util.commander import async_cmd


def get_svc_ip(svc):
    print(f"\n\n")
    print(str(svc))
    ingress = svc.status.load_balancer.ingress
    print(f"ingress: {ingress} is of type: {type(ingress)}")

    if ingress is None:
        return None

    ingress = svc.status.load_balancer.ingress
    print(f"ingress: {ingress} is of type: {type(ingress)}")

    outer_ip = ingress[0].ip
    print(f"outer ip: {outer_ip} is of type: {type(outer_ip)}")
    return outer_ip


# TODO create other resource wrappers with super class or interface or whatever is pythonian
class Servicer:

    # TODO make this a singleton
    def __init__(self):

        config.load_kube_config(
            os.path.join(os.environ["HOME"], '.kube/config'))

        self.v1 = client.CoreV1Api()

    def get_service(self, name):

        svc_list = self.v1.list_namespaced_service("default")

        for svc in svc_list.items:

            if name == svc.metadata.name:
                return svc

    # TODO run this on another thread or process and add rx complying callback.
    # TODO Take care not to double async with async_cmd.
    def async_init_service(self, observer, svc_name, svc_file_path, interval=5):

        result = async_cmd(f"kubectl create -f {svc_file_path}")
        print(f"result: {result}")

        time_waiting = 0
        ip = None

        while ip is None:

            svc = self.get_service(svc_name)

            if time_waiting > 400:
                print(f"waited {time_waiting} that's enough exiting")
                observer.on_next("timeout either provisioning might be too long or some code problem")
                break

            ip = get_svc_ip(svc)

            if ip is None:
                try:
                    observer.on_next(f"\n\nTime spent waiting: {time_waiting}.\nWaiting {interval} seconds for "
                                     f"service {svc_name} to init with outer IP")
                    time.sleep(interval)
                    time_waiting += interval

                except Exception as e:
                    observer.on_error(e)

        observer.on_next(ip)
        observer.on_completed()


class ServicerObserver(Observer):

    def on_error(self, error):
        print(f"error occurred:\n{str(error)}")

    def on_completed(self):
        print("Done!")

    def on_next(self, value):
        print(f"{value}")


def stam(observer):

    d = os.path.dirname(os.path.abspath(inspect.stack()[0][1]))
    print(f"current dir: {d}")
    d = d[:d.rfind('/')]
    d = d[:d.rfind('/')]
    print(f"dir above where we start path to files: {d}")
    # Since there are only 4 services for now it's more readable to do them one at a time
    # sso_result = cmd(f"kubectl create -f {d}/sso/{env_deploy_dir}/sso-service.yaml")
    # print(f"result: {sso_result}")
    # dx_result = cmd(f"kubectl create -f {d}/data-exchange/{env_deploy_dir}/data-exchange-service.yaml")
    # print(f"result: {dx_result}")
    # cep_result = cmd(f"kubectl create -f {d}/cep/{env_deploy_dir}/cep-service.yaml")
    # print(f"result: {cep_result}")

    path = f"{d}/deploy/backoffice/gcp/backoffice-service.yaml"
    servicer = Servicer()

    servicer.async_init_service(observer, svc_name='backoffice', svc_file_path=path)


# Contents of main is project specific
if __name__ == "__main__":

    source = Observable.create(stam)
    source.subscribe(ServicerObserver())
