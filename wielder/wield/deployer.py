#!/usr/bin/env python
from __future__ import print_function

import logging
import os
import time
import rx
from rx import operators as ops
import concurrent.futures
from kubernetes import client, config

from wielder.util.commander import async_cmd
from wielder.wield.enumerator import KubeResType
from wielder.wield.servicer import observe_service


def delete_multiple(res_tuples, module_root):

    for res_tup in res_tuples:
        name, namespace, res_path, _type = res_tup

        if _type == KubeResType.PV:

            delete_pv(namespace=namespace, pv_type=name)
        else:
            os.system(f'kubectl delete -f {module_root}/{res_path} --wait=false;')

            if _type == KubeResType.DEPLOY or _type == KubeResType.STATEFUL_SET:

                pods = get_pods(
                    name,
                    namespace=namespace
                )

                for pod in pods:
                    os.system(f"kubectl delete -n {namespace} {pod} --force --grace-period=0;")


def apply_multiple(res_tuples, module_root, observe_svc=False):

    for res_tup in res_tuples:
        name, namespace, res_path, _type = res_tup

        os.system(f'kubectl apply -f {module_root}/{res_path}')

        if _type == KubeResType.SERVICE and observe_svc:

            observe_service(
                svc_name=name,
                svc_namespace=namespace
            )

        elif _type == KubeResType.DEPLOY or _type == KubeResType.STATEFUL_SET:

            pods = get_pods(
                name,
                namespace=namespace
            )

            for pod in pods:
                observe_pod(pod)


def delete_pvc_pv(pvc_type, pv_type=None, namespace='default'):
    """
    Deletes persistent volumes and their claims even if they are protected provided their claims are deleted.
    :param pvc_type: claim name or prefix for storage claim automatic creations or stateful sets
    :param pv_type: defaults to pvc_type, claim name or prefix for storage claim automatic creations or stateful sets
    :param namespace:
    """
    pv_type = pvc_type if pv_type is None else pv_type

    delete_pvc(pvc_type, namespace=namespace)
    delete_pv(pv_type, namespace=namespace)


def delete_pv(pv_type, namespace='default'):
    """
    Deletes persistent volumes even if they are protected provided their claims are deleted.
    :param pv_type: volume name or prefix for pv automatic creations or stateful sets
    :param namespace:
    """

    escaped = """'{"metadata":{"finalizers": []}}'"""
    pvc_strings = async_cmd('kubectl get pv')

    for pv_str in pvc_strings:
        pv = pv_str.split('   ')[0]
        logging.info(f'{pv}')

        if f'{namespace}/{pv_type}' in pv_str:
            cmd = f"""kubectl patch persistentvolume/{pv} -p {escaped} --type=merge"""
            logging.info(f'cmd: {cmd}')
            response = async_cmd(cmd)
            logging.info(f'response: {response}')

            cmd = f"kubectl delete persistentvolume/{pv}  --wait=false"
            logging.info(f'cmd: {cmd}')
            response = async_cmd(cmd)
            logging.info(f'response: {response}')


def delete_pvc(pvc_type, namespace='default'):
    """
    Deletes persistent volume claims.
    :param pvc_type: claim name or prefix for storage claim automatic creations or stateful sets
    :param namespace:
    """

    pvc_strings = async_cmd(f'kubectl get pvc -n {namespace}')

    for pvc_str in pvc_strings:
        pvc = pvc_str.split('   ')[0]
        logging.info(pvc)

        if f'{pvc_type}' in pvc_str:

            cmd = f"kubectl delete pvc {pvc} -n {namespace}  --wait=false"
            logging.info(f'cmd: {cmd}')
            response = async_cmd(cmd)
            logging.info(f'response: {response}')


def get_pods(name, exact=False, namespace='default'):

    # TODO check if this could be created once in an object.
    config.load_kube_config(os.path.join(os.environ["HOME"], '.kube/config'))

    v1 = client.CoreV1Api()

    pod_list = v1.list_namespaced_pod(namespace)

    if exact:
        relevant_pods = [pod for pod in pod_list.items if name == pod.metadata.name]
    else:
        relevant_pods = [pod for pod in pod_list.items if name in pod.metadata.name]

    return relevant_pods


def print_pod_gist(pod):

    # logging.info(f"\npod status: {pod.status}\n")
    logging.info(
        f"pod name: {pod.metadata.name}\n"
        f"pod message: {pod.status.message}\n"
        f"pod phase: {pod.status.phase}\n"
        f"pod reason: {pod.status.reason}\n\n"
    )


