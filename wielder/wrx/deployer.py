#!/usr/bin/env python
from __future__ import print_function

import os
import time
import inspect
import rx
import concurrent.futures
from kubernetes import client, config


# TODO move default string to constant
def get_pods(name, exact=False, namespace='default'):

    # TODO check if this could be created once and passed as variable.
    config.load_kube_config(os.path.join(os.environ["HOME"], '.kube/config'))

    v1 = client.CoreV1Api()

    pod_list = v1.list_namespaced_pod(namespace)

    if exact:
        relevant_pods = [pod for pod in pod_list.items if name == pod.metadata.name]
    else:
        relevant_pods = [pod for pod in pod_list.items if name in pod.metadata.name]

    return relevant_pods


def print_pod_gist(pod):

    # print(f"\npod status: {pod.status}\n")
    print(f"pod name: {pod.metadata.name}\n"
          f"pod message: {pod.status.message}\n"
          f"pod phase: {pod.status.phase}\n"
          f"pod reason: {pod.status.reason}\n\n"
          )


def observe_pod(pod):

    namespace = pod.metadata.namespace
    name = pod.metadata.name
    print_pod_gist(pod)

    interval = 5
    time_elapsed = 0

    while 'Running' not in pod.status.phase:

        if time_elapsed > 400:
            print(f"waited {time_elapsed} that'sn enough exiting")
            return "timeout either provisioning might be too long or some code problem", name, pod
            break

        try:
            print(f"\n\nWaited {time_elapsed} for {name} going to sleep for {interval}")
            time.sleep(interval)
            time_elapsed += interval

        except Exception as e:
            return pod.metadata.name, pod, e

        pods = get_pods(name, namespace=namespace)

        if len(pods) > 0:

            pod = pods[0]
            print_pod_gist(pod)

    return pod.metadata.name, pod, pod.status.phase


def observe_pods(name, callback=None):

    pods = get_pods(name)

    # this is consequential
    # [observe_pod(pod) for pod in pods]

    # this is concurrent

    if len(pods) > 0:

        with concurrent.futures.ProcessPoolExecutor(len(pods)) as executor:
            rx.Observable.from_(pods).flat_map(
                lambda pod: executor.submit(observe_pod, pod)
            ).subscribe(output if callback is None else callback)


def init_observe_pods(deploy_tuple, use_minikube_repo=False, callback=None, init=True, namespace='default'):

    print(f"callback: str(callback)")

    name = deploy_tuple[0]

    if init:

        file_path = deploy_tuple[1]

        if use_minikube_repo:
            os.system(f"eval $(minikube docker-env)")

        # a deployment might have n pods!
        result = os.system(f"kubectl create -f {file_path}")

        print(f"result: {result}")

    pods = get_pods(name, namespace=namespace)

    # this is consequential
    # [observe_pod(pod) for pod in pods]

    # this is concurrent
    if len(pods) > 0:

        with concurrent.futures.ProcessPoolExecutor(len(pods)) as executor:
            rx.Observable.from_(pods).flat_map(
                lambda pod: executor.submit(observe_pod, pod)
            ).subscribe(output if callback is None else callback)


# TODO write error and progress discerning logic or use Observer
def output(result):

    print(f"result: {result[0]}")
    # [print(f"result: {r}") for r in result]


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

    d = os.path.dirname(os.path.abspath(inspect.stack()[0][1]))
    print(f"current dir: {d}")
    root_path = d[:d.rfind('/')]
    root_path = root_path[:root_path.rfind('/')]
    print(f"two dirs above where we start path to files: {d}")

    deploy_name = 'rtp-mysql'
    deploy_file = f"{root_path}/deploy/mysql/deploy/mysql-deploy.yaml"

    init_observe_pods((deploy_name, deploy_file))
