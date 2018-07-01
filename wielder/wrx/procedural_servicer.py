#!/usr/bin/env python
from __future__ import print_function

import os
import time
import inspect
import rx
from rx import Observable, Observer
from kubernetes import client, config

from wielder.util.commander import async_cmd
import concurrent.futures


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


def get_service(name):

    config.load_kube_config(os.path.join(os.environ["HOME"], '.kube/config'))

    v1 = client.CoreV1Api()

    svc_list = v1.list_namespaced_service("default")

    for svc in svc_list.items:

        if name == svc.metadata.name:
            return svc


# TODO run this on another thread or process and add rx complying callback.
# TODO Take care not to double async with async_cmd.
def init_service(svc_name, svc_file_path, interval=5):

    result = async_cmd(f"kubectl create -f {svc_file_path}")
    print(f"result: {result}")

    time_waiting = 0
    ip = None

    while ip is None:

        svc = get_service(svc_name)

        if time_waiting > 400:
            print(f"waited {time_waiting} that's enough exiting ...")
            break

        ip = get_svc_ip(svc)

        if ip is None:
            try:
                print(f"\n\nTime spent waiting: {time_waiting}.\nWaiting {interval} seconds for "
                      f"service {svc_name} to init with outer IP")
                time.sleep(interval)
                time_waiting += interval

            except Exception as e:
                print(str(e))

    return ip


# Contents of main is project specific
if __name__ == "__main__":

    d = os.path.dirname(os.path.abspath(inspect.stack()[0][1]))
    print(f"current dir: {d}")
    root_path = d[:d.rfind('/')]
    root_path = root_path[:root_path.rfind('/')]
    print(f"two dirs above where we start path to files: {d}")

    # svc_names = ['cep', 'data-exchange', 'sso', 'backoffice']
    svc_names = ['backoffice']

    for sn in svc_names:
        file_path = f"{root_path}/deploy/{sn}/gcp/{sn}-service.yaml"
        init_service(sn, file_path)

