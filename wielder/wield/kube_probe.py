#!/usr/bin/env python

import logging
import json
import time

from wielder.util.commander import subprocess_cmd
from wielder.util.log_util import setup_logging
from wielder.wield.enumerator import KubeResType


def get_kube_namespace_resources_by_type(context, namespace, kube_res, verbose=False):
    """
    A Wrapper of kubectl which parses resources from json
    :param context: Kubernetes context
    :param namespace:
    :type namespace: str
    :param kube_res: statefulset, deployment ...
    :type kube_res: str
    :param verbose: log or not
    :type verbose: bool
    :return: kubernetes resources in the namespace as python
    :rtype:
    """

    res_bytes = subprocess_cmd(f'kubectl --context {context} get {kube_res} -n {namespace} -o json')

    try:
        res_json = res_bytes.decode('utf8').replace("'", '"')
        data = json.loads(res_json)
    except Exception as e:
        data = json.loads(res_bytes)

    if verbose:
        s = json.dumps(data, indent=4, sort_keys=True)
        logging.debug(s)

    return data


def get_kube_res_by_name(context, namespace, kube_res, res_name):
    """
    A Wrapper of kubectl which parses resources from json
    :param context: Kubernetes context
    :param res_name: The name of the resource
    :type res_name: str
    :param namespace:
    :type namespace: str
    :param kube_res: statefulset, deployment ...
    :type kube_res: str
    :return: kubernetes resource as python
    :rtype:
    """

    resources = get_kube_namespace_resources_by_type(context, namespace, kube_res)

    for res in resources['items']:

        if res['metadata']['name'] == res_name:

            s = json.dumps(res, indent=4, sort_keys=True)
            logging.debug(s)

            return res

    logging.warning(
        f"Didn't find a resource for:\n"
        f" context: {context}\n"
        f" namespace: {namespace}\n"
        f" res_name: {res_name}\n"
        f"Going for pods with the res type in them"
    )

    for res in resources['items']:

        actual_res = res['metadata']['name']
        if res_name in actual_res:

            logging.info(f'Found res with similar name: {actual_res}')
            s = json.dumps(res, indent=4, sort_keys=True)
            logging.debug(s)

            return res


def is_kube_set_ready(context, namespace, kube_res, res_name):
    """
    Checks if the kubernetes resource e.g. statefulset is ready
    :param context: Kubernetes context
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

        status = get_kube_res_by_name(context, namespace, kube_res, res_name)

        if status is not None:

            status = status['status']

            if 'currentReplicas' in status:
                actual_replicas = status['currentReplicas']
            else:
                actual_replicas = status['updatedReplicas']

            if status['replicas'] == actual_replicas:

                if 'readyReplicas' in status and status['readyReplicas'] == actual_replicas:

                    return True
        else:
            logging.warning(f'status came back None')

    except Exception as e:
        logging.warning(e)

    return False


def observe_set(context, namespace, kube_res, res_name, timeout=400):
    """
    Block until the kubernetes resource e.g. statefulset is ready
    :param context: Kubernetes context
    :param timeout:
    :type timeout:
    :param res_name: The name of the resource
    :type res_name: str
    :param namespace:
    :type namespace: str
    :param kube_res: statefulset, deployment ...
    :type kube_res: str
    """

    interval = 5
    time_elapsed = 0

    while True:

        if is_kube_set_ready(context, namespace, kube_res, res_name):
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
