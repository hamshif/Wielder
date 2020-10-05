#!/usr/bin/env python

import logging
import json
import time

from wielder.util.commander import subprocess_cmd
from wielder.util.log_util import setup_logging
from wielder.wield.enumerator import KubeResType


def get_kube_namespace_resources_by_type(namespace, kube_res, verbose=False):
    """
    A Wrapper of kubectl which parses resources from json
    :param namespace:
    :type namespace: str
    :param kube_res: statefullset, deployment ...
    :type kube_res: str
    :param verbose: log or not
    :type verbose: bool
    :return: kubernetes resources in the namespace as python
    :rtype:
    """

    res_bytes = subprocess_cmd(f'kubectl get {kube_res} -n {namespace} -o json')
    res_json = res_bytes.decode('utf8').replace("'", '"')
    data = json.loads(res_json)

    if verbose:
        s = json.dumps(data, indent=4, sort_keys=True)
        logging.debug(s)

    return data


def get_kube_res_by_name(namespace, kube_res, res_name):
    """
    A Wrapper of kubectl which parses resources from json
    :param res_name: The name of the resource
    :type res_name: str
    :param namespace:
    :type namespace: str
    :param kube_res: statefullset, deployment ...
    :type kube_res: str
    :return: kubernetes resource as python
    :rtype:
    """

    resources = get_kube_namespace_resources_by_type(namespace, kube_res)

    for res in resources['items']:

        if res['metadata']['name'] == res_name:

            s = json.dumps(res, indent=4, sort_keys=True)
            logging.debug(s)

            return res


def is_kube_set_ready(namespace, kube_res, res_name):
    """
    Checks if the kubernetes resource e.g. statefulset is ready
    :param res_name: The name of the resource
    :type res_name: str
    :param namespace:
    :type namespace: str
    :param kube_res: statefullset, deployment ...
    :type kube_res: str
    :return: True or False if the resource is ready
    :rtype: bool
    """

    try:

        status = get_kube_res_by_name(namespace, kube_res, res_name)['status']

        if status['replicas'] == status['currentReplicas']:

            if 'readyReplicas' in status and status['readyReplicas'] == status['currentReplicas']:

                return True

    except Exception as e:
        logging.warning(e)

    return False


def observe_set(namespace, kube_res, res_name, timeout=400):
    """
    Block until the kubernetes resource e.g. statefulset is ready
    :param timeout:
    :type timeout:
    :param res_name: The name of the resource
    :type res_name: str
    :param namespace:
    :type namespace: str
    :param kube_res: statefullset, deployment ...
    :type kube_res: str
    """

    interval = 5
    time_elapsed = 0

    while True:

        if is_kube_set_ready(namespace, kube_res, res_name):
            logging.info(f"Kubernetes {kube_res} {res_name} is ready!!!")
            break

        if time_elapsed > timeout:
            logging.info(f"waited {time_elapsed} isn't that exiting")
            return "timeout either provisioning might be too long or some code problem", res_name, kube_res

        try:
            logging.info(f"\n\nWaited {time_elapsed} for {res_name} going to sleep for {interval}")
            time.sleep(interval)
            time_elapsed += interval

        except Exception as e:
            logging.warning(e)


if __name__ == f'__main__':

    setup_logging(log_level=logging.DEBUG)

    if is_kube_set_ready('kafka', KubeResType.STATEFUL_SET.value, 'pzoo'):

        logging.debug('\nwhoopy')

    else:
        logging.debug('\nHaval')