def all_pod_containers_ready(pod):

    containers_statuses = pod.status.init_container_statuses

    if containers_statuses is not None:

        for container_status in containers_statuses:

            if not container_status.ready:
                return False

    return True


def observe_pod(pod):

    namespace = pod.metadata.namespace
    name = pod.metadata.name
    print_pod_gist(pod)

    interval = 5
    time_elapsed = 0

    while True:

        if 'Running' in pod.status.phase and all_pod_containers_ready(pod):
            break

        if time_elapsed > 400:
            logging.info(f"waited {time_elapsed} that'sn enough exiting")
            return "timeout either provisioning might be too long or some code problem", name, pod

        try:
            logging.info(f"\n\nWaited {time_elapsed} for {name} going to sleep for {interval}")
            time.sleep(interval)
            time_elapsed += interval

        except Exception as e:
            return pod.metadata.name, pod, e

        pods = get_pods(name, namespace=namespace)

        if len(pods) > 0:

            pod = pods[0]
            print_pod_gist(pod)

    return pod.metadata.name, pod, pod.status.phase


def pod_nodes(name, namespace):

    nodes = {}
    pods = get_pods(name=name, namespace=namespace)

    for pod in pods:

        nodes[f'{pod.metadata.name}'] = pod.status.host_ip

    return nodes


def observe_pods(name, callback=None):

    pods = get_pods(name)

    # this is consequential
    # [observe_pod(pod) for pod in pods]

    # this is concurrent

    if len(pods) > 0:

        source = rx.from_(pods)

        with concurrent.futures.ProcessPoolExecutor(len(pods)) as executor:

            composed = source.pipe(
                ops.flat_map(
                    lambda pod: executor.submit(observe_pod, pod)
                )
            )
            composed.subscribe(output if callback is None else callback)


def init_observe_pods(deploy_tuple, use_minikube_repo=False, callback=None, init=True, namespace='default'):

    logging.info(f"callback: {str(callback)}")

    name = deploy_tuple[0]

    if init:

        file_path = deploy_tuple[1]

        if use_minikube_repo:
            os.system(f"eval $(minikube docker-env)")

        # a deployment might have n pods!
        result = os.system(f"kubectl apply -f {file_path}")

        logging.info(f"result: {result}")

    pods = get_pods(name, namespace=namespace)

    # this is consequential
    # [observe_pod(pod) for pod in pods]

    # this is concurrent
    # TODO refactor to not repeat code
    if len(pods) > 0:

        source = rx.from_(pods)

        with concurrent.futures.ProcessPoolExecutor(len(pods)) as executor:
            composed = source.pipe(
                ops.flat_map(
                    lambda pod: executor.submit(observe_pod, pod)
                )
            )
            composed.subscribe(output if callback is None else callback)


# TODO write error and progress discerning logic or use Observer
def output(result):

    logging.info(f"result: {result[0]}")
    [logging.debug(f"result: {r}") for r in result]


# TODO delete all pods try using python kube library if possible
def delete_first_deploy_pod(selector, selector_value):
    """
    :param selector: a value indicated in deployment configuration usually yaml
    :param selector_value: a value which will uniquely select pods of the deployment
    :return: nothing the action is to delete the first pod in the deployment
    """
    # TODO replace ugly hack find a way to replace the deployment conf before running it to avoid killing pods
    os.system(
        f"kubectl delete po $(kubectl get po -l {selector}={selector_value} | awk 'NR == 2 {{print $1}}') --force --grace-period=0;"
    )


# TODO use python library function if exists
# TODO make generic to patches
# TODO warn if unsuccessful
# TODO create a planned patch which doesn't involve actual deployment
def patch_deploy(deploy_name, full_file_path, selector, selector_value):

    # TODO replace ugly hack find a way to replace the deployment conf before running it to avoid killing pods
    os.system(
        f'kubectl patch deploy {deploy_name} --patch "$(cat {full_file_path})";'
    )

    delete_first_deploy_pod(selector, selector_value)


#   TODO make sure of uniqueness
def mount_to_minikube_in_background(mount_name, local_mount_path, minikube_destination_path):

    os.system(
        f'screen -dmS {mount_name} minikube mount {local_mount_path}:{minikube_destination_path};'
    )


# Contents of main is project specific
if __name__ == "__main__":

    logging.info('TODO')

    _pod_nodes = pod_nodes(name='kafka', namespace='kafka')

    print(_pod_nodes)

    # delete_pv(namespace='kafka', pv_type='data')
