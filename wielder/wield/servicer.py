#!/usr/bin/env python
from __future__ import print_function

import logging
import os
import time
import inspect
import rx
from rx import operators as ops
import concurrent.futures
from kubernetes import client, config

from wielder.util.commander import async_cmd


def get_svc_ingress_property(svc, name):

    print(f"\n\n")
    logging.info(str(svc))
    ingress = svc.status.load_balancer.ingress
    logging.info(f"ingress: {ingress} is of type: {type(ingress)}")

    if ingress is None:
        return None

    prop = None
    if name == 'ip':
        prop = ingress[0].ip
    elif name == 'hostname':
        prop = ingress[0].hostname

    logging.info(f"outer ip: {prop} is of type: {type(prop)}")
    return prop


def get_svc_ip(svc):

    outer_ip = get_svc_ingress_property(svc, 'ip')
    return outer_ip


def get_svc_hostname(svc):

    hostname = get_svc_ingress_property(svc, 'hostname')
    return hostname


def get_service(name, namespace="default"):

    config.load_kube_config(os.path.join(os.environ["HOME"], '.kube/config'))

    v1 = client.CoreV1Api()

    svc_list = v1.list_namespaced_service(namespace)

    for svc in svc_list.items:

        if name == svc.metadata.name:
            return svc


# TODO merge this with init_observe_service or deprecate
# TODO find a better way to make sure the service is up
# make sure the service in the cloud is up by checking ip
def observe_service(svc_name, svc_namespace, prop_name='ip'):

    interval = 5

    time_waiting = 0
    svc = None
    prop = None

    while prop is None:

        svc = get_service(svc_name, namespace=svc_namespace)

        if time_waiting > 400:
            logging.info(f"waited {time_waiting} that'sn enough exiting")
            return "timeout either provisioning might be too long or some code problem", svc_name, svc
            break

        prop = get_svc_ingress_property(svc, prop_name)

        if prop is None:
            try:
                logging.info(f"\n\nWaited {time_waiting} for {svc_name} going to sleep for {interval}")
                time.sleep(interval)
                time_waiting += interval

            except Exception as e:
                return svc_name, svc, e

    return svc_name, svc, prop


def init_observe_service(svc_tuple):
    # TODO add ip or hostname property for services of both kinds

    svc_name = svc_tuple[0]
    svc_file_path = svc_tuple[1]

    if len(svc_tuple) > 2:
        svc_namespace = svc_tuple[2]
    else:
        svc_namespace = "default"

    interval = 5

    result = async_cmd(f"kubectl create -f {svc_file_path}")
    logging.info(f"result: {result}")

    time_waiting = 0
    ip = None

    svc = None

    while ip is None:

        svc = get_service(svc_name, namespace=svc_namespace)

        if time_waiting > 400:
            logging.info(f"waited {time_waiting} that'sn enough exiting")
            return "timeout either provisioning might be too long or some code problem", svc_name, svc
            break

        ip = get_svc_ip(svc)

        if ip is None:
            try:
                logging.info(f"\n\nWaited {time_waiting} for {svc_name} going to sleep for {interval}")
                time.sleep(interval)
                time_waiting += interval

            except Exception as e:
                return svc_name, svc, e

    return svc_name, svc, ip


def get_tuple_generator(f, values):
    return ((v, f(v)) for v in values)


# TODO write error and progress discerning logic or use Observer
def output(result):

    [logging.info(f"result: {r}") for r in result]


# Contents of main is project specific
if __name__ == "__main__":

    d = os.path.dirname(os.path.abspath(inspect.stack()[0][1]))
    logging.info(f"current dir: {d}")
    root_path = d[:d.rfind('/')]
    root_path = root_path[:root_path.rfind('/')]
    logging.debug(f"two dirs above where we start path to files: {d}")

    # TODO get the service names from config
    svc_names = ['cep', 'data-exchange', 'sso', 'backoffice']
    svc_tup_gen = get_tuple_generator(lambda sn: f"{root_path}/deploy/{sn}/gcp/{sn}-service.yaml", svc_names)

    source = rx.from_(svc_tup_gen)

    with concurrent.futures.ProcessPoolExecutor(len(svc_names)) as executor:
        composed = source.pipe(
            ops.flat_map(
                lambda service_name: executor.submit(init_observe_service, service_name)
            )
        )
        composed.subscribe(output)

