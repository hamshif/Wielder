#!/usr/bin/env python

import logging
import json
import os
import time

from wielder.util.commander import subprocess_cmd
from wielder.util.log_util import setup_logging
from wielder.wield.enumerator import KubeResType, KubeJobStatus


def is_job_complete(context, namespace, res_name):

    status = get_job_status(context, namespace, res_name)

    if status == KubeJobStatus.COMPLETE.value:

        return True

    return False


def get_job_status(context, namespace, res_name):

    complete = KubeJobStatus.FAILED.value
    counter = 0

    job_active = True

    while job_active:

        job = get_kube_res_by_name(context, namespace, KubeResType.JOBS.value, res_name)

        status = job['status']

        if 'active' in status:

            logging.info(f'context = {context} namespace = {namespace} res_name = {res_name}')
            logging.info(f'status: {status},')
            logging.info(f'{counter} Not ready sleeping for 5')
            time.sleep(5)
            counter = counter + 1
        else:
            complete = status['conditions'][0]['type']
            job_active = False

    logging.info(f'context = {context} namespace = {namespace} res_name = {res_name}')
    logging.info(f'status: {complete}')

    return complete


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


def get_kube_resources_by_name(context, namespace, kube_res, res_name):
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

    names = []

    for res in resources['items']:

        actual_res = res['metadata']['name']
        if res_name in actual_res:

            logging.info(f'Found res with similar name: {actual_res}')
            s = json.dumps(res, indent=4, sort_keys=True)
            logging.debug(s)

            names.append(res)

    return names


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

    resources = get_kube_resources_by_name(context, namespace, kube_res, res_name)

    if len(resources) > 0:
        return resources[0]


def get_pvcs_pvs_by_partial_claim_name(context, namespace, res_name):
    """
    A Wrapper of kubectl which parses resources from json
    :param context: Kubernetes context
    :param res_name: The name of the resource
    :type res_name: str
    :param namespace:
    :type namespace: str
    :return: kubernetes resource as python
    :rtype:
    """

    logging.warning(
        f"Didn't find a resource for:\n"
        f" context: {context}\n"
        f" namespace: {namespace}\n"
        f" res_name: {res_name}\n"
    )

    pvcs = get_kube_resources_by_name(context, namespace, 'pvc', res_name)

    matching_resources = []

    for pvc in pvcs:

        pvc_name = pvc['metadata']['name']

        volume_name = pvc['spec']['volumeName']

        logging.info(f'Found res with similar name: {pvc_name}')
        s = json.dumps(pvc, indent=4, sort_keys=True)
        logging.debug(s)

        matching_resources.append((pvc_name, volume_name))

    return matching_resources


def delete_pvc_volumes(context, namespace, pvc_name):

    pvc_pv_tuples = get_pvcs_pvs_by_partial_claim_name(context, namespace, pvc_name)

    for pvc_pv_tuple in pvc_pv_tuples:

        print(pvc_pv_tuples)
        _cmd = f'kubectl --context {context} -n {namespace} delete pvc {pvc_pv_tuple[0]};'
        os.system(_cmd)

        _cmd = f'kubectl --context {context} -n {namespace} delete pv {pvc_pv_tuple[1]};'
        os.system(_cmd)


def is_kube_set_ready(context, namespace, kube_res, res_name, enough_replicas=20):
    """
    Checks if the kubernetes resource e.g. statefulset is ready
    :param enough_replicas: max number of replicas to avoid tracking large incomplete sets
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

        stateful_set = get_kube_res_by_name(context, namespace, kube_res, res_name)

        if stateful_set is not None:

            status = stateful_set['status']

            if 'currentReplicas' in status:
                actual_replicas = status['currentReplicas']
            else:
                actual_replicas = status['updatedReplicas']

            if actual_replicas == status['replicas']:

                if 'readyReplicas' in status and status['readyReplicas'] == actual_replicas:

                    return True
            elif actual_replicas == enough_replicas:

                logging.info(f"Detected {enough_replicas}, considering the set {res_name} OK")
                return True
        else:
            logging.warning(f'stateful set came back None')

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
