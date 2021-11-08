import logging

from wielder.util.util import copy_file_to_pods
from wielder.wield.deployer import get_pods


# TODO Consider not copying all files at once and adding a filter for ignored stuff
#  e.g. .iml and use staging tmp dir

def sync_dev_to_kube(locale, conf):
    """
    Synchronises files (code & configuration) from a development workstation and kubernetes pods
    for development purposes

    # Example of config need to be add to developer.conf
    dev: {

        push: true
        dev_mode: false # if in dev mode then copy files to pod
        pod_names: [airflow-worker] # list of pods in which we need to push modules
        context: kind-pepticom-local

        airflow-worker {
               mount_folders: false # do we need mount pvc and classes to airflow-worker (custom parameter)
               module_list: [dud, pep-services, Wielder, pep-terraform]
               namespace: airflow
               pod_destination: /tmp/duds
          }
    }
    :param locale:
    :param conf:
    :return:
    """

    if conf.dev.push:

        for pod_search_name in conf.dev.pod_names:

            pod_settings = conf.dev[pod_search_name]
            pods = get_pods(pod_search_name, conf.kube_context, False, pod_settings.namespace)

            for module_name in pod_settings.module_list:
                copy_file_to_pods(
                    pods=pods,
                    src=f'{locale.super_project_root}/{module_name}',
                    pod_dest=f'{pod_settings.pod_destination}',
                    namespace=pod_settings.namespace,
                    context=conf.kube_context
                )
